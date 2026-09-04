"""Generic metric observation scopes.

GLOBAL_2026 and EVENT are required for this phase. TIER/REGION are reserved
for future work — do not invent event-local CIR parameters when scoping.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ScopeType(StrEnum):
    GLOBAL_2026 = "GLOBAL_2026"
    EVENT = "EVENT"
    TIER = "TIER"
    REGION = "REGION"


@dataclass(frozen=True)
class MetricScope:
    scope_type: ScopeType
    scope_id: str | None = None
    season_year: int | None = None
    tier: str | None = None
    region: str | None = None
    label: str | None = None
    status: str | None = None

    @classmethod
    def global_2026(cls, *, label: str = "2026 CIR") -> MetricScope:
        return cls(
            scope_type=ScopeType.GLOBAL_2026,
            scope_id=None,
            season_year=2026,
            label=label,
        )

    @classmethod
    def for_event(
        cls,
        *,
        event_id: UUID | str,
        label: str,
        tier: str | None = None,
        region: str | None = None,
        status: str | None = None,
        season_year: int | None = None,
    ) -> MetricScope:
        return cls(
            scope_type=ScopeType.EVENT,
            scope_id=str(event_id),
            season_year=season_year,
            tier=tier,
            region=region,
            label=label,
            status=status,
        )


def event_scope_id(event_id: UUID | str) -> str:
    return str(event_id)
