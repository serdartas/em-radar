from fastapi.testclient import TestClient


def _create_signal(api_client: TestClient, name: str, label: str) -> str:
    return api_client.post(
        "/api/signal-definitions",
        json={
            "name": name,
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [{"field": "labels", "operator": "contains", "value": label}],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "origin": "user_created",
        },
    ).json()["id"]


def _create_group(api_client: TestClient, name: str, signal_ids: list[str]) -> str:
    return api_client.post(
        "/api/signal-config-groups",
        json={"name": name, "signal_ids": signal_ids},
    ).json()["id"]


def _export(api_client: TestClient, group_ids: list[str]) -> str:
    query = "&".join(f"group_ids={group_id}" for group_id in group_ids)
    return api_client.get(f"/api/signal-pack/export?export_type=private_backup&{query}").text


def _seed_and_export(api_client: TestClient) -> tuple[str, str]:
    signal_id = _create_signal(api_client, "Stale work", "tuned-label")
    group_id = _create_group(api_client, "scrum-health", [signal_id])
    return signal_id, _export(api_client, [group_id])


def test_preview_reports_signal_and_group_clashes(api_client: TestClient) -> None:
    _, exported = _seed_and_export(api_client)

    preview = api_client.post("/api/signal-pack/import", json={"raw_yaml": exported}).json()

    assert preview["signal_name_clashes"] == ["Stale work"]
    assert preview["group_name_clashes"] == ["scrum-health"]


def test_conflict_skip_creates_nothing(api_client: TestClient) -> None:
    _, exported = _seed_and_export(api_client)

    api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": exported, "conflict": "skip"},
    )

    assert len(api_client.get("/api/signal-definitions").json()) == 1
    assert len(api_client.get("/api/signal-config-groups").json()) == 1


def test_conflict_keep_both_suffixes_signal_and_group(api_client: TestClient) -> None:
    _, exported = _seed_and_export(api_client)

    api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": exported, "conflict": "keep_both"},
    )

    signal_names = {d["name"] for d in api_client.get("/api/signal-definitions").json()}
    group_names = {g["name"] for g in api_client.get("/api/signal-config-groups").json()}
    assert signal_names == {"Stale work", "Stale work (2)"}
    assert group_names == {"scrum-health", "scrum-health (2)"}

    new_group = next(
        g
        for g in api_client.get("/api/signal-config-groups").json()
        if g["name"] == "scrum-health (2)"
    )
    new_signal = next(
        d for d in api_client.get("/api/signal-definitions").json() if d["name"] == "Stale work (2)"
    )
    # The duplicated group wires to the duplicated signal, not the original.
    assert new_group["signal_ids"] == [new_signal["id"]]


def test_conflict_overwrite_updates_existing_without_creating(api_client: TestClient) -> None:
    signal_id = _create_signal(api_client, "Stale work", "old-label")
    _create_group(api_client, "scrum-health", [signal_id])
    # Export a different signal value, then rename it back to the clashing name by hand.
    other_signal = _create_signal(api_client, "Stale work overwrite", "new-label")
    other_group = _create_group(api_client, "scrum-health overwrite", [other_signal])
    exported = (
        _export(api_client, [other_group])
        .replace("Stale work overwrite", "Stale work")
        .replace("scrum-health overwrite", "scrum-health")
    )

    api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": exported, "conflict": "overwrite"},
    )

    definitions = api_client.get("/api/signal-definitions").json()
    overwritten = next(d for d in definitions if d["id"] == signal_id)
    assert overwritten["expression"]["conditions"][0]["value"] == "new-label"
    # No suffixed duplicate of the clashing name was created.
    assert sum(1 for d in definitions if d["name"] == "Stale work") == 1


def test_conflict_cancel_writes_nothing(api_client: TestClient) -> None:
    _, exported = _seed_and_export(api_client)

    api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": exported, "conflict": "cancel"},
    )

    assert len(api_client.get("/api/signal-definitions").json()) == 1
    assert len(api_client.get("/api/signal-config-groups").json()) == 1


def test_pack_with_unknown_group_signal_reference_is_rejected(api_client: TestClient) -> None:
    pack = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: broken-pack
  version: 1.0.0
  description: References a signal that is not defined.
spec:
  export_type: private_backup
  signals:
    - name: Defined signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: x
      report_settings:
        severity: warning
        category: flow
  groups:
    - name: broken-group
      signals: [Missing signal]
"""

    response = api_client.post("/api/signal-pack/import", json={"raw_yaml": pack})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid-signal-pack"
