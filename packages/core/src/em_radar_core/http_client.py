import logging
import re
import threading
from collections.abc import Callable, Mapping, Sequence

import httpx

_REDACTED = "[REDACTED]"
_UPSTREAM_RECORD_FACTORY: Callable[..., logging.LogRecord] | None = None
_UPSTREAM_MAKE_RECORD: Callable[..., logging.LogRecord] | None = None
_EXCEPTION_FORMATTER = logging.Formatter()
# Record attributes handled explicitly by filter(); the generic attribute sweep skips them.
_SKIP_ATTRIBUTES = frozenset({"msg", "args", "exc_info", "exc_text", "stack_info"})

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

    def _redact_value(self, value: object) -> object:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, Mapping):
            return {key: self._redact_value(item) for key, item in value.items()}
        if isinstance(value, list | tuple | set | frozenset):
            return type(value)(self._redact_value(item) for item in value)
        return value

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
        # Structured `extra` attributes (including nested containers) are attached after
        # the record factory runs; sweep every remaining attribute so a formatter that
        # renders them cannot emit a raw credential.
        for key, value in list(record.__dict__.items()):
            if key in _SKIP_ATTRIBUTES:
                continue
            scrubbed = self._redact_value(value)
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


def _redacting_make_record(
    self: logging.Logger, *args: object, **kwargs: object
) -> logging.LogRecord:
    if _UPSTREAM_MAKE_RECORD is None:
        raise RuntimeError("Credential-redacting makeRecord was not initialized")
    record = _UPSTREAM_MAKE_RECORD(self, *args, **kwargs)
    _CREDENTIAL_FILTER.filter(record)
    return record


def _install_redacting_record_factory() -> None:
    global _UPSTREAM_RECORD_FACTORY

    if _UPSTREAM_RECORD_FACTORY is not None:
        return
    _UPSTREAM_RECORD_FACTORY = logging.getLogRecordFactory()
    logging.setLogRecordFactory(_redacting_record_factory)


def _install_redacting_make_record() -> None:
    global _UPSTREAM_MAKE_RECORD

    if _UPSTREAM_MAKE_RECORD is not None:
        return
    _UPSTREAM_MAKE_RECORD = logging.Logger.makeRecord
    logging.Logger.makeRecord = _redacting_make_record  # type: ignore[method-assign]


def configure_log_scrubbing() -> None:
    """Install credential redaction process-wide.

    Two hooks cooperate so no log record can carry a raw credential regardless of how or
    where it is emitted:

    - The record factory scrubs every record's message, args, traceback and stack info at
      creation, for records from any logger.
    - `Logger.makeRecord` is wrapped so redaction also runs *after* structured `extra`
      attributes are attached — the universal record-creation chokepoint, so it covers
      handlers registered later and non-propagating child loggers too.

    Call this once at application startup, before any connector is initialised; calling it
    more than once is safe.
    """
    _install_redacting_record_factory()
    _install_redacting_make_record()


def create_redacting_async_client(
    *,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    sensitive_values: Sequence[str] = (),
    **client_kwargs: object,
) -> httpx.AsyncClient:
    _CREDENTIAL_FILTER.add_sensitive_values(sensitive_values)
    _install_redacting_record_factory()
    _install_redacting_make_record()
    return client_factory(**client_kwargs)


__all__ = ["configure_log_scrubbing", "create_redacting_async_client"]
