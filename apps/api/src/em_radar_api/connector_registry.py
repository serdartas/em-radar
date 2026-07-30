from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from importlib.metadata import entry_points
from typing import cast

from jsonschema import SchemaError, ValidationError, validators

from em_radar_core.connectors import (
    Capabilities,
    ConnectorBase,
    ConnectorConfigError,
    ConnectorError,
    ConnectorNotFoundError,
    SignalCapabilitySchema,
)

from em_radar_api.db import schema_version

ENTRY_POINT_GROUP = "em_radar.connectors"
CREDENTIAL_FIELD_NAMES = frozenset({"token", "password", "api_key", "secret", "authorization"})


def list_connectors() -> list[dict[str, object]]:
    connectors: list[dict[str, object]] = []
    for connector_type in _compatible_connector_types():
        descriptor = {
            "name": connector_type.name,
            "display_name": connector_type.display_name,
            "config_schema": _schema_with_secret_flags(connector_type.config_schema),
            "capabilities": asdict(connector_type.describe_capabilities()),
        }
        if hasattr(connector_type, "describe_signal_schema"):
            descriptor["signal_schema"] = asdict(_signal_schema(connector_type))
        connectors.append(descriptor)
    return connectors


def get_connector_capabilities(name: str) -> Capabilities | None:
    """Return capabilities for a registered connector, or None if not found or incompatible."""
    try:
        return _connector_type(name).describe_capabilities()
    except (ConnectorNotFoundError, ConnectorError):
        return None


def create_connector(name: str, config: Mapping[str, object]) -> ConnectorBase:
    connector_type = _connector_type(name)
    try:
        validator = validators.validator_for(connector_type.config_schema)
        validator.check_schema(connector_type.config_schema)
        validator(connector_type.config_schema).validate(dict(config))
    except SchemaError as error:
        raise ConnectorConfigError("Connector config schema is invalid") from error
    except ValidationError as error:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise ConnectorConfigError(
            f"Invalid connector config at {path}: failed {error.validator} validation"
        ) from error
    return connector_type(dict(config))


def _connector_types() -> list[type[ConnectorBase]]:
    return sorted(
        (
            cast(type[ConnectorBase], entry_point.load())
            for entry_point in entry_points(group=ENTRY_POINT_GROUP)
        ),
        key=lambda connector_type: connector_type.name,
    )


def _compatible_connector_types() -> list[type[ConnectorBase]]:
    connector_types = _connector_types()
    for connector_type in connector_types:
        _ensure_compatible(connector_type)
    return connector_types


def _connector_type(name: str) -> type[ConnectorBase]:
    for connector_type in _connector_types():
        if connector_type.name == name:
            _ensure_compatible(connector_type)
            return connector_type
    raise ConnectorNotFoundError(f"Connector {name!r} is not registered")


def _ensure_compatible(connector_type: type[ConnectorBase]) -> None:
    if connector_type.min_model_version > schema_version:
        raise ConnectorError(
            f"Connector {connector_type.name!r} requires canonical model version "
            f"{connector_type.min_model_version}; upgrade EM Radar from version {schema_version}"
        )


def _signal_schema(connector_type: type[ConnectorBase]) -> SignalCapabilitySchema:
    if hasattr(connector_type, "describe_signal_schema"):
        return connector_type.describe_signal_schema()
    return SignalCapabilitySchema(
        connector_type=connector_type.name,
        entity_types=(),
        scope_types=(),
        fields=(),
    )


def _schema_with_secret_flags(schema: Mapping[str, object]) -> dict[str, object]:
    flagged = deepcopy(dict(schema))
    _flag_secret_properties(flagged)
    return flagged


def _flag_secret_properties(value: object) -> None:
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            for name, property_schema in properties.items():
                if (
                    isinstance(property_schema, dict)
                    and str(name).lower() in CREDENTIAL_FIELD_NAMES
                ):
                    property_schema["writeOnly"] = True
        for child in value.values():
            _flag_secret_properties(child)
    elif isinstance(value, list):
        for child in value:
            _flag_secret_properties(child)
