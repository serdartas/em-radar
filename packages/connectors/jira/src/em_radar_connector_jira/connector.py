from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from typing import ClassVar, cast

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl, SecretStr, ValidationError

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorAuthError,
    ConnectorConfigError,
    ConnectorDataError,
    ConnectorNotFoundError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
)

CLIENT_FACTORY: Callable[..., httpx.AsyncClient] = httpx.AsyncClient


class JiraConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: HttpUrl
    token: SecretStr
    auth_email: str | None = None
    verify_tls: bool = True


class JiraConnector:
    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira (Cloud or Server)"
    config_schema: ClassVar[dict[str, object]] = JiraConnectorConfig.model_json_schema()
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        try:
            self.config = JiraConnectorConfig.model_validate(config)
        except ValidationError as error:
            raise ConnectorConfigError("Invalid Jira connector config") from error

        self._client = CLIENT_FACTORY(
            base_url=str(self.config.base_url),
            headers={"Authorization": _authorization_header(self.config)},
            verify=self.config.verify_tls,
        )

    async def test_connection(self) -> ConnectionTestResult:
        user_payload = await self._request_json("rest/api/2/myself")
        permissions_payload = await self._request_json("rest/api/2/mypermissions")
        return ConnectionTestResult(
            ok=True,
            detail="Connected to Jira",
            user_display_name=_display_name(user_payload),
            permissions=_permissions(permissions_payload),
        )

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(
            provides_workitems=False,
            provides_sprints=False,
            provides_transitions=False,
            supports_incremental_fetch=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request_json(self, path: str) -> dict[str, object]:
        try:
            response = await self._client.get(path)
        except httpx.RequestError as error:
            raise ConnectorTransientError("Failed to reach Jira") from error

        if response.status_code >= 400:
            raise _error_for_status(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise ConnectorDataError("Jira returned invalid JSON") from error

        if not isinstance(payload, dict):
            raise ConnectorDataError("Jira returned an unexpected payload shape")
        return cast(dict[str, object], payload)


def _authorization_header(config: JiraConnectorConfig) -> str:
    token = config.token.get_secret_value()
    username = config.auth_email if config.auth_email is not None else token
    secret = f"{username}:{token if config.auth_email is not None else ''}".encode("utf-8")
    encoded = base64.b64encode(secret).decode("ascii")
    return f"Basic {encoded}"


def _display_name(payload: Mapping[str, object]) -> str | None:
    for key in ("displayName", "name", "accountId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _permissions(payload: Mapping[str, object]) -> list[str]:
    raw_permissions = payload.get("permissions")
    if not isinstance(raw_permissions, Mapping):
        return []

    permissions = [str(name) for name, value in raw_permissions.items() if _has_permission(value)]
    return sorted(permissions)


def _has_permission(value: object) -> bool:
    if isinstance(value, Mapping):
        candidate = value.get("havePermission")
        return isinstance(candidate, bool) and candidate
    return isinstance(value, bool) and value


def _error_for_status(
    status_code: int,
) -> (
    ConnectorAuthError
    | ConnectorNotFoundError
    | ConnectorRateLimitedError
    | ConnectorTransientError
    | ConnectorDataError
):
    if status_code in (401, 403):
        return ConnectorAuthError("Jira authentication failed")
    if status_code == 404:
        return ConnectorNotFoundError("Jira endpoint was not found")
    if status_code == 429:
        return ConnectorRateLimitedError("Jira rate limit exceeded")
    if status_code >= 500:
        return ConnectorTransientError(f"Jira server error ({status_code})")
    return ConnectorDataError(f"Jira request failed with status {status_code}")
