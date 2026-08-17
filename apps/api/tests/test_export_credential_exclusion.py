"""M7-03 — Regression: export never leaks credentials; import rejects credential-bearing packs.

Covers:
- Exporting a signal group while a source connection that stores many credential-shaped field names
  and distinct sentinel values is in the DB produces YAML with zero credential-named keys and does
  not contain any sentinel literal, in both private_backup and public_template modes.
- An exported pack carries no connectors, scopes, or teams keys (§14, §15 of the signal spec).
- The multi-group export path also produces credential-free, structurally-pure YAML.
- Importing a pack that contains any credential-named field is rejected (preview and apply).
- Importing a pack that contains executable content is rejected (preview and apply).
"""

import pytest
import yaml
from fastapi.testclient import TestClient

from em_radar_api.repositories.source_connections import is_credential_field_name


# ── Field-name sets ───────────────────────────────────────────────────────────

# The five field names forbidden by the signal-spec §14; used for import-rejection tests.
_CREDENTIAL_FIELDS = ("token", "password", "api_key", "secret", "authorization")

# Keys in _EXECUTABLE_FIELDS inside validation._check_forbidden_content.
_EXECUTABLE_KEY_FIELDS = ("command", "script", "code")

# String values caught by _EXECUTABLE_PATTERN in validation._check_forbidden_content.
_EXECUTABLE_VALUE_PAYLOADS = (
    "eval('unsafe')",
    "exec('cmd')",
)

# Sentinel values stored in the connection fixture — one per recognized credential shape in
# is_credential_field_name (covers exact CREDENTIAL_FIELD_NAMES entries, names ending in
# "token", and names containing "secret").  Each sentinel is distinct so we can assert none
# of them appear anywhere in the export response text.
_CRED_SENTINELS: dict[str, str] = {
    "token": "sentinel-token-abc1111",
    "access_token": "sentinel-access-token-abc2222",
    "private_token": "sentinel-private-token-abc3333",
    "refresh_token": "sentinel-refresh-token-abc4444",
    "client_secret": "sentinel-client-secret-abc5555",
    "api_key": "sentinel-api-key-abc6666",
    "password": "sentinel-password-abc7777",
    "secret": "sentinel-secret-abc8888",
    "authorization": "sentinel-authorization-abc9999",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _credential_keys(value: object) -> set[str]:
    """Recursively collect credential-named keys from a parsed YAML value.

    Uses is_credential_field_name from the storage layer so the scanner stays in lockstep
    with what the storage layer treats as a credential (including names ending in "token" or
    containing "secret", beyond the five names listed in the signal spec §14).
    """
    if isinstance(value, dict):
        cred = {str(k) for k in value if is_credential_field_name(str(k))}
        return cred.union(*(_credential_keys(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(*(_credential_keys(child) for child in value))
    return set()


def _create_connection_with_sentinels(api_client: TestClient) -> str:
    """Create a source connection whose config contains every recognized credential-field shape.

    The connection API accepts arbitrary config dicts.  Storing all credential-named fields
    with distinct sentinel values lets the export tests assert that none of those values leak
    into the exported YAML text.
    """
    response = api_client.post(
        "/api/connections",
        json={
            "name": "Jira sentinel-creds connection",
            "connector_name": "jira",
            "config": _CRED_SENTINELS,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_signal(api_client: TestClient, name: str) -> str:
    return api_client.post(
        "/api/signal-definitions",
        json={
            "name": name,
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "status_category", "operator": "is", "value": "in_progress"}
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


def _assert_no_sentinel_values(text: str) -> None:
    """Fail if any sentinel credential value appears anywhere in the export text."""
    for field, sentinel in _CRED_SENTINELS.items():
        assert sentinel not in text, (
            f"Sentinel value for {field!r} ({sentinel!r}) must not appear in the export"
        )


_SIGNAL_BLOCK = """\
    - name: Legitimate signal
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
      enabled: true
      origin: user_created
"""

_PACK_HEADER = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: forbidden-content-pack
  version: 1.0.0
  description: A pack embedding forbidden content.
"""

_PACK_SPEC = f"""\
spec:
  export_type: private_backup
  signals:
{_SIGNAL_BLOCK}"""


def _credential_pack(credential_field: str) -> str:
    """A syntactically valid pack that embeds a forbidden credential key in metadata."""
    return _PACK_HEADER + f"  {credential_field}: unsafe-value\n" + _PACK_SPEC


def _executable_key_pack(field_name: str) -> str:
    """A pack with a forbidden executable field key embedded in metadata."""
    return _PACK_HEADER + f"  {field_name}: forbidden-value\n" + _PACK_SPEC


def _executable_value_pack(payload: str) -> str:
    """A pack whose description contains a forbidden executable-content value."""
    # Embed the payload inside a plain YAML string — no quoting needed, the _EXECUTABLE_PATTERN
    # matches anywhere in the value (e.g. "eval(" matches \b(?:eval|exec)\s*\().
    return (
        _PACK_HEADER.replace(
            "A pack embedding forbidden content.",
            f"A description that invokes {payload}",
        )
        + _PACK_SPEC
    )


# ── Export tests ──────────────────────────────────────────────────────────────


def test_export_with_token_connection_private_backup_has_no_credential_keys(
    api_client: TestClient,
) -> None:
    """Exporting a signal group while a source connection with multiple credential-shaped
    fields exists in the DB produces YAML with zero credential-named keys and no sentinel
    values — private_backup mode (REQ-NF-003)."""
    _create_connection_with_sentinels(api_client)
    signal_id = _create_signal(api_client, "Token-check private signal")
    group_id = _create_group(api_client, "token-check-private", [signal_id])

    response = api_client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id], "export_type": "private_backup"},
    )

    assert response.status_code == 200
    _assert_no_sentinel_values(response.text)
    parsed = yaml.safe_load(response.text)
    assert not _credential_keys(parsed), (
        f"Export contains credential-named keys: {_credential_keys(parsed)}"
    )


def test_export_with_token_connection_public_template_has_no_credential_keys(
    api_client: TestClient,
) -> None:
    """Exporting a signal group while a source connection with multiple credential-shaped
    fields exists in the DB produces YAML with zero credential-named keys and no sentinel
    values — public_template mode (REQ-NF-003)."""
    _create_connection_with_sentinels(api_client)
    signal_id = _create_signal(api_client, "Token-check public signal")
    group_id = _create_group(api_client, "token-check-public", [signal_id])

    response = api_client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id], "export_type": "public_template"},
    )

    assert response.status_code == 200
    _assert_no_sentinel_values(response.text)
    parsed = yaml.safe_load(response.text)
    assert not _credential_keys(parsed), (
        f"Export contains credential-named keys: {_credential_keys(parsed)}"
    )


def test_export_carries_no_connectors_scopes_or_teams(api_client: TestClient) -> None:
    """An exported pack carries no connectors, scopes, or teams — §14, §15 of the signal spec.

    A pack is signals-only; scope and connector config live on the team, never in the pack.
    """
    _create_connection_with_sentinels(api_client)
    signal_id = _create_signal(api_client, "Structural purity signal")
    group_id = _create_group(api_client, "structural-purity-group", [signal_id])

    response = api_client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id], "export_type": "private_backup"},
    )

    assert response.status_code == 200
    parsed = yaml.safe_load(response.text)
    assert "connectors" not in parsed, "Top-level 'connectors' key must not appear in exports"
    assert "teams" not in parsed, "Top-level 'teams' key must not appear in exports"
    spec = parsed.get("spec", {})
    assert "connectors" not in spec, "'connectors' must not appear inside spec"
    assert "scopes" not in spec, "'scopes' must not appear inside spec"
    assert "teams" not in spec, "'teams' must not appear inside spec"


def test_multi_group_export_has_no_credential_keys_and_no_forbidden_structure(
    api_client: TestClient,
) -> None:
    """Exporting multiple groups at once also produces credential-free, structurally-pure YAML.

    Exercises the multi-group branch in export_signal_groups_pack.
    """
    _create_connection_with_sentinels(api_client)
    signal_id_a = _create_signal(api_client, "Multi-group signal A")
    signal_id_b = _create_signal(api_client, "Multi-group signal B")
    group_id_a = _create_group(api_client, "multi-export-group-a", [signal_id_a])
    group_id_b = _create_group(api_client, "multi-export-group-b", [signal_id_b])

    response = api_client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id_a, group_id_b], "export_type": "private_backup"},
    )

    assert response.status_code == 200
    _assert_no_sentinel_values(response.text)
    parsed = yaml.safe_load(response.text)
    assert not _credential_keys(parsed), (
        f"Multi-group export contains credential-named keys: {_credential_keys(parsed)}"
    )
    assert "connectors" not in parsed
    assert "teams" not in parsed
    spec = parsed.get("spec", {})
    assert "connectors" not in spec
    assert "scopes" not in spec
    assert "teams" not in spec
    # Both groups are present.
    group_names = {g["name"] for g in spec.get("groups", [])}
    assert group_names == {"multi-export-group-a", "multi-export-group-b"}


# ── Import rejection tests — credential fields ────────────────────────────────


@pytest.mark.parametrize("credential_field", _CREDENTIAL_FIELDS)
def test_import_preview_rejects_credential_bearing_pack(
    api_client: TestClient,
    credential_field: str,
) -> None:
    """Previewing an import of a pack that contains a credential-named key is rejected
    with 422 (REQ-NF-003, signal spec §14)."""
    response = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": _credential_pack(credential_field)},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid-signal-pack"
    assert "credential" in detail["message"].lower()


@pytest.mark.parametrize("credential_field", _CREDENTIAL_FIELDS)
def test_import_apply_rejects_credential_bearing_pack_and_writes_nothing(
    api_client: TestClient,
    credential_field: str,
) -> None:
    """Applying an import of a pack that contains a credential-named key is rejected
    with 422 and no signal definitions are written (REQ-NF-003, signal spec §14)."""
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": _credential_pack(credential_field)},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid-signal-pack"
    assert "credential" in detail["message"].lower()
    assert api_client.get("/api/signal-definitions").json() == []


# ── Import rejection tests — executable / forbidden content ───────────────────


@pytest.mark.parametrize("field_name", _EXECUTABLE_KEY_FIELDS)
def test_import_preview_rejects_executable_key_pack(
    api_client: TestClient,
    field_name: str,
) -> None:
    """Previewing an import of a pack with a forbidden executable field key is rejected
    with 422 (REQ-NF-012, signal spec §14)."""
    response = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": _executable_key_pack(field_name)},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid-signal-pack"
    assert "executable" in detail["message"].lower()


@pytest.mark.parametrize("field_name", _EXECUTABLE_KEY_FIELDS)
def test_import_apply_rejects_executable_key_pack_and_writes_nothing(
    api_client: TestClient,
    field_name: str,
) -> None:
    """Applying an import of a pack with a forbidden executable field key is rejected
    with 422 and nothing is written (REQ-NF-012, signal spec §14)."""
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": _executable_key_pack(field_name)},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid-signal-pack"
    assert "executable" in detail["message"].lower()
    assert api_client.get("/api/signal-definitions").json() == []


@pytest.mark.parametrize("payload", _EXECUTABLE_VALUE_PAYLOADS)
def test_import_preview_rejects_executable_value_pack(
    api_client: TestClient,
    payload: str,
) -> None:
    """Previewing an import of a pack whose description contains executable content is rejected
    with 422 (REQ-NF-012, signal spec §14)."""
    response = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": _executable_value_pack(payload)},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid-signal-pack"
    assert "executable" in detail["message"].lower()


@pytest.mark.parametrize("payload", _EXECUTABLE_VALUE_PAYLOADS)
def test_import_apply_rejects_executable_value_pack_and_writes_nothing(
    api_client: TestClient,
    payload: str,
) -> None:
    """Applying an import of a pack whose description contains executable content is rejected
    with 422 and nothing is written (REQ-NF-012, signal spec §14)."""
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": _executable_value_pack(payload)},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid-signal-pack"
    assert "executable" in detail["message"].lower()
    assert api_client.get("/api/signal-definitions").json() == []
