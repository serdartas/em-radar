import logging
from collections.abc import Callable, Sequence

import httpx

_REDACTED = "[REDACTED]"
_UPSTREAM_RECORD_FACTORY: Callable[..., logging.LogRecord] | None = None


class _CredentialRedactionFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self._sensitive_values: set[str] = set()

    def add_sensitive_values(self, values: Sequence[str]) -> None:
        self._sensitive_values.update(value for value in values if value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for value in self._sensitive_values:
            redacted = redacted.replace(value, _REDACTED)
        if redacted != message:
            record.msg = redacted
            record.args = ()
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

    current_factory = logging.getLogRecordFactory()
    if current_factory is _redacting_record_factory:
        return
    _UPSTREAM_RECORD_FACTORY = current_factory
    logging.setLogRecordFactory(_redacting_record_factory)


def create_redacting_async_client(
    *,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    sensitive_values: Sequence[str] = (),
    **client_kwargs: object,
) -> httpx.AsyncClient:
    _CREDENTIAL_FILTER.add_sensitive_values(sensitive_values)
    _install_redacting_record_factory()
    return client_factory(**client_kwargs)


__all__ = ["create_redacting_async_client"]
