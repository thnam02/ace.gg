from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metrics.team_elo import DEFAULT_BASELINE_RATING, DEFAULT_K_FACTOR, expected_win_probability
from app.models import Event, Match, Team, TeamRatingSnapshot
from app.services.team_rating_service import TeamRatingConfig, TeamRatingService
from tests.factories import seed_match_graph


def _add_match(
    session: Session,
    *,
    team_a: Team,
    team_b: Team,
    event_id,
    winner: Team,
    played_at: datetime,
    vlr_match_id: int,
    status: str = "completed",
) -> Match:
    match = Match(
        vlr_match_id=vlr_match_id,
        event_id=event_id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        winner_team_id=winner.id,
        played_at=played_at,
        status=status,
    )
    session.add(match)
    session.flush()
    return match


def test_first_match_uses_baseline_ratings(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    service = TeamRatingService(db_session)
    summary = service.rebuild_team_ratings()

    assert summary.matches_processed == 1
    assert summary.snapshots_written == 2

    snapshot = service.get_snapshot(graph["match"].id, graph["team_a"].id)
    assert snapshot is not None
    assert snapshot.rating_before == pytest.approx(DEFAULT_BASELINE_RATING)
    assert snapshot.opponent_rating_before == pytest.approx(DEFAULT_BASELINE_RATING)
    assert snapshot.expected_win_probability == pytest.approx(0.5)


def test_win_loss_elo_updates(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    service = TeamRatingService(db_session)
    service.rebuild_team_ratings()

    winner_snapshot = service.get_snapshot(graph["match"].id, graph["team_a"].id)
    loser_snapshot = service.get_snapshot(graph["match"].id, graph["team_b"].id)
    assert winner_snapshot is not None
    assert loser_snapshot is not None

    expected = expected_win_probability(
        DEFAULT_BASELINE_RATING,
        DEFAULT_BASELINE_RATING,
    )
    assert winner_snapshot.rating_after == pytest.approx(
        DEFAULT_BASELINE_RATING + DEFAULT_K_FACTOR * (1.0 - expected)
    )
    assert loser_snapshot.rating_after == pytest.approx(
        DEFAULT_BASELINE_RATING + DEFAULT_K_FACTOR * (0.0 - expected)
    )


def test_chronological_processing_uses_prior_match_ratings(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    team_a = graph["team_a"]
    team_b = graph["team_b"]
    event = graph["event"]

    _add_match(
        db_session,
        team_a=team_a,
        team_b=team_b,
        event_id=event.id,
        winner=team_a,
        played_at=datetime(2024, 8, 11, 18, 0, tzinfo=UTC),
        vlr_match_id=50002,
    )

    service = TeamRatingService(db_session)
    service.rebuild_team_ratings()

    first_snapshot = service.get_snapshot(graph["match"].id, team_a.id)
    second_match = db_session.scalar(select(Match).where(Match.vlr_match_id == 50002))
    assert first_snapshot is not None
    assert second_match is not None

    second_snapshot = service.get_snapshot(second_match.id, team_a.id)
    assert second_snapshot is not None
    assert second_snapshot.rating_before == pytest.approx(first_snapshot.rating_after)


def test_no_future_leakage_in_pre_match_ratings(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    team_a = graph["team_a"]
    team_b = graph["team_b"]
    event = graph["event"]

    early_match = graph["match"]
    late_match = _add_match(
        db_session,
        team_a=team_a,
        team_b=team_b,
        event_id=event.id,
        winner=team_b,
        played_at=datetime(2024, 8, 20, 18, 0, tzinfo=UTC),
        vlr_match_id=50003,
    )

    service = TeamRatingService(db_session)
    service.rebuild_team_ratings()

    early_snapshot = service.get_snapshot(early_match.id, team_a.id)
    late_snapshot = service.get_snapshot(late_match.id, team_a.id)
    assert early_snapshot is not None
    assert late_snapshot is not None

    assert early_snapshot.rating_before == pytest.approx(DEFAULT_BASELINE_RATING)
    assert late_snapshot.rating_before == pytest.approx(early_snapshot.rating_after)


def test_deterministic_rebuild_produces_identical_ratings(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    service = TeamRatingService(db_session)

    service.rebuild_team_ratings()
    first_after = service.get_snapshot(graph["match"].id, graph["team_a"].id).rating_after

    service.rebuild_team_ratings()
    second_after = service.get_snapshot(graph["match"].id, graph["team_a"].id).rating_after

    assert first_after == pytest.approx(second_after)


def test_rebuild_is_idempotent(db_session: Session) -> None:
    seed_match_graph(db_session)
    service = TeamRatingService(db_session)

    first = service.rebuild_team_ratings()
    count_after_first = db_session.scalar(select(func.count()).select_from(TeamRatingSnapshot))
    assert count_after_first == 2

    second = service.rebuild_team_ratings()
    count_after_second = db_session.scalar(select(func.count()).select_from(TeamRatingSnapshot))
    assert count_after_second == 2
    assert first.snapshots_written == second.snapshots_written


def test_skips_incomplete_matches(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    event = Event(
        vlr_event_id=7777,
        name="Skipped Event",
        start_date=date(2024, 9, 1),
        end_date=date(2024, 9, 30),
    )
    db_session.add(event)
    db_session.flush()

    db_session.add(
        Match(
            vlr_match_id=60001,
            event_id=event.id,
            team_a_id=graph["team_a"].id,
            team_b_id=graph["team_b"].id,
            winner_team_id=None,
            played_at=datetime(2024, 9, 5, 12, 0, tzinfo=UTC),
            status="completed",
        )
    )
    db_session.add(
        Match(
            vlr_match_id=60002,
            event_id=event.id,
            team_a_id=graph["team_a"].id,
            team_b_id=graph["team_b"].id,
            winner_team_id=graph["team_a"].id,
            played_at=None,
            status="completed",
        )
    )
    db_session.add(
        Match(
            vlr_match_id=60003,
            event_id=event.id,
            team_a_id=graph["team_a"].id,
            team_b_id=graph["team_b"].id,
            winner_team_id=graph["team_a"].id,
            played_at=datetime(2024, 9, 6, 12, 0, tzinfo=UTC),
            status="cancelled",
        )
    )
    db_session.flush()

    summary = TeamRatingService(db_session).rebuild_team_ratings()
    assert summary.matches_processed == 1
    assert summary.matches_skipped == 3


def test_same_timestamp_uses_secondary_ordering(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    team_a = graph["team_a"]
    team_b = graph["team_b"]
    event = graph["event"]
    played_at = datetime(2024, 8, 15, 12, 0, tzinfo=UTC)

    later_id_match = _add_match(
        db_session,
        team_a=team_a,
        team_b=team_b,
        event_id=event.id,
        winner=team_a,
        played_at=played_at,
        vlr_match_id=50010,
    )
    earlier_id_match = _add_match(
        db_session,
        team_a=team_a,
        team_b=team_b,
        event_id=event.id,
        winner=team_b,
        played_at=played_at,
        vlr_match_id=50009,
    )

    service = TeamRatingService(db_session)
    service.rebuild_team_ratings()

    first_processed = service.get_snapshot(graph["match"].id, team_a.id)
    second_processed = service.get_snapshot(earlier_id_match.id, team_a.id)
    third_processed = service.get_snapshot(later_id_match.id, team_a.id)
    assert first_processed is not None
    assert second_processed is not None
    assert third_processed is not None

    assert second_processed.rating_before == pytest.approx(first_processed.rating_after)
    assert third_processed.rating_before == pytest.approx(second_processed.rating_after)


def test_opponent_strength_for_player_map_stats(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    service = TeamRatingService(db_session)
    service.rebuild_team_ratings()

    strength = service.get_opponent_strength_for_player_map_stats(graph["stats"])
    assert strength.team_rating_pre_match == pytest.approx(DEFAULT_BASELINE_RATING)
    assert strength.opponent_rating_pre_match == pytest.approx(DEFAULT_BASELINE_RATING)
    assert strength.expected_team_win_probability == pytest.approx(0.5)


def test_new_team_joining_mid_season_starts_at_baseline(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    new_team = Team(vlr_team_id=9999, name="New Team", tag="NEW", country="US")
    db_session.add(new_team)
    db_session.flush()

    _add_match(
        db_session,
        team_a=graph["team_a"],
        team_b=new_team,
        event_id=graph["event"].id,
        winner=graph["team_a"],
        played_at=datetime(2024, 8, 12, 12, 0, tzinfo=UTC),
        vlr_match_id=50020,
    )

    service = TeamRatingService(db_session)
    service.rebuild_team_ratings()

    new_team_snapshot = service.get_snapshot(
        db_session.scalar(select(Match).where(Match.vlr_match_id == 50020)).id,
        new_team.id,
    )
    assert new_team_snapshot is not None
    assert new_team_snapshot.rating_before == pytest.approx(DEFAULT_BASELINE_RATING)


def test_custom_config_baseline_and_k_factor(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    config = TeamRatingConfig(baseline_rating=1400.0, k_factor=16.0)
    service = TeamRatingService(db_session, config=config)
    service.rebuild_team_ratings()

    snapshot = service.get_snapshot(graph["match"].id, graph["team_a"].id)
    assert snapshot is not None
    assert snapshot.rating_before == pytest.approx(1400.0)
    assert snapshot.rating_after == pytest.approx(1400.0 + 16.0 * 0.5)
