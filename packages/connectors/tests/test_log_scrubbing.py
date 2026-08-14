"""Dedicated tests for credential redaction from log output (REQ-NF-003).

Verifies that tokens and Authorization / PRIVATE-TOKEN header values never appear
in log output regardless of which logger receives the message.

Coverage:
- _CredentialRedactionFilter unit tests for Bearer, Basic-auth, and PRIVATE-TOKEN patterns
- Credential-shaped values are scrubbed even without registration (defense in depth)
- A registered token embedded in an exception traceback is scrubbed before formatting
- A credential passed through logging `extra` is scrubbed at handler stage
- A late-registered handler on a non-propagating logger with nested-container `extra`
  still emits no raw credential (makeRecord wrap covers every emission path)
- configure_log_scrubbing() public API is idempotent
- Jira connector (Bearer PAT mode): token and Authorization header not in any log record
- Jira connector (Basic auth mode): token and encoded Authorization header not in any log record
- GitLab connector: token / PRIVATE-TOKEN value not in any log record
- Shared global filter: after both connectors are initialised, either token is scrubbed
  from every logger in the process
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import sys
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.connectors import ConnectorAuthError
from em_radar_core.http_client import (
    _CREDENTIAL_FILTER,
    _CredentialRedactionFilter,
    configure_log_scrubbing,
)

_REDACTED = "[REDACTED]"
# A fresh, uniquely-named logger created at test time is never disabled by
# alembic's fileConfig(disable_existing_loggers=True) run in earlier suites, and
# it is fully under this module's control (no coupling to third-party names).
_TEST_LOGGER_NAME = "em_radar_scrub_test"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _make_record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg=message,
        args=args,
        exc_info=None,
    )


# --------------------------------------------------------------------------- #
# _CredentialRedactionFilter unit tests
# --------------------------------------------------------------------------- #


def test_filter_redacts_bearer_token_in_authorization_line() -> None:
    """A Bearer token that appears in a log line is replaced with [REDACTED]."""
    token = "glpat-superSecret-123"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    record = _make_record("Authorization: Bearer %s", token)
    filt.filter(record)

    msg = record.getMessage()
    assert token not in msg
    assert _REDACTED in msg


def test_filter_redacts_private_token_header_value() -> None:
    """A PRIVATE-TOKEN value that appears in a log line is replaced with [REDACTED]."""
    token = "glpat-private-token-xyz"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    record = _make_record("PRIVATE-TOKEN: %s", token)
    filt.filter(record)

    msg = record.getMessage()
    assert token not in msg
    assert _REDACTED in msg


def test_filter_redacts_full_basic_auth_header_before_raw_token() -> None:
    """The full Basic-auth header must be redacted before the raw token substring.

    If the shorter raw token were processed first, only the token substring inside
    the base64 blob would be replaced, leaving the surrounding encoded bytes visible.
    Longest-first ordering eliminates the full header in one pass.
    """
    email = "user@example.com"
    token = "myjiratoken"
    encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
    auth_header = f"Basic {encoded}"

    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token, auth_header])

    record = _make_record("Authorization: %s", auth_header)
    filt.filter(record)

    msg = record.getMessage()
    assert token not in msg
    assert auth_header not in msg
    assert _REDACTED in msg


def test_filter_redacts_credential_shaped_value_without_registration() -> None:
    """Credential-shaped header values are scrubbed even when never registered."""
    filt = _CredentialRedactionFilter()

    bearer = _make_record("Authorization: Bearer %s", "unregistered-bearer-value")
    filt.filter(bearer)
    assert "unregistered-bearer-value" not in bearer.getMessage()
    assert _REDACTED in bearer.getMessage()

    private = _make_record("PRIVATE-TOKEN: %s", "glpat-unregistered-value")
    filt.filter(private)
    assert "glpat-unregistered-value" not in private.getMessage()
    assert _REDACTED in private.getMessage()


def test_filter_redacts_token_in_exception_traceback() -> None:
    """A registered token embedded in an exception must not survive to the Formatter.

    Tracebacks are rendered from exc_info/exc_text after the record factory runs, so
    the filter has to scrub the cached traceback text, not just the log message.
    """
    token = "exception-embedded-secret-abcdef"
    configure_log_scrubbing()
    _CREDENTIAL_FILTER.add_sensitive_values([token])

    logger = logging.getLogger(f"{_TEST_LOGGER_NAME}.exc")
    try:
        raise ValueError(f"upstream failure carrying {token}")
    except ValueError:
        record = logger.makeRecord(
            logger.name, logging.ERROR, "", 0, "connector request failed", (), sys.exc_info()
        )

    formatted = logging.Formatter().format(record)
    assert token not in formatted
    assert _REDACTED in formatted


def test_filter_redacts_token_in_extra_field() -> None:
    """A credential passed via logging `extra` is attached after the record factory,
    so the handler-stage filter must scrub arbitrary string attributes too."""
    token = "extra-field-secret-abcdef"
    configure_log_scrubbing()
    _CREDENTIAL_FILTER.add_sensitive_values([token])

    logger = logging.getLogger(f"{_TEST_LOGGER_NAME}.extra")
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        "",
        0,
        "outbound request",
        (),
        None,
        extra={"authorization": f"Bearer {token}"},
    )
    # Simulate the handler-stage invocation where `extra` attributes are present.
    _CREDENTIAL_FILTER.filter(record)

    formatted = logging.Formatter("%(message)s auth=%(authorization)s").format(record)
    assert token not in formatted
    assert _REDACTED in formatted


def test_late_handler_and_nested_extra_are_redacted() -> None:
    """End-to-end: a handler registered after configure_log_scrubbing(), on a
    non-propagating child logger, formatting a nested-container `extra`, still emits
    no raw credential — proving the makeRecord wrap covers every emission path."""
    token = "late-handler-nested-secret-abcdef"
    configure_log_scrubbing()
    _CREDENTIAL_FILTER.add_sensitive_values([token])

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s headers=%(headers)s"))
    logger = logging.getLogger(f"{_TEST_LOGGER_NAME}.late")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        logger.info("outbound", extra={"headers": {"Authorization": f"Bearer {token}"}})
    finally:
        logger.removeHandler(handler)

    output = stream.getvalue()
    assert token not in output
    assert _REDACTED in output


# --------------------------------------------------------------------------- #
# configure_log_scrubbing public API
# --------------------------------------------------------------------------- #


def test_configure_log_scrubbing_is_idempotent() -> None:
    """Calling configure_log_scrubbing multiple times must not stack factories or raise."""
    configure_log_scrubbing()
    configure_log_scrubbing()
    # If the factory accidentally wrapped itself, creating any log record would recurse.
    record = logging.getLogger("test.idempotent").makeRecord(
        "test.idempotent", logging.DEBUG, "", 0, "hello", (), None
    )
    assert record.getMessage() == "hello"


# --------------------------------------------------------------------------- #
# Jira connector: Bearer PAT — token and Authorization value not in logs
# --------------------------------------------------------------------------- #


def test_jira_bearer_pat_does_not_log_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the Jira connector uses a plain PAT (Bearer), neither the raw token nor
    the full Authorization header value should appear in any captured log record."""
    token = "jira-bearer-pat-secret"
    authorization = f"Bearer {token}"

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # Simulate what a debug-enabled httpx / httpcore logger might emit.
            logging.getLogger(_TEST_LOGGER_NAME).debug(
                "send request Authorization: %s", request.headers["authorization"]
            )
            logging.getLogger(_TEST_LOGGER_NAME).debug("raw token: %s", token)
            return httpx.Response(401)

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector({"base_url": "https://jira.example.com", "token": token})
        caplog.set_level(logging.DEBUG)
        with pytest.raises(ConnectorAuthError):
            await connector.test_connection()
        await connector.close()

    asyncio.run(run())

    assert any(_REDACTED in r.getMessage() for r in caplog.records), (
        "Expected at least one [REDACTED] marker — no redaction occurred"
    )
    assert all(token not in r.getMessage() for r in caplog.records), (
        f"Raw token {token!r} found in log output"
    )
    assert all(authorization not in r.getMessage() for r in caplog.records), (
        "Authorization header value found in log output"
    )


# --------------------------------------------------------------------------- #
# Jira connector: Basic auth — encoded header and raw token not in logs
# --------------------------------------------------------------------------- #


def test_jira_basic_auth_does_not_log_encoded_header(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the Jira connector uses Basic auth (email + token), neither the raw token
    nor the base64-encoded Authorization header value should appear in any log record."""
    token = "jira-token-basic-mode"
    email = "em@example.com"
    encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
    authorization = f"Basic {encoded}"

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # Simulate a header value reaching a debug logger.
            logging.getLogger(_TEST_LOGGER_NAME).debug(
                "Authorization: %s", request.headers["authorization"]
            )
            logging.getLogger(_TEST_LOGGER_NAME).debug("raw token: %s", token)
            return httpx.Response(401)

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": token,
                "auth_email": email,
            }
        )
        caplog.set_level(logging.DEBUG)
        with pytest.raises(ConnectorAuthError):
            await connector.test_connection()
        await connector.close()

    asyncio.run(run())

    assert any(_REDACTED in r.getMessage() for r in caplog.records), (
        "Expected at least one [REDACTED] marker — no redaction occurred"
    )
    assert all(token not in r.getMessage() for r in caplog.records), (
        f"Raw token {token!r} found in log output"
    )
    assert all(authorization not in r.getMessage() for r in caplog.records), (
        "Encoded Authorization header found in log output"
    )


# --------------------------------------------------------------------------- #
# GitLab connector: PRIVATE-TOKEN value not in logs
# --------------------------------------------------------------------------- #


def test_gitlab_private_token_does_not_appear_in_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The PRIVATE-TOKEN header value must be absent from every log record when a GitLab
    connector request is made."""
    token = "glpat-very-secret-token"

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # Simulate the PRIVATE-TOKEN header value reaching a debug logger.
            logging.getLogger(_TEST_LOGGER_NAME).debug(
                "PRIVATE-TOKEN: %s", request.headers.get("private-token")
            )
            logging.getLogger(_TEST_LOGGER_NAME).debug("token value: %s", token)
            return httpx.Response(401)

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector({"base_url": "https://gitlab.example.com", "token": token})
        caplog.set_level(logging.DEBUG)
        with pytest.raises(ConnectorAuthError):
            await connector.test_connection()
        await connector.close()

    asyncio.run(run())

    assert any(_REDACTED in r.getMessage() for r in caplog.records), (
        "Expected at least one [REDACTED] marker — no redaction occurred"
    )
    assert all(token not in r.getMessage() for r in caplog.records), (
        f"PRIVATE-TOKEN value {token!r} found in log output"
    )


# --------------------------------------------------------------------------- #
# Shared global filter: both connector tokens scrubbed by any logger
# --------------------------------------------------------------------------- #


def test_shared_filter_redacts_both_connector_tokens(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After both connectors are initialised, the shared global filter must scrub
    either token from any logger in the process — not just the httpx logger."""
    jira_token = "jira-shared-scrub-test-token"
    gitlab_token = "gitlab-shared-scrub-test-token"

    async def run() -> None:
        def noop(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(noop))
        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(noop))

        jira_connector = JiraConnector(
            {"base_url": "https://jira.example.com", "token": jira_token}
        )
        gitlab_connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": gitlab_token}
        )

        caplog.set_level(logging.DEBUG)
        # Use a completely unrelated logger to confirm the factory is process-wide.
        logging.getLogger("unrelated.component").debug(
            "jira=%s gitlab=%s", jira_token, gitlab_token
        )

        await jira_connector.close()
        await gitlab_connector.close()

    asyncio.run(run())

    messages = [r.getMessage() for r in caplog.records]
    assert any(messages), "Expected at least one log record"
    for msg in messages:
        assert jira_token not in msg, f"Jira token found in: {msg!r}"
        assert gitlab_token not in msg, f"GitLab token found in: {msg!r}"
