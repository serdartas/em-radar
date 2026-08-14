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
# `msg` and `args` are swept (not skipped) so a credential in a mapping-valued message or in
# an argument the template does not reference — which getMessage() never exposes as text — is
# still sanitized.
_SKIP_ATTRIBUTES = frozenset({"exc_info", "exc_text", "stack_info"})
# Exact-value redaction is skipped for trivially short values: a 1-4 char token would
# otherwise mangle unrelated log lines wherever those characters occur. This matches the
# M7-01 read-surface rule that treats tokens of 4 or fewer characters as fully maskable;
# such credentials are still caught structurally by the header patterns below.
_MIN_REGISTERED_LENGTH = 5

# Defense-in-depth: credential-shaped substrings are scrubbed even when the exact
# value was never registered by a connector (a token pasted into a URL, a second
# auth scheme, a byte-for-byte different header string, a short token, etc.).
# Redaction is keyed on the credential header name so the value is scrubbed regardless
# of its length or form.
_CREDENTIAL_HEADER_KEYS = r"authorization|private-token"
_CYCLE_PLACEHOLDER = "<circular reference>"
# Mapping keys whose value is a credential; used to redact by key context when scrubbing a
# live structured `extra` mapping (mirrors the connection serializer's credential rule).
_CREDENTIAL_KEY_NAMES = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "clientsecret",
        "password",
        "privatetoken",
        "refreshtoken",
        "secret",
        "token",
    }
)
_CREDENTIAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Quoted mapping / dict / httpx Headers repr, e.g. {'private-token': 'abc'}.
    (
        re.compile(rf"(?i)(['\"](?:{_CREDENTIAL_HEADER_KEYS})['\"]\s*:\s*)(['\"]).*?\2"),
        r"\1\2" + _REDACTED + r"\2",
    ),
    # Header-line form, e.g. Authorization: Bearer xxx / PRIVATE-TOKEN: xxx.
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+\S+"), r"\1" + _REDACTED),
    (re.compile(r"(?i)(private-token\s*[:=]\s*)\S+"), r"\1" + _REDACTED),
    # Bare Bearer scheme.
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), f"Bearer {_REDACTED}"),
)


def _is_credential_key(key: object) -> bool:
    if isinstance(key, bytes | bytearray):
        key = bytes(key).decode("utf-8", "replace")
    if not isinstance(key, str):
        return False
    normalized = "".join(character for character in key.casefold() if character.isalnum())
    return (
        normalized in _CREDENTIAL_KEY_NAMES
        or normalized.endswith("token")
        or "secret" in normalized
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
            self._sensitive_values.update(
                value for value in values if len(value) >= _MIN_REGISTERED_LENGTH
            )

    def redact(self, text: str) -> str:
        with self._lock:
            values = sorted(self._sensitive_values, key=len, reverse=True)
        for value in values:
            text = text.replace(value, _REDACTED)
        for pattern, replacement in _CREDENTIAL_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _redact_value(
        self, value: object, seen: frozenset[int] = frozenset()
    ) -> tuple[bool, object]:
        # Returns (changed, new_value). The changed flag is tracked structurally so the
        # caller never evaluates equality on an arbitrary object whose __eq__ could raise.
        # `seen` carries the identities on the current path to stop self-referential extras
        # from recursing forever.
        if isinstance(value, str):
            redacted = self.redact(value)
            return (redacted != value, redacted)
        if isinstance(value, bytes | bytearray):
            decoded = bytes(value).decode("utf-8", "replace")
            redacted = self.redact(decoded)
            if redacted == decoded:
                return (False, value)
            encoded = redacted.encode("utf-8")
            return (True, bytearray(encoded) if isinstance(value, bytearray) else encoded)
        if isinstance(value, Mapping | list | tuple | set | frozenset):
            if id(value) in seen:
                # Replace a repeated reference with a marker rather than the original object,
                # which would reintroduce unsanitized content held elsewhere in the cycle.
                return (True, _CYCLE_PLACEHOLDER)
            seen = seen | {id(value)}
            if isinstance(value, Mapping):
                changed = False
                result: dict[object, object] = {}
                for key, item in value.items():
                    # Keys can carry a credential too (a token used as a dict key); redact
                    # the key, but decide credential-key context from the original key.
                    key_changed, new_key = self._redact_value(key, seen)
                    changed = changed or key_changed
                    if _is_credential_key(key):
                        result[new_key] = _REDACTED
                        if not (isinstance(item, str) and item == _REDACTED):
                            changed = True
                        continue
                    item_changed, new_item = self._redact_value(item, seen)
                    changed = changed or item_changed
                    result[new_key] = new_item
                return (changed, result if changed else value)
            changed = False
            items = []
            for item in value:
                # (key, value) pairs, e.g. httpx Headers.raw = [(b"PRIVATE-TOKEN", b"abc")],
                # are redacted by key context so short/byte values are not missed.
                if (
                    isinstance(item, tuple | list)
                    and len(item) == 2
                    and _is_credential_key(item[0])
                ):
                    items.append(
                        (item[0], _REDACTED) if isinstance(item, tuple) else [item[0], _REDACTED]
                    )
                    changed = True
                    continue
                item_changed, new_item = self._redact_value(item, seen)
                changed = changed or item_changed
                items.append(new_item)
            if not changed:
                return (False, value)
            # Rebuild with base-type constructors so tuple/set subclasses (e.g. NamedTuple)
            # never hit an incompatible constructor.
            if isinstance(value, list):
                return (True, items)
            if isinstance(value, tuple):
                return (True, tuple(items))
            if isinstance(value, frozenset):
                return (True, frozenset(items))
            return (True, set(items))
        return (False, value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        # Tracebacks and stack traces bypass getMessage(); a Formatter renders them
        # after this filter runs, so pre-fill (and scrub) the cached text here. The raw
        # exc_info tuple is dropped only when its traceback actually contained a credential,
        # so a formatter rendering %(exc_info)s cannot emit it — while credential-free
        # exceptions keep their tuple for structured handlers.
        if record.exc_text is not None:
            redacted_exc = self.redact(record.exc_text)
            if redacted_exc != record.exc_text:
                record.exc_text = redacted_exc
                record.exc_info = None
        elif record.exc_info is not None and record.exc_info[0] is not None:
            formatted_exc = _EXCEPTION_FORMATTER.formatException(record.exc_info)
            redacted_exc = self.redact(formatted_exc)
            if redacted_exc != formatted_exc:
                record.exc_text = redacted_exc
                record.exc_info = None
        if record.stack_info is not None:
            record.stack_info = self.redact(record.stack_info)
        # Structured `extra` attributes (including nested containers) are attached after
        # the record factory runs; sweep every remaining attribute so a formatter that
        # renders them cannot emit a raw credential.
        for key, value in list(record.__dict__.items()):
            if key in _SKIP_ATTRIBUTES:
                continue
            changed, scrubbed = self._redact_value(value)
            if changed:
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
