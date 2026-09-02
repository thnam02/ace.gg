from __future__ import annotations

import httpx

from app.config import settings


class VctCircuitProvider:
    """Fetch the official VLR /vct circuit page. Isolated discovery adapter."""

    def __init__(
        self,
        *,
        url: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = (url or settings.vlr_circuit_url).rstrip("/")
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "VALORANT-Scout/1.0 (VCT circuit discovery)"},
            follow_redirects=True,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_page(self, *, season_year: int | None = None) -> str:
        params = {"year": season_year} if season_year is not None else None
        response = self._client.get(self._url, params=params)
        response.raise_for_status()
        return response.text


class StaticVctCircuitProvider:
    """In-memory /vct HTML for tests."""

    def __init__(self, html: str) -> None:
        self._html = html

    def close(self) -> None:
        return None

    def fetch_page(self, *, season_year: int | None = None) -> str:
        del season_year
        return self._html
