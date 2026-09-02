from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.metrics.team_elo import (
    DEFAULT_BASELINE_RATING,
    DEFAULT_K_FACTOR,
    expected_win_probability,
    update_rating,
)
from app.models import Match, PlayerMapStats, TeamRatingSnapshot
from app.schemas.team_rating import OpponentStrengthFeatures, TeamRatingRebuildSummary

SKIPPED_MATCH_STATUSES = frozenset({"cancelled", "unplayed"})


@dataclass(frozen=True)
class TeamRatingConfig:
    baseline_rating: float = DEFAULT_BASELINE_RATING
    k_factor: float = DEFAULT_K_FACTOR


class TeamRatingService:
    """Historical Elo ratings and pre-match opponent strength features."""

    def __init__(self, session: Session, *, config: TeamRatingConfig | None = None) -> None:
        self._session = session
        self._config = config or TeamRatingConfig()

    def rebuild_team_ratings(self) -> TeamRatingRebuildSummary:
        self._session.execute(delete(TeamRatingSnapshot))
        matches = self._load_ratable_matches()
        ratings: dict[UUID, float] = {}
        processed = 0
        skipped = 0
        snapshots_written = 0

        for match in matches:
            if not self._is_ratable_match(match):
                skipped += 1
                continue

            team_a_id = match.team_a_id
            team_b_id = match.team_b_id
            winner_id = match.winner_team_id
            assert team_a_id is not None
            assert team_b_id is not None
            assert winner_id is not None
            assert match.played_at is not None

            rating_a_before = self._rating_for_team(ratings, team_a_id)
            rating_b_before = self._rating_for_team(ratings, team_b_id)

            expected_a = expected_win_probability(rating_a_before, rating_b_before)
            expected_b = 1.0 - expected_a

            score_a = 1.0 if winner_id == team_a_id else 0.0
            score_b = 1.0 if winner_id == team_b_id else 0.0

            rating_a_after = update_rating(
                rating_a_before,
                score_a,
                expected_a,
                self._config.k_factor,
            )
            rating_b_after = update_rating(
                rating_b_before,
                score_b,
                expected_b,
                self._config.k_factor,
            )

            self._session.add_all(
                [
                    TeamRatingSnapshot(
                        team_id=team_a_id,
                        match_id=match.id,
                        opponent_team_id=team_b_id,
                        rating_before=rating_a_before,
                        rating_after=rating_a_after,
                        opponent_rating_before=rating_b_before,
                        expected_win_probability=expected_a,
                        result=int(score_a),
                        effective_at=match.played_at,
                    ),
                    TeamRatingSnapshot(
                        team_id=team_b_id,
                        match_id=match.id,
                        opponent_team_id=team_a_id,
                        rating_before=rating_b_before,
                        rating_after=rating_b_after,
                        opponent_rating_before=rating_a_before,
                        expected_win_probability=expected_b,
                        result=int(score_b),
                        effective_at=match.played_at,
                    ),
                ]
            )

            ratings[team_a_id] = rating_a_after
            ratings[team_b_id] = rating_b_after
            processed += 1
            snapshots_written += 2

        self._session.flush()
        return TeamRatingRebuildSummary(
            matches_processed=processed,
            matches_skipped=skipped,
            snapshots_written=snapshots_written,
        )

    def get_opponent_strength_for_match_team(
        self,
        match_id: UUID,
        team_id: UUID,
    ) -> OpponentStrengthFeatures:
        snapshot = self._session.scalar(
            select(TeamRatingSnapshot).where(
                TeamRatingSnapshot.match_id == match_id,
                TeamRatingSnapshot.team_id == team_id,
            )
        )
        if snapshot is None:
            return OpponentStrengthFeatures()
        return OpponentStrengthFeatures(
            team_rating_pre_match=snapshot.rating_before,
            opponent_rating_pre_match=snapshot.opponent_rating_before,
            expected_team_win_probability=snapshot.expected_win_probability,
        )

    def get_opponent_strength_for_player_map_stats(
        self,
        stats: PlayerMapStats,
    ) -> OpponentStrengthFeatures:
        return self.get_opponent_strength_for_match_team(
            stats.match_map.match_id,
            stats.team_id,
        )

    def get_snapshot(
        self,
        match_id: UUID,
        team_id: UUID,
    ) -> TeamRatingSnapshot | None:
        return self._session.scalar(
            select(TeamRatingSnapshot).where(
                TeamRatingSnapshot.match_id == match_id,
                TeamRatingSnapshot.team_id == team_id,
            )
        )

    def _rating_for_team(self, ratings: dict[UUID, float], team_id: UUID) -> float:
        return ratings.get(team_id, self._config.baseline_rating)

    def _load_ratable_matches(self) -> list[Match]:
        query = (
            select(Match)
            .order_by(Match.played_at.asc().nulls_last(), Match.vlr_match_id, Match.id)
        )
        return list(self._session.scalars(query).all())

    def _is_ratable_match(self, match: Match) -> bool:
        if match.played_at is None:
            return False
        if match.status in SKIPPED_MATCH_STATUSES:
            return False
        if match.team_a_id is None or match.team_b_id is None:
            return False
        if match.winner_team_id is None:
            return False
        if match.winner_team_id not in {match.team_a_id, match.team_b_id}:
            return False
        return True
