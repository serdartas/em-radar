import base64
import logging

from em_radar_core.http_client import _CredentialRedactionFilter

_REDACTED = "[REDACTED]"


def _make_record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg=message,
        args=args,
        exc_info=None,
    )


def test_filter_fully_redacts_auth_header_when_token_is_substring() -> None:
    """When the raw token is a substring of the encoded auth header, the filter must
    redact the longer auth header value first so no partial credential survives.

    Example: token='YUBi' appears verbatim inside base64('a@b.com:YUBi').
    If the shorter token were processed first, the auth header becomes
    'Basic [REDACTED]LmNvbTpZVUJp' — the surrounding base64 leaks.
    Processing longest values first eliminates the full auth header in one pass.
    """
    email = "a@b.com"
    token = "YUBi"
    secret = f"{email}:{token}".encode()
    auth_header = "Basic " + base64.b64encode(secret).decode()

    # Confirm the structural invariant that makes this case interesting.
    assert token in auth_header, f"test invariant failed: {token!r} not in {auth_header!r}"

    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values([token, auth_header])

    # Force worst-case iteration order (shortest first) so the test fails deterministically
    # when the sorted(key=len, reverse=True) fix is absent, regardless of PYTHONHASHSEED.
    class _ShortestFirstSet(set):  # type: ignore[type-arg]
        def __iter__(self) -> object:
            return iter(sorted(super().__iter__(), key=len))

    filt._sensitive_values = _ShortestFirstSet([token, auth_header])

    record = _make_record("credential: %s", auth_header)
    filt.filter(record)

    msg = record.getMessage()
    assert msg == f"credential: {_REDACTED}"
    assert token not in msg
    assert auth_header not in msg


def test_filter_redacts_multiple_occurrences_in_one_message() -> None:
    filt = _CredentialRedactionFilter()
    token = "s3cr3t"
    filt.add_sensitive_values([token])

    record = _make_record("first=%s second=%s", token, token)
    filt.filter(record)

    msg = record.getMessage()
    assert token not in msg
    assert msg == f"first={_REDACTED} second={_REDACTED}"


def test_filter_leaves_unrelated_message_unchanged() -> None:
    filt = _CredentialRedactionFilter()
    filt.add_sensitive_values(["topsecret"])

    record = _make_record("ordinary log message")
    original_msg = record.msg
    filt.filter(record)

    assert record.getMessage() == "ordinary log message"
    assert record.msg is original_msg  # msg object not replaced when no redaction needed
