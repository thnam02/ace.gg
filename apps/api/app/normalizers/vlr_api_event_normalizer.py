from __future__ import annotations

from typing import Any

from app.normalizers.event_tier_resolver import EventTierResolver
from app.normalizers.vlr_api_parsing import (
    as_dict,
    as_list,
    country_to_region,
    event_match_entries,
    parse_date_range_text,
    parse_vlr_id,
    team_tag_from_name,
)
from app.schemas.ingestion import NormalizedEvent, NormalizedEventPageData, NormalizedTeam


class VlrApiEventNormalizer:
    """Convert vlrggapi event JSON into canonical ingestion DTOs."""

    def __init__(self, tier_resolver: EventTierResolver | None = None) -> None:
        self._tier_resolver = tier_resolver or EventTierResolver()

    def normalize_event_page(
        self,
        event_id: int,
        event_data: dict[str, Any],
        event_matches_data: dict[str, Any] | None = None,
    ) -> NormalizedEventPageData:
        segments = as_dict(event_data.get("segments"))
        event_info = as_dict(segments.get("event"))

        name = str(event_info.get("name") or f"Event {event_id}")
        series = str(event_info.get("series") or "")
        start_date, end_date = parse_date_range_text(str(event_info.get("dates") or ""))
        location = str(event_info.get("location") or "")
        region = country_to_region(location) or _region_from_location_text(location)
        tier = self._tier_resolver.resolve(
            name=name,
            series=series,
            explicit_tier=str(event_info.get("tier") or "") or None,
        ).value

        event = NormalizedEvent(
            vlr_event_id=event_id,
            name=name,
            region=region,
            tier=tier,
            start_date=start_date,
            end_date=end_date,
            season_year=end_date.year if end_date else start_date.year if start_date else None,
            status=_event_status(event_matches_data),
        )

        teams = self._normalize_teams(segments)
        match_ids = self._discover_match_ids(event_matches_data)

        return NormalizedEventPageData(
            event=event,
            participating_teams=teams,
            match_ids=match_ids,
        )

    def _normalize_teams(self, segments: dict[str, Any]) -> list[NormalizedTeam]:
        teams: list[NormalizedTeam] = []
        seen: set[int] = set()
        sources = as_list(segments.get("teams"))
        for prize in as_list(segments.get("prizes")):
            team_row = as_dict(as_dict(prize).get("team"))
            if team_row:
                sources.append(team_row)
        for entry in sources:
            row = as_dict(entry)
            team_id = parse_vlr_id(row.get("id"))
            name = str(row.get("name") or "").strip()
            if team_id is None or not name or team_id in seen:
                continue
            seen.add(team_id)
            teams.append(
                NormalizedTeam(
                    vlr_team_id=team_id,
                    name=name,
                    tag=team_tag_from_name(name),
                    country=None,
                    region=None,
                )
            )
        return teams

    def _discover_match_ids(self, event_matches_data: dict[str, Any] | None) -> list[int]:
        if event_matches_data is None:
            return []
        discovered: list[int] = []
        seen: set[int] = set()
        for entry in event_match_entries(event_matches_data):
            row = as_dict(entry)
            match_id = parse_vlr_id(row.get("match_id"))
            if match_id is None or match_id in seen:
                continue
            seen.add(match_id)
            discovered.append(match_id)
        return discovered


def _event_status(event_matches_data: dict[str, Any] | None) -> str | None:
    if event_matches_data is None:
        return None
    matches = event_match_entries(event_matches_data)
    if not matches:
        return None
    return "completed"


def _region_from_location_text(location: str) -> str | None:
    lowered = location.lower()
    for keyword, region in (
        ("north america", "NA"),
        ("south america", "SA"),
        ("europe", "EU"),
        ("korea", "KR"),
        ("asia", "AP"),
        ("oceania", "OCE"),
        ("china", "CN"),
    ):
        if keyword in lowered:
            return region
    return None
