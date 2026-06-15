from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_api.models.signal_pack_history import SignalPackHistory
from em_radar_api.repositories.signal_configs import list_signal_configs, upsert_signal_config
from em_radar_api.signal_configs import SignalConfigUpsert
from em_radar_core.models import Severity

MINIMAL_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: imported-overrides
  version: 1.0.0
  description: Imported test overrides.
spec:
  signals:
    - id: stale-in-progress-work-item
      enabled: false
      severity: critical
      params:
        days_threshold: 2
"""


def test_import_preview_and_additive_apply_change_only_pack_signals_and_store_yaml(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id="blocked-without-update",
                enabled=False,
                params={"days_threshold": 1},
            ),
        )

    preview_response = api_client.post("/api/signal-pack/import", json={"raw_yaml": MINIMAL_PACK})

    assert preview_response.status_code == 200
    assert preview_response.json() == {
        "pack_name": "imported-overrides",
        "warnings": [],
        "changes": [
            {
                "signal_id": "stale-in-progress-work-item",
                "enabled": {"before": True, "after": False},
                "severity": {"before": "warning", "after": "critical"},
                "params": {
                    "before": {"days_threshold": 7, "exclude_labels": []},
                    "after": {"days_threshold": 2, "exclude_labels": []},
                },
            }
        ],
    }
    with session_factory() as session:
        assert [config.signal_id for config in list_signal_configs(session)] == [
            "blocked-without-update"
        ]
        assert list(session.exec(select(SignalPackHistory))) == []

    apply_response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": MINIMAL_PACK},
    )

    assert apply_response.status_code == 200
    with session_factory() as session:
        configs = {config.signal_id: config for config in list_signal_configs(session)}
        assert not configs["blocked-without-update"].enabled
        assert configs["blocked-without-update"].params == {"days_threshold": 1}
        assert not configs["stale-in-progress-work-item"].enabled
        assert configs["stale-in-progress-work-item"].severity_override is Severity.CRITICAL
        assert configs["stale-in-progress-work-item"].params == {
            "days_threshold": 2,
            "exclude_labels": [],
        }
        history = list(session.exec(select(SignalPackHistory)))
        assert len(history) == 1
        assert history[0].pack_name == "imported-overrides"
        assert history[0].raw_yaml == MINIMAL_PACK


def test_invalid_pack_is_rejected_without_state_change(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(signal_id="blocked-without-update", params={"days_threshold": 1}),
        )

    invalid_pack = MINIMAL_PACK.replace("days_threshold: 2", "unknown_param: 2")
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": invalid_pack},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid-signal-pack"
    with session_factory() as session:
        configs = list_signal_configs(session)
        assert len(configs) == 1
        assert configs[0].params == {"days_threshold": 1}
        assert list(session.exec(select(SignalPackHistory))) == []


def test_replace_all_resets_signals_not_in_pack(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id="blocked-without-update",
                enabled=False,
                severity_override=Severity.INFO,
                params={"days_threshold": 1},
            ),
        )

    preview_response = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": MINIMAL_PACK, "mode": "replace_all"},
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()
    blocked_diff = next(
        change for change in preview["changes"] if change["signal_id"] == "blocked-without-update"
    )
    assert blocked_diff == {
        "signal_id": "blocked-without-update",
        "enabled": {"before": False, "after": True},
        "severity": {"before": "info", "after": "critical"},
        "params": {"before": {"days_threshold": 1}, "after": {"days_threshold": 3}},
    }

    apply_response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": MINIMAL_PACK, "mode": "replace_all"},
    )

    assert apply_response.status_code == 200
    with session_factory() as session:
        configs = {config.signal_id: config for config in list_signal_configs(session)}
        assert len(configs) == 13
        assert configs["blocked-without-update"].enabled
        assert configs["blocked-without-update"].severity_override is None
        assert configs["blocked-without-update"].params == {"days_threshold": 3}
        assert not configs["stale-in-progress-work-item"].enabled
