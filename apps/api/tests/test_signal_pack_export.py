import re

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session
import yaml

from em_radar_api.repositories.signal_configs import upsert_signal_config
from em_radar_api.signal_configs import SignalConfigUpsert
from em_radar_config import SIGNAL_CATALOG, load_signal_pack
from em_radar_core.models import Severity


def test_minimal_export_is_valid_and_omits_untouched_signals(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id="stale-in-progress-work-item",
                enabled=False,
                severity_override=Severity.CRITICAL,
                params={"days_threshold": 2},
                scope={"project_keys": ["RAD"]},
            ),
        )
        upsert_signal_config(
            session,
            SignalConfigUpsert(signal_id="blocked-without-update", params={"days_threshold": 3}),
        )

    response = api_client.get("/api/signal-pack/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/yaml")
    assert response.headers["content-disposition"] == 'attachment; filename="signal-pack.yaml"'
    pack = load_signal_pack(response.text).pack
    assert re.fullmatch(r"local-overrides-\d{8}-\d{6}", pack.metadata.name)
    assert [signal.id for signal in pack.spec.signals] == ["stale-in-progress-work-item"]
    assert pack.spec.signals[0].enabled is False
    assert pack.spec.signals[0].severity is Severity.CRITICAL
    assert pack.spec.signals[0].params == {"days_threshold": 2, "exclude_labels": []}
    assert pack.spec.signals[0].scope is not None
    assert pack.spec.signals[0].scope.project_keys == ["RAD"]


def test_full_export_contains_every_signal_with_effective_values(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id="stale-in-progress-work-item",
                severity_override=Severity.CRITICAL,
                params={"days_threshold": 2},
            ),
        )

    response = api_client.get(
        "/api/signal-pack/export",
        params={"mode": "full", "name": "current-settings"},
    )

    assert response.status_code == 200
    pack = load_signal_pack(response.text).pack
    signals = {signal.id: signal for signal in pack.spec.signals}
    assert pack.metadata.name == "current-settings"
    assert set(signals) == set(SIGNAL_CATALOG)
    assert signals["stale-in-progress-work-item"].severity is Severity.CRITICAL
    assert signals["blocked-without-update"].severity is Severity.CRITICAL
    assert all(signal.params is not None for signal in signals.values())


def test_export_has_no_credential_named_keys_and_omits_field_mappings_by_default(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/signal-pack/export")

    assert response.status_code == 200
    exported = yaml.safe_load(response.text)
    assert exported["spec"].get("field_mappings") is None
    assert not _credential_keys(exported)


def test_export_rejects_invalid_mode_and_name(api_client: TestClient) -> None:
    assert api_client.get("/api/signal-pack/export", params={"mode": "other"}).status_code == 422
    assert (
        api_client.get("/api/signal-pack/export", params={"name": "Not Valid"}).status_code == 422
    )


def _credential_keys(value: object) -> set[str]:
    credential_names = {"token", "password", "api_key", "secret", "authorization"}
    if isinstance(value, dict):
        keys = {str(key).casefold() for key in value}
        return (keys & credential_names).union(
            *(_credential_keys(child) for child in value.values())
        )
    if isinstance(value, list):
        return set().union(*(_credential_keys(child) for child in value))
    return set()
