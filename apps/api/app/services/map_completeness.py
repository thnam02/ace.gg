from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MatchMap, PlayerMapStats

EXPECTED_PLAYERS_PER_MAP = 10


class MapCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    EMPTY = "EMPTY"


def is_played_map(match_map: MatchMap) -> bool:
    return match_map.team_a_score is not None and match_map.team_b_score is not None


def classify_player_stat_count(count: int) -> MapCompleteness:
    if count == 0:
        return MapCompleteness.EMPTY
    if count == EXPECTED_PLAYERS_PER_MAP:
        return MapCompleteness.COMPLETE
    return MapCompleteness.INCOMPLETE


@dataclass
class MapCompletenessSummary:
    maps_total: int = 0
    maps_played: int = 0
    maps_complete: int = 0
    maps_incomplete: int = 0
    maps_empty: int = 0
    complete_map_ids: set[UUID] = field(default_factory=set)
    incomplete_map_ids: set[UUID] = field(default_factory=set)
    empty_map_ids: set[UUID] = field(default_factory=set)

    @property
    def complete_map_pct(self) -> float:
        if self.maps_played == 0:
            return 0.0
        return 100.0 * self.maps_complete / self.maps_played

    @property
    def maps_used_for_cir(self) -> int:
        return self.maps_complete

    @property
    def maps_excluded_from_cir(self) -> int:
        return self.maps_incomplete + self.maps_empty


def summarize_map_completeness(session: Session) -> MapCompletenessSummary:
    counts: dict[UUID, int] = {
        match_map_id: int(count)
        for match_map_id, count in session.execute(
            select(PlayerMapStats.match_map_id, func.count()).group_by(PlayerMapStats.match_map_id)
        ).all()
    }
    maps = list(session.scalars(select(MatchMap)).all())
    summary = MapCompletenessSummary(maps_total=len(maps))
    for match_map in maps:
        if not is_played_map(match_map):
            continue
        summary.maps_played += 1
        count = int(counts.get(match_map.id, 0))
        classification = classify_player_stat_count(count)
        if classification is MapCompleteness.COMPLETE:
            summary.maps_complete += 1
            summary.complete_map_ids.add(match_map.id)
        elif classification is MapCompleteness.EMPTY:
            summary.maps_empty += 1
            summary.empty_map_ids.add(match_map.id)
        else:
            summary.maps_incomplete += 1
            summary.incomplete_map_ids.add(match_map.id)
    return summary


def complete_match_map_ids(session: Session) -> set[UUID]:
    return summarize_map_completeness(session).complete_map_ids


def filter_stats_to_complete_maps(
    stats: list[PlayerMapStats],
    complete_ids: set[UUID],
) -> list[PlayerMapStats]:
    return [row for row in stats if row.match_map_id in complete_ids]
