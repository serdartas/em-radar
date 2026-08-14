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
from collections import namedtuple
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


class _RaisingEq:
    """An object whose equality must never be evaluated by the redaction sweep."""

    __hash__ = None

    def __eq__(self, other: object) -> bool:
        raise AssertionError("equality must not be evaluated on arbitrary extras")


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


def test_filter_redacts_bytes_leaf_in_extra() -> None:
    """A credential carried as a bytes leaf inside a container is redacted too."""
    token = "bytes-leaf-secret-abcdef"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    record = _make_record("request")
    record.headers = [(b"Authorization", b"Bearer " + token.encode())]
    filt.filter(record)

    rendered = repr(record.headers)
    assert token not in rendered
    assert _REDACTED in rendered


def test_filter_handles_namedtuple_extra_without_crashing() -> None:
    """Rebuilding a tuple subclass must not raise; secret-free values stay intact and a
    secret-bearing one is still redacted."""
    Pair = namedtuple("Pair", ["key", "value"])
    token = "namedtuple-secret-abcdef"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    intact = _make_record("request")
    intact.pair = Pair("region", "eu-west-1")
    filt.filter(intact)
    assert intact.pair == Pair("region", "eu-west-1")

    secret = _make_record("request")
    secret.pair = Pair("Authorization", f"Bearer {token}")
    filt.filter(secret)
    assert token not in str(secret.pair)


def test_short_value_below_threshold_is_not_registered() -> None:
    """A very short token is not registered for exact-match replacement, so it cannot
    mangle unrelated log lines."""
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values(["xy"])

    record = _make_record("xylophone status ok")
    filt.filter(record)
    assert record.getMessage() == "xylophone status ok"


def test_short_token_in_headers_repr_is_redacted_by_key() -> None:
    """A short, unregistered token inside a mapping/Headers repr is redacted by header
    key context, while non-credential headers are left intact."""
    filt = _CredentialRedactionFilter()

    record = _make_record("outbound %s", "Headers({'private-token': 'abc', 'host': 'x'})")
    filt.filter(record)

    msg = record.getMessage()
    assert "'abc'" not in msg
    assert _REDACTED in msg
    assert "'host': 'x'" in msg


def test_filter_redacts_bytearray_leaf() -> None:
    """A credential carried as a bytearray leaf is redacted while keeping its type."""
    token = "bytearray-secret-abcdef"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    record = _make_record("request")
    record.blob = bytearray(f"Bearer {token}".encode())
    filt.filter(record)

    assert isinstance(record.blob, bytearray)
    assert token not in record.blob.decode()
    assert _REDACTED in record.blob.decode()


def test_filter_clears_exc_info_after_caching_redacted_traceback() -> None:
    """A formatter rendering %(exc_info)s directly must not see the raw exception object."""
    token = "exc-info-secret-abcdef"
    configure_log_scrubbing()
    _CREDENTIAL_FILTER.add_sensitive_values([token])

    logger = logging.getLogger(f"{_TEST_LOGGER_NAME}.excinfo")
    try:
        raise ValueError(f"failure carrying {token}")
    except ValueError:
        record = logger.makeRecord(
            logger.name, logging.ERROR, "", 0, "request failed", (), sys.exc_info()
        )

    formatted = logging.Formatter("%(message)s exc=%(exc_info)s").format(record)
    assert token not in formatted
    assert _REDACTED in formatted


def test_filter_handles_cyclic_extra_without_recursing_forever() -> None:
    """A self-referential extra container must not raise RecursionError."""
    filt = _CredentialRedactionFilter()

    payload: dict[str, object] = {}
    payload["self"] = payload
    record = _make_record("request")
    record.payload = payload
    filt.filter(record)


def test_cyclic_extra_does_not_reintroduce_registered_secret() -> None:
    """A cyclic reference must be replaced with a marker, not the original object, so a
    registered secret elsewhere in the cycle cannot leak through the repeated reference."""
    token = "cyclic-registered-secret-abcdef"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    payload: dict[str, object] = {"value": token}
    payload["self"] = payload
    record = _make_record("request")
    record.payload = payload
    filt.filter(record)

    assert token not in repr(record.payload)


def test_short_token_under_credential_key_is_redacted_in_live_mapping() -> None:
    """A short, unregistered credential under a credential-named key in a live mapping is
    redacted by key context, so a %(headers)s render cannot emit it."""
    filt = _CredentialRedactionFilter()

    record = _make_record("request")
    record.headers = {"Authorization": "abc", "Host": "example.com"}
    filt.filter(record)

    formatted = logging.Formatter("%(headers)s").format(record)
    assert "abc" not in formatted
    assert _REDACTED in formatted
    assert "example.com" in formatted


def test_filter_redacts_credential_in_unreferenced_args() -> None:
    """A credential in a message argument not referenced by the template must be sanitized,
    since getMessage() never exposes it but %(args)s / structured handlers could."""
    token = "unreferenced-arg-secret-abcdef"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    record = _make_record("%(safe)s", {"safe": "ok", "token": token})
    filt.filter(record)

    assert token not in repr(record.args)


def test_filter_redacts_byte_header_pairs_by_key() -> None:
    """Byte (key, value) header pairs (e.g. httpx Headers.raw) are redacted by key context."""
    filt = _CredentialRedactionFilter()

    record = _make_record("request")
    record.raw_headers = [(b"PRIVATE-TOKEN", b"abc"), (b"Host", b"example.com")]
    filt.filter(record)

    rendered = repr(record.raw_headers)
    assert "abc" not in rendered
    assert _REDACTED in rendered
    assert "example.com" in rendered


def test_filter_redacts_registered_token_used_as_mapping_key() -> None:
    """A registered credential used as a mapping key is redacted, not copied verbatim."""
    token = "keypos-registered-value-abcdef"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    record = _make_record("request")
    record.payload = {token: "cached"}
    filt.filter(record)

    assert token not in repr(record.payload)
    assert _REDACTED in repr(record.payload)


def test_filter_redacts_mapping_valued_message() -> None:
    """A mapping passed as the log message is sanitized by credential-key context."""
    filt = _CredentialRedactionFilter()

    record = _make_record({"token": "abc", "safe": "ok"})  # type: ignore[arg-type]
    filt.filter(record)

    rendered = record.getMessage()
    assert "abc" not in rendered
    assert _REDACTED in rendered
    assert "ok" in rendered


def test_credential_free_exception_keeps_exc_info() -> None:
    """An exception whose traceback holds no credential must keep its exc_info tuple so
    structured handlers still receive the exception type/value/traceback."""
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values(["some-registered-secret-abcdef"])

    try:
        raise ValueError("ordinary failure, no secrets here")
    except ValueError:
        record = logging.LogRecord("t", logging.ERROR, "", 0, "failed", (), sys.exc_info())
    filt.filter(record)

    assert record.exc_info is not None
    assert record.exc_text is None


def test_filter_redacts_authorization_value_for_any_scheme() -> None:
    """An Authorization header value is redacted for any scheme (or none)."""
    filt = _CredentialRedactionFilter()
    cases = {
        "Authorization: Digest digest-secret-xyz": "digest-secret-xyz",
        "Authorization: bareTokenValue": "bareTokenValue",
        "authorization = Custom-Scheme creds-123": "creds-123",
    }
    for line, secret in cases.items():
        record = _make_record("%s", line)
        filt.filter(record)
        msg = record.getMessage()
        assert secret not in msg, f"{secret!r} leaked in {msg!r}"
        assert _REDACTED in msg


def test_filter_redacts_registered_token_used_as_pair_key() -> None:
    """A registered credential used as the key of a (key, value) pair is redacted."""
    token = "pairkey-registered-token-abcdef"
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token])

    record = _make_record("request")
    record.payload = [(token, "cached")]
    filt.filter(record)

    assert token not in repr(record.payload)
    assert _REDACTED in repr(record.payload)


def test_filter_does_not_evaluate_equality_on_arbitrary_extra() -> None:
    """The attribute sweep must never invoke __eq__ on an arbitrary extra object, since a
    raising or non-boolean implementation would abort the process-wide logging hook."""
    filt = _CredentialRedactionFilter()

    record = _make_record("request")
    sentinel = _RaisingEq()
    record.payload = sentinel
    filt.filter(record)

    assert record.payload is sentinel


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
