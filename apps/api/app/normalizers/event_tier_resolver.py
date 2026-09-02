from __future__ import annotations

from enum import StrEnum


class EventTier(StrEnum):
    T1 = "T1"
    T2 = "T2"
    OTHER = "Other"
    UNKNOWN = "Unknown"


class EventTierResolver:
    """Resolve VLR event tier from metadata using explicit keyword rules."""

    T1_KEYWORDS: tuple[str, ...] = (
        "champions",
        "masters",
        "lock//in",
        "lock in",
        "world championship",
    )
    T2_KEYWORDS: tuple[str, ...] = (
        "challengers",
        "ascension",
        "qualifier",
        "last chance",
        "lcq",
    )
    OTHER_KEYWORDS: tuple[str, ...] = (
        "game changers",
        "off-season",
        "offseason",
        "showmatch",
    )

    def resolve(
        self,
        *,
        name: str,
        series: str | None = None,
        explicit_tier: str | None = None,
    ) -> EventTier:
        if explicit_tier:
            normalized = explicit_tier.strip().upper()
            if normalized in {"S", "T1", "1"}:
                return EventTier.T1
            if normalized in {"A", "T2", "2"}:
                return EventTier.T2
            if normalized in {"B", "C", "OTHER"}:
                return EventTier.OTHER

        combined = " ".join(part for part in (name, series or "") if part).lower()
        if not combined.strip():
            return EventTier.UNKNOWN

        if any(keyword in combined for keyword in self.T1_KEYWORDS):
            return EventTier.T1
        if any(keyword in combined for keyword in self.T2_KEYWORDS):
            return EventTier.T2
        if any(keyword in combined for keyword in self.OTHER_KEYWORDS):
            return EventTier.OTHER

        if "stage" in combined and "champions tour" in combined:
            return EventTier.T2

        return EventTier.UNKNOWN
