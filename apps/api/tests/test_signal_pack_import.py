from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_api.models.signal_pack_history import SignalPackHistory
from em_radar_api.repositories.signal_configs import list_signal_configs, upsert_signal_config
from em_radar_api.signal_configs import SignalConfigUpsert
from em_radar_api.tables import ProjectTable, RepositoryTable
from em_radar_core.models import Severity, Source

DUPLICATE_SIGNAL_NAMES_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: duplicate-signals-pack
  version: 1.0.0
  description: Pack with two signals sharing the same name.
spec:
  export_type: private_backup
  signals:
    - name: My Signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: alpha
      report_settings:
        severity: warning
        category: flow
    - name: My Signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: beta
      report_settings:
        severity: critical
        category: flow
"""

DUPLICATE_GROUP_NAMES_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: duplicate-groups-pack
  version: 1.0.0
  description: Pack with unique signal names but two groups sharing the same name.
spec:
  export_type: private_backup
  signals:
    - name: Signal Alpha
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: alpha
      report_settings:
        severity: warning
        category: flow
    - name: Signal Beta
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: beta
      report_settings:
        severity: warning
        category: flow
  groups:
    - name: My Group
      signals: [Signal Alpha]
    - name: My Group
      signals: [Signal Beta]
"""

VALID_DEFINITION_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: unique-signals-pack
  version: 1.0.0
  description: Pack with unique signal names.
spec:
  export_type: private_backup
  signals:
    - name: Signal Alpha
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: alpha
      report_settings:
        severity: warning
        category: flow
    - name: Signal Beta
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: beta
      report_settings:
        severity: warning
        category: flow
"""

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

SCOPED_PACK = MINIMAL_PACK.replace(
    "      params:\n",
    """\
      scope:
        project_keys: [KNOWN, MISSING]
        repository_paths: [known/repository, missing/*]
      params:
""",
)


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


def test_import_preview_warns_about_unknown_scope_targets(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            ProjectTable(
                source=Source.JIRA,
                external_id="known-project",
                key="KNOWN",
                name="Known project",
            )
        )
        session.add(
            RepositoryTable(
                source=Source.JIRA,
                external_id="known-repository",
                name="Known repository",
                full_path="known/repository",
                default_branch="main",
            )
        )
        session.commit()

    response = api_client.post("/api/signal-pack/import", json={"raw_yaml": SCOPED_PACK})

    assert response.status_code == 200
    assert response.json()["warnings"] == [
        {
            "code": "unknown-scope-target",
            "message": "Project key MISSING does not exist",
            "path": "spec.signals.0.scope.project_keys",
        },
        {
            "code": "unknown-scope-target",
            "message": "Repository path missing/* does not exist",
            "path": "spec.signals.0.scope.repository_paths",
        },
    ]


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


def test_import_with_duplicate_signal_names_is_rejected_with_no_partial_import(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": DUPLICATE_SIGNAL_NAMES_PACK},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid-signal-pack"
    assert "My Signal" in response.json()["detail"]["message"]
    # No signals were persisted — no partial import occurred.
    assert api_client.get("/api/signal-definitions").json() == []


def test_preview_reports_intra_pack_duplicate_signal_names(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": DUPLICATE_SIGNAL_NAMES_PACK},
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["intra_pack_duplicate_signal_names"] == ["My Signal"]


def test_import_with_duplicate_group_names_is_rejected_with_no_partial_import(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": DUPLICATE_GROUP_NAMES_PACK},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid-signal-pack"
    assert "My Group" in response.json()["detail"]["message"]
    # Signals were NOT persisted — the rejection happened before any DB write.
    assert api_client.get("/api/signal-definitions").json() == []


def test_preview_reports_intra_pack_duplicate_group_names(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": DUPLICATE_GROUP_NAMES_PACK},
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["intra_pack_duplicate_group_names"] == ["My Group"]


def test_cancel_on_duplicate_name_pack_returns_preview_without_writing(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": DUPLICATE_SIGNAL_NAMES_PACK, "conflict": "cancel"},
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["intra_pack_duplicate_signal_names"] == ["My Signal"]
    # cancel never writes anything, even for valid packs.
    assert api_client.get("/api/signal-definitions").json() == []


def test_valid_definition_pack_with_unique_names_imports_successfully(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": VALID_DEFINITION_PACK},
    )

    assert response.status_code == 200
    definitions = api_client.get("/api/signal-definitions").json()
    names = {d["name"] for d in definitions}
    assert "Signal Alpha" in names
    assert "Signal Beta" in names
