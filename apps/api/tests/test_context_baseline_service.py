from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.metrics.context_baselines import BaselineThresholds
from app.services.context_baseline_service import ContextBaselineService
from tests.factories import seed_match_graph
from tests.test_stats_engine_service import _add_second_map


def test_context_baseline_service_for_player_map(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    _add_second_map(db_session, graph)
    service = ContextBaselineService(
        db_session,
        thresholds=BaselineThresholds(
            agent_map_tier_min_rounds=1,
            role_map_tier_min_rounds=1,
            role_tier_min_rounds=1,
            tier_min_rounds=1,
        ),
    )

    result = service.for_player_map_stats(graph["stats"])
    features = result.features

    assert features.kpr == pytest.approx(18 / 21)
    assert features.kpr_expected is not None
    assert features.kpr_residual is not None
    assert features.baseline_level is not None
    assert features.reference_rounds is not None
    assert features.reference_observations is not None


def test_context_baseline_service_for_player_maps(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    _add_second_map(db_session, graph)

    service = ContextBaselineService(
        db_session,
        thresholds=BaselineThresholds(
            agent_map_tier_min_rounds=1,
            role_map_tier_min_rounds=1,
            role_tier_min_rounds=1,
            tier_min_rounds=1,
        ),
    )

    result = service.for_player(graph["player"].id)
    assert result.player_id == str(graph["player"].id)
    assert len(result.maps) == 2
    assert all(item.features.kpr is not None for item in result.maps)
