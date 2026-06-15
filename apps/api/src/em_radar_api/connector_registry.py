from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from importlib.metadata import entry_points
from typing import cast

from jsonschema import SchemaError, ValidationError, validators

from em_radar_core.connectors import (
    ConnectorBase,
    ConnectorConfigError,
    ConnectorNotFoundError,
)

ENTRY_POINT_GROUP = "em_radar.connectors"
CREDENTIAL_FIELD_NAMES = frozenset({"token", "password", "api_key", "secret", "authorization"})


def list_connectors() -> list[dict[str, object]]:
    return [
        {
            "name": connector_type.name,
            "display_name": connector_type.display_name,
            "config_schema": _schema_with_secret_flags(connector_type.config_schema),
            "capabilities": asdict(connector_type({}).describe_capabilities()),
        }
        for connector_type in _connector_types()
    ]


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


def _connector_type(name: str) -> type[ConnectorBase]:
    for connector_type in _connector_types():
        if connector_type.name == name:
            return connector_type
    raise ConnectorNotFoundError(f"Connector {name!r} is not registered")


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
