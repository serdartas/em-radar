import logging
import re
import threading
from collections.abc import Callable, Sequence

import httpx

_REDACTED = "[REDACTED]"
_UPSTREAM_RECORD_FACTORY: Callable[..., logging.LogRecord] | None = None
_EXCEPTION_FORMATTER = logging.Formatter()

# Defense-in-depth: credential-shaped substrings are scrubbed even when the exact
# value was never registered by a connector (a token pasted into a URL, a second
# auth scheme, a byte-for-byte different header string, etc.).
_CREDENTIAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+\S+"), r"\1" + _REDACTED),
    (re.compile(r"(?i)(private-token\s*[:=]\s*)\S+"), r"\1" + _REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), f"Bearer {_REDACTED}"),
)


class _CredentialRedactionFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        # Registered secrets are retained for the process lifetime (deduplicated by the
        # set): a connector's token may still be logged by background tasks after the
        # connector closes, so values are never removed once seen.
        self._sensitive_values: set[str] = set()
        self._lock = threading.Lock()

    def add_sensitive_values(self, values: Sequence[str]) -> None:
        with self._lock:
            self._sensitive_values.update(value for value in values if value)

    def redact(self, text: str) -> str:
        with self._lock:
            values = sorted(self._sensitive_values, key=len, reverse=True)
        for value in values:
            text = text.replace(value, _REDACTED)
        for pattern, replacement in _CREDENTIAL_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        # Tracebacks and stack traces bypass getMessage(); a Formatter renders them
        # after this filter runs, so pre-fill (and scrub) the cached text here.
        if record.exc_text is not None:
            record.exc_text = self.redact(record.exc_text)
        elif record.exc_info is not None and record.exc_info[0] is not None:
            record.exc_text = self.redact(_EXCEPTION_FORMATTER.formatException(record.exc_info))
        if record.stack_info is not None:
            record.stack_info = self.redact(record.stack_info)
        # Structured `extra` attributes are attached after the record factory returns,
        # so scrub every string attribute when this filter also runs at handler stage.
        for key, value in list(record.__dict__.items()):
            if isinstance(value, str):
                scrubbed = self.redact(value)
                if scrubbed != value:
                    record.__dict__[key] = scrubbed
        return True


_CREDENTIAL_FILTER = _CredentialRedactionFilter()


def _redacting_record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
    if _UPSTREAM_RECORD_FACTORY is None:
        raise RuntimeError("Credential-redacting record factory was not initialized")
    record = _UPSTREAM_RECORD_FACTORY(*args, **kwargs)
    _CREDENTIAL_FILTER.filter(record)
    return record


def _install_redacting_record_factory() -> None:
    global _UPSTREAM_RECORD_FACTORY

    if _UPSTREAM_RECORD_FACTORY is not None:
        return
    _UPSTREAM_RECORD_FACTORY = logging.getLogRecordFactory()
    logging.setLogRecordFactory(_redacting_record_factory)


def configure_log_scrubbing() -> None:
    """Install credential redaction process-wide.

    The record factory scrubs every record's message, args, traceback and stack info at
    creation. `extra` attributes are attached only afterwards, so the same filter is also
    registered on the root logger and its handlers, where it runs once the record is fully
    populated. Call this once at application startup, before any connector is initialised;
    calling it more than once is safe.
    """
    _install_redacting_record_factory()
    root = logging.getLogger()
    if _CREDENTIAL_FILTER not in root.filters:
        root.addFilter(_CREDENTIAL_FILTER)
    for handler in root.handlers:
        if _CREDENTIAL_FILTER not in handler.filters:
            handler.addFilter(_CREDENTIAL_FILTER)


def create_redacting_async_client(
    *,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    sensitive_values: Sequence[str] = (),
    **client_kwargs: object,
) -> httpx.AsyncClient:
    _CREDENTIAL_FILTER.add_sensitive_values(sensitive_values)
    _install_redacting_record_factory()
    return client_factory(**client_kwargs)


__all__ = ["configure_log_scrubbing", "create_redacting_async_client"]
