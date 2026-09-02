from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.vlrggapi_errors import (
    VlrggApiHttpError,
    VlrggApiMalformedResponseError,
    VlrggApiStatusError,
)


class VlrggApiClient:
    """HTTP client for a self-hosted vlrggapi instance."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client or httpx.Client(base_url=self._base_url, timeout=timeout)

    @property
    def base_url(self) -> str:
        return self._base_url

    def close(self) -> None:
        self._client.close()

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise VlrggApiHttpError(0, path, str(exc)) from exc

        if response.status_code != 200:
            raise VlrggApiHttpError(response.status_code, path)

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise VlrggApiMalformedResponseError(path, "invalid JSON") from exc

        if not isinstance(payload, dict):
            raise VlrggApiMalformedResponseError(path, "expected object payload")

        return payload

    def get_data(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        payload = self.get_json(path, params=params)
        status = payload.get("status")
        if status != "success":
            raise VlrggApiStatusError(path, str(status))

        data = payload.get("data")
        if not isinstance(data, dict):
            raise VlrggApiMalformedResponseError(path, "expected data object")

        return data

    def get_data_optional(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any] | None:
        try:
            return self.get_data(path, params=params)
        except (VlrggApiHttpError, VlrggApiMalformedResponseError, VlrggApiStatusError):
            return None
