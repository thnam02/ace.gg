from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services.feature_engine_service import FeatureEngineService
from tests.factories import seed_match_graph
from tests.test_stats_engine_service import _add_second_map


def test_feature_service_for_player(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    _add_second_map(db_session, graph)

    features = FeatureEngineService(db_session).for_player(graph["player"].id)

    assert features.player_id == str(graph["player"].id)
    assert features.aggregate.kpr == pytest.approx(38 / 45)
    assert features.aggregate.adr is not None
    assert features.aggregate.expected_adr is not None
    assert features.aggregate.clutch_attempts == 5
    assert len(features.maps) == 2


def test_feature_service_trains_from_reference_population(db_session: Session) -> None:
    graph = seed_match_graph(db_session)
    service = FeatureEngineService(db_session)

    adr_model = service.train_adr_model()
    clutch_prior = service.estimate_clutch_prior()

    assert adr_model.sample_count >= 1
    assert clutch_prior.alpha > 0
    assert clutch_prior.beta > 0

    map_features = service.for_player_map_stats(graph["stats"])
    assert map_features.kpr == pytest.approx(18 / 21)
    assert map_features.residual_adr is not None
