from __future__ import annotations

from collections import Counter
from uuid import UUID

RANKING_REGIONS: tuple[str, ...] = ("Americas", "EMEA", "Pacific", "China", "INTL")
LEAGUE_REGIONS: tuple[str, ...] = ("Americas", "EMEA", "Pacific", "China")

_REGION_ALIASES: dict[str, str] = {
    "americas": "Americas",
    "na": "Americas",
    "br": "Americas",
    "sa": "Americas",
    "la": "Americas",
    "us": "Americas",
    "emea": "EMEA",
    "eu": "EMEA",
    "pacific": "Pacific",
    "ap": "Pacific",
    "apac": "Pacific",
    "kr": "Pacific",
    "oce": "Pacific",
    "sea": "Pacific",
    "china": "China",
    "cn": "China",
    "intl": "INTL",
    "international": "INTL",
}


def canonicalize_ranking_region(value: str | None) -> str | None:
    if not value:
        return None
    aliased = _REGION_ALIASES.get(value.strip().lower())
    if aliased is not None:
        return aliased
    return infer_ranking_region_from_text(value)


def infer_ranking_region_from_text(value: str) -> str | None:
    lowered = value.lower()
    if "north america" in lowered or "americas" in lowered:
        return "Americas"
    if "emea" in lowered or "europe" in lowered:
        return "EMEA"
    if "pacific" in lowered or "southeast asia" in lowered:
        return "Pacific"
    if "china" in lowered:
        return "China"
    if "masters" in lowered or "champions" in lowered:
        return "INTL"
    return None


def event_ranking_region(*, region: str | None, name: str | None) -> str | None:
    return canonicalize_ranking_region(region) or infer_ranking_region_from_text(name or "")


def pick_ranking_region(
    *,
    team_region: str | None,
    event_regions: list[str | None],
) -> str | None:
    canonical_events = [canonicalize_ranking_region(item) for item in event_regions if item]
    canonical_events = [item for item in canonical_events if item is not None]
    league = [item for item in canonical_events if item in LEAGUE_REGIONS]
    pool = league or canonical_events
    if pool:
        counts = Counter(pool)
        top_count = max(counts.values())
        tied = {region for region, count in counts.items() if count == top_count}
        for region in RANKING_REGIONS:
            if region in tied:
                return region
        return next(iter(tied))
    return canonicalize_ranking_region(team_region)


def snapshot_event_ids(details: dict[str, object] | None) -> list[UUID]:
    if not details:
        return []
    raw = details.get("event_ids")
    if not isinstance(raw, list):
        return []
    ids: list[UUID] = []
    for value in raw:
        try:
            ids.append(UUID(str(value)))
        except ValueError:
            continue
    return ids
