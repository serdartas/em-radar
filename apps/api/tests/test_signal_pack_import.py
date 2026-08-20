from fastapi.testclient import TestClient

from em_radar_api.tables import ProjectTable, RepositoryTable
from em_radar_core.models import Source

DUPLICATE_SIGNAL_NAMES_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: duplicate-signals-pack

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

INVALID_EXPRESSION_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: invalid-expression-pack

  description: Pack with an invalid expression.
spec:
  export_type: private_backup
  signals:
    - name: Invalid Signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: jira_private_priority
            operator: is
            value: High
      report_settings:
        severity: warning
        category: flow
"""

GROUP_FAILURE_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: invalid-group-pack

  description: Pack with a group that duplicates one signal reference.
spec:
  export_type: private_backup
  signals:
    - name: Atomic Signal
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
  groups:
    - name: Invalid Group
      signals: [Atomic Signal, Atomic Signal]
"""

SCOPED_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: scoped-pack

  description: Pack with scope.
spec:
  export_type: private_backup
  signals:
    - name: Scoped Signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: status_category
            operator: is
            value: in_progress
      report_settings:
        severity: warning
        category: flow
      scope:
        project_keys: [KNOWN, MISSING]
        repository_paths: [known/repository, missing/*]
"""


def test_definition_pack_rejects_invalid_expression_before_import(
    api_client: TestClient,
    session_factory,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": INVALID_EXPRESSION_PACK},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid-signal-pack"


def test_definition_pack_apply_rolls_back_when_late_group_write_fails(
    api_client: TestClient,
    session_factory,
) -> None:
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": GROUP_FAILURE_PACK},
    )

    assert response.status_code == 422
    assert api_client.get("/api/signal-definitions").json() == []


def test_import_preview_warns_about_unknown_scope_targets(
    api_client: TestClient,
    session_factory,
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
