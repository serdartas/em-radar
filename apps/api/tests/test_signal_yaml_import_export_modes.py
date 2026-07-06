import yaml
from fastapi.testclient import TestClient

_ORG_SPECIFIC_LABEL = "fraud-internal-2024"


def _create_signal(api_client: TestClient, name: str) -> str:
    return api_client.post(
        "/api/signal-definitions",
        json={
            "name": name,
            "description": "Finds labelled fraud work.",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "labels", "operator": "contains", "value": _ORG_SPECIFIC_LABEL}
                ],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
        },
    ).json()["id"]


def _create_group(api_client: TestClient, name: str, signal_ids: list[str]) -> str:
    return api_client.post(
        "/api/signal-config-groups",
        json={"name": name, "signal_ids": signal_ids},
    ).json()["id"]


def test_private_export_contains_no_connectors_scopes_or_credentials(
    api_client: TestClient,
) -> None:
    signal_id = _create_signal(api_client, "Stale fraud work")
    group_id = _create_group(api_client, "fraud-signals", [signal_id])

    text = api_client.get(
        f"/api/signal-pack/export?export_type=private_backup&group_ids={group_id}"
    ).text

    assert "connectors:" not in text
    assert "scopes:" not in text
    assert "target_scopes" not in text
    assert "token" not in text
    assert "base_url" not in text
    assert _ORG_SPECIFIC_LABEL in text


def test_export_requires_group_ids(api_client: TestClient) -> None:
    response = api_client.get("/api/signal-pack/export?export_type=private_backup")

    assert response.status_code == 422


def test_export_then_import_reproduces_equivalent_group(api_client: TestClient) -> None:
    signal_id = _create_signal(api_client, "Stale fraud work")
    group_id = _create_group(api_client, "fraud-signals", [signal_id])

    exported = api_client.get(
        f"/api/signal-pack/export?export_type=private_backup&group_ids={group_id}"
    ).text

    apply = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": exported, "mode": "additive", "conflict": "keep_both"},
    )
    assert apply.status_code == 200

    groups = api_client.get("/api/signal-config-groups").json()
    imported_group = next(group for group in groups if group["id"] != group_id)
    assert len(imported_group["signal_ids"]) == 1

    definitions = {d["id"]: d for d in api_client.get("/api/signal-definitions").json()}
    imported_signal = definitions[imported_group["signal_ids"][0]]
    original_signal = definitions[signal_id]
    assert imported_signal["expression"] == original_signal["expression"]
    assert imported_signal["report_settings"] == original_signal["report_settings"]


def test_multi_group_export_dedupes_shared_signal_and_references_by_name(
    api_client: TestClient,
) -> None:
    signal_id = _create_signal(api_client, "Stale fraud work")
    group_a = _create_group(api_client, "scrum-health", [signal_id])
    group_b = _create_group(api_client, "flow-health", [signal_id])

    text = api_client.get(
        f"/api/signal-pack/export?export_type=private_backup"
        f"&group_ids={group_a}&group_ids={group_b}"
    ).text
    pack = yaml.safe_load(text)

    signals = pack["spec"]["signals"]
    assert len(signals) == 1
    assert signals[0]["name"] == "Stale fraud work"

    groups = {group["name"]: group for group in pack["spec"]["groups"]}
    assert groups["scrum-health"]["signals"] == ["Stale fraud work"]
    assert groups["flow-health"]["signals"] == ["Stale fraud work"]


def test_multi_group_import_recreates_both_groups_with_one_signal(
    api_client: TestClient,
) -> None:
    signal_id = _create_signal(api_client, "Stale fraud work")
    group_a = _create_group(api_client, "scrum-health", [signal_id])
    group_b = _create_group(api_client, "flow-health", [signal_id])

    exported = api_client.get(
        f"/api/signal-pack/export?export_type=private_backup"
        f"&group_ids={group_a}&group_ids={group_b}"
    ).text

    apply = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": exported, "mode": "additive", "conflict": "keep_both"},
    )
    assert apply.status_code == 200

    groups = api_client.get("/api/signal-config-groups").json()
    imported = [group for group in groups if group["id"] not in {group_a, group_b}]
    assert len(imported) == 2

    # Both imported groups reference the same single re-created signal.
    referenced = {signal_id for group in imported for signal_id in group["signal_ids"]}
    assert len(referenced) == 1


def test_public_template_export_scrubs_org_specific_condition_values(
    api_client: TestClient,
) -> None:
    signal_id = _create_signal(api_client, "Stale fraud work")
    group_id = _create_group(api_client, "fraud-signals", [signal_id])

    private_text = api_client.get(
        f"/api/signal-pack/export?export_type=private_backup&group_ids={group_id}"
    ).text
    public_text = api_client.get(
        f"/api/signal-pack/export?export_type=public_template&group_ids={group_id}"
    ).text

    assert "public_template" in public_text
    assert _ORG_SPECIFIC_LABEL in private_text
    assert _ORG_SPECIFIC_LABEL not in public_text
    # The field/operator structure is preserved so the template stays usable.
    assert "labels" in public_text
