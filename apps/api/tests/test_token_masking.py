"""Parametrized tests asserting no raw token leaks through any API serializer or endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session

from em_radar_api.db import create_db_engine
from em_radar_api.repositories.source_connections import (
    create_source_connection,
    get_source_connection,
    list_source_connections,
    update_source_connection,
)
from em_radar_api.routers.source_connections import ConnectionTestResponse
from em_radar_api.security import mask_secret
from em_radar_api.source_connections import (
    ConnectorName,
    SourceConnectionCreate,
    SourceConnectionUpdate,
)

# Realistic field names that normalize into CREDENTIAL_FIELD_NAMES or match the
# suffix/substring rules in is_credential_field_name.
CREDENTIAL_FIELD_NAMES = [
    "token",
    "access_token",
    "api_key",
    "authorization",
    "client_secret",
    "password",
    "private_token",
    "refresh_token",
    "secret",
]


# ---------------------------------------------------------------------------
# Unit tests for mask_secret
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "secret, expected",
    [
        # Tokens longer than 4 chars: keep last 4
        ("abcdefgh", "****efgh"),
        ("jira-token-123456789", "****6789"),
        ("demo-token-abcdefgh", "****efgh"),
        ("glpat-xxxxxxxxxxxxxxxxxxxx", "****xxxx"),
        ("a" * 20, f"****{'a' * 4}"),
        # Exactly 5 chars: last 4 shown
        ("abcde", "****bcde"),
        # Exactly 4 chars: fully masked
        ("abcd", "****"),
        # Shorter than 4 chars: fully masked
        ("abc", "****"),
        ("ab", "****"),
        ("a", "****"),
        # Empty string: fully masked
        ("", "****"),
    ],
)
def test_mask_secret_format(secret: str, expected: str) -> None:
    assert mask_secret(secret) == expected


def test_mask_secret_never_returns_raw_value() -> None:
    """mask_secret must never return the original value unchanged."""
    for length in range(1, 40):
        secret = "x" * length
        result = mask_secret(secret)
        assert result != secret, f"mask_secret returned raw secret for length {length}"
        assert result.startswith("****"), (
            f"mask_secret output lacks '****' prefix for length {length}"
        )


def test_mask_secret_short_token_reveals_no_chars() -> None:
    """For tokens <=4 chars, the mask must reveal none of the original characters."""
    for secret in ["a", "ab", "abc", "abcd"]:
        result = mask_secret(secret)
        assert result == "****"


# ---------------------------------------------------------------------------
# Repository-layer tests (in-memory SQLite, no DB mock)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_token",
    [
        "jira-token-123456789",
        "glpat-abcdefghijklmnopq",
        "short",
        "x",
        "exactly4char",
        "a" * 32,
    ],
)
def test_repository_read_never_leaks_raw_token(raw_token: str) -> None:
    """create/list/get/update all return masked config values — never the full raw token."""
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        created = create_source_connection(
            session,
            SourceConnectionCreate(
                name="Test connection",
                connector_name=ConnectorName.JIRA,
                config={"base_url": "https://jira.example.com", "token": raw_token},
            ),
        )

        _assert_config_values_masked(created.config, raw_token, "create response")

        listed = list_source_connections(session)
        for conn in listed:
            _assert_config_values_masked(conn.config, raw_token, "list response")

        fetched = get_source_connection(session, created.id)
        assert fetched is not None
        _assert_config_values_masked(fetched.config, raw_token, "get response")

        updated = update_source_connection(
            session,
            created.id,
            SourceConnectionUpdate(config={"base_url": "https://updated.example.com"}),
        )
        assert updated is not None
        _assert_config_values_masked(updated.config, raw_token, "update response")


@pytest.mark.parametrize("field_name", CREDENTIAL_FIELD_NAMES)
def test_every_credential_field_name_is_masked(field_name: str) -> None:
    """Each recognized credential field name is masked, not just `token`."""
    raw_token = "super-secret-value-abcdefgh"
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        created = create_source_connection(
            session,
            SourceConnectionCreate(
                name="Cred field connection",
                connector_name=ConnectorName.JIRA,
                config={"base_url": "https://jira.example.com", field_name: raw_token},
            ),
        )

    assert created.config[field_name] == "****efgh"
    _assert_config_values_masked(created.config, raw_token, f"field {field_name}")


def test_credential_nested_in_list_is_masked() -> None:
    """A credential field inside a list of objects is masked, not leaked."""
    raw_token = "list-nested-secret-abcdefgh"
    engine = create_db_engine(":memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        created = create_source_connection(
            session,
            SourceConnectionCreate(
                name="List nested creds",
                connector_name=ConnectorName.JIRA,
                config={
                    "base_url": "https://jira.example.com",
                    "accounts": [{"token": raw_token}],
                },
            ),
        )

    _assert_config_values_masked(created.config, raw_token, "list-nested credential")


def test_test_connection_response_carries_no_credential_fields() -> None:
    """The test-connection response schema must never expose a credential-shaped field."""
    forbidden = {"token", "password", "api_key", "secret", "authorization", "config"}
    assert forbidden.isdisjoint(ConnectionTestResponse.model_fields)


# ---------------------------------------------------------------------------
# Endpoint-level tests (full HTTP round-trip)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_token",
    [
        "jira-token-123456789",
        "glpat-xxxxxxxxxxxxxxxxxxxx",
        "tok",
        "1234",  # exactly 4 — fully masked
        "12345",  # 5 chars — ****2345
        "a" * 40,
    ],
)
def test_endpoint_responses_never_leak_raw_token(
    api_client: TestClient,
    raw_token: str,
) -> None:
    """POST /connections, GET /connections, and PATCH /connections/{id} must all mask tokens."""
    create_resp = api_client.post(
        "/api/connections",
        json={
            "name": "Masked test",
            "connector_name": "jira",
            "config": {"base_url": "https://jira.example.com", "token": raw_token},
        },
    )
    assert create_resp.status_code == 201
    _assert_config_values_masked(create_resp.json()["config"], raw_token, "POST /connections")

    connection_id = create_resp.json()["id"]

    list_resp = api_client.get("/api/connections")
    assert list_resp.status_code == 200
    for conn in list_resp.json():
        _assert_config_values_masked(conn["config"], raw_token, "GET /connections")

    patch_resp = api_client.patch(
        f"/api/connections/{connection_id}",
        json={"config": {"base_url": "https://updated.example.com"}},
    )
    assert patch_resp.status_code == 200
    _assert_config_values_masked(patch_resp.json()["config"], raw_token, "PATCH /connections/{id}")


def test_masked_token_has_correct_format_in_endpoint(api_client: TestClient) -> None:
    """Verify the exact `****` + last-4 format appears in endpoint responses."""
    token = "demo-token-123456789"
    resp = api_client.post(
        "/api/connections",
        json={
            "name": "Format check",
            "connector_name": "jira",
            "config": {"base_url": "https://jira.example.com", "token": token},
        },
    )
    assert resp.status_code == 201
    config = resp.json()["config"]
    assert config["token"] == "****6789"
    assert config["base_url"] == "https://jira.example.com"


def test_short_token_fully_masked_in_endpoint(api_client: TestClient) -> None:
    """Tokens of 4 chars or fewer are fully masked to `****` with no suffix."""
    for idx, short in enumerate(["x", "ab", "abc", "1234"]):
        resp = api_client.post(
            "/api/connections",
            json={
                "name": f"Short token conn {idx}",
                "connector_name": "jira",
                "config": {"base_url": "https://jira.example.com", "token": short},
            },
        )
        assert resp.status_code == 201
        assert resp.json()["config"]["token"] == "****", (
            f"Expected '****' for token {short!r}, got {resp.json()['config']['token']!r}"
        )


def test_nested_credential_field_masked_in_endpoint(api_client: TestClient) -> None:
    """Credential fields nested inside objects are also masked."""
    token = "nested-api-key-abcdefgh"
    resp = api_client.post(
        "/api/connections",
        json={
            "name": "Nested creds",
            "connector_name": "jira",
            "config": {"base_url": "https://jira.example.com", "auth": {"api_key": token}},
        },
    )
    assert resp.status_code == 201
    nested = resp.json()["config"]["auth"]
    assert nested["api_key"] == "****efgh"
    assert token not in nested["api_key"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_config_values_masked(
    config: object,
    raw_token: str,
    context: str,
) -> None:
    """Recursively check that raw_token does not appear as any leaf value in config."""
    _check_no_raw_value(config, raw_token, context, path="config")


def _check_no_raw_value(value: object, raw_token: str, context: str, path: str) -> None:
    if isinstance(value, str):
        assert value != raw_token, f"Raw token {raw_token!r} leaked as value at {path} in {context}"
    elif isinstance(value, dict):
        for k, v in value.items():
            _check_no_raw_value(v, raw_token, context, f"{path}.{k}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _check_no_raw_value(item, raw_token, context, f"{path}[{i}]")
