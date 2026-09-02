from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.providers.vlrggapi_errors import (
    VlrggApiHttpError,
    VlrggApiMalformedResponseError,
    VlrggApiStatusError,
)

_RETRYABLE_STATUS_CODES = {429, 503}


class VlrggApiClient:
    """HTTP client for a self-hosted vlrggapi instance."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        request_delay: float = 0.0,
        max_retries: int = 6,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client or httpx.Client(base_url=self._base_url, timeout=timeout)
        self._request_delay = request_delay
        self._max_retries = max_retries
        self.http_429_count = 0
        self._cooldown_until = 0.0

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
        last_error: VlrggApiHttpError | None = None
        for attempt in range(self._max_retries + 1):
            cooldown = self._cooldown_until - time.time()
            if cooldown > 0:
                time.sleep(cooldown)
            try:
                response = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise VlrggApiHttpError(0, path, str(exc)) from exc

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                if response.status_code == 429:
                    self.http_429_count += 1
                last_error = VlrggApiHttpError(response.status_code, path)
                delay = _retry_delay(response, attempt)
                if response.status_code == 429:
                    self._cooldown_until = time.time() + delay
                time.sleep(delay)
                continue

            if response.status_code == 429:
                self.http_429_count += 1
                self._cooldown_until = time.time() + _retry_delay(response, attempt)

            if response.status_code != 200:
                raise VlrggApiHttpError(response.status_code, path)

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise VlrggApiMalformedResponseError(path, "invalid JSON") from exc

            if not isinstance(payload, dict):
                raise VlrggApiMalformedResponseError(path, "expected object payload")

            if self._request_delay > 0:
                time.sleep(self._request_delay)
            return payload

        if last_error is not None:
            raise last_error
        raise VlrggApiHttpError(0, path, "request failed")

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


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), 120.0)
        except ValueError:
            pass
    delay = min(2.0**attempt, 90.0)
    if response.status_code == 429:
        return max(delay, 20.0)
    return delay
