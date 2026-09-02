from __future__ import annotations

from app.normalizers.vct_circuit import parse_vct_circuit_page
from app.providers.vct_circuit_provider import StaticVctCircuitProvider, VctCircuitProvider
from app.schemas.vct_circuit import VctDiscoveredEvent

VctCircuitProviderLike = VctCircuitProvider | StaticVctCircuitProvider


class VctCircuitDiscoveryService:
    """Canonical VCT circuit membership comes from /vct, not a hard-coded ID list."""

    def __init__(
        self,
        provider: VctCircuitProviderLike | None = None,
        *,
        season_year: int = 2026,
    ) -> None:
        self._provider = provider or VctCircuitProvider()
        self._season_year = season_year

    def discover(self, *, html: str | None = None) -> list[VctDiscoveredEvent]:
        if html is not None:
            page = html
        else:
            page = self._provider.fetch_page(season_year=self._season_year)
        return parse_vct_circuit_page(page, season_year=self._season_year)
