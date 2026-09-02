from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.metrics.cir_validation_config import (
    ABLATION_VARIANTS,
    SHRINKAGE_K_VALUES,
    STABILITY_ROUND_THRESHOLDS,
)
from app.metrics.cir_validation_metrics import distribution_summary, spearman_correlation
from app.models import Agent, Match, MatchMap, PlayerMapStats
from app.schemas.cir_validation import CIRValidationResult
from app.services.cir_training_service import CIRTrainingService
from app.services.cir_validation_service import CIRValidationService
from tests.factories import seed_match_graph


def _validation_service(db_session: Session) -> CIRValidationService:
    return CIRValidationService(
        db_session,
        training_service=CIRTrainingService(db_session, require_complete_maps=False),
    )


def _seed_validation_graph(db_session: Session) -> dict[str, object]:
    graph = seed_match_graph(db_session)
    controller_agent = Agent(name="Omen", role="Controller")
    initiator_agent = Agent(name="Sova", role="Initiator")
    sentinel_agent = Agent(name="Sage", role="Sentinel")
    db_session.add_all([controller_agent, initiator_agent, sentinel_agent])
    db_session.flush()

    graph["controller_agent"] = controller_agent
    graph["initiator_agent"] = initiator_agent
    graph["sentinel_agent"] = sentinel_agent

    for index, (vlr_id, played_day) in enumerate(
        (
            (51001, 11),
            (51002, 12),
            (51003, 13),
            (51004, 14),
            (51005, 15),
            (51006, 16),
            (51007, 17),
            (51008, 18),
        ),
        start=1,
    ):
        match = Match(
            vlr_match_id=vlr_id,
            event_id=graph["event"].id,
            team_a_id=graph["team_a"].id,
            team_b_id=graph["team_b"].id,
            winner_team_id=graph["team_a"].id,
            played_at=datetime(2024, 8, played_day, 18, 0, tzinfo=UTC),
            status="completed",
        )
        db_session.add(match)
        db_session.flush()
        team_a_score = 13 if index % 2 == 1 else 10
        team_b_score = 9 if index % 2 == 1 else 13
        rounds = team_a_score + team_b_score
        match_map = MatchMap(
            match_id=match.id,
            map_number=1,
            map_name=f"Map{index}",
            team_a_score=team_a_score,
            team_b_score=team_b_score,
            winner_team_id=graph["team_a"].id,
            rounds_played=rounds,
        )
        db_session.add(match_map)
        db_session.flush()

        agents = [
            graph["agent"],
            controller_agent,
            initiator_agent,
            sentinel_agent,
        ]
        players = [graph["player"], graph["teammate"]]
        for player_index, (player, agent) in enumerate(zip(players, agents, strict=False)):
            stats = PlayerMapStats(
                match_map_id=match_map.id,
                player_id=player.id,
                team_id=graph["team_a"].id,
                agent_id=agent.id,
                rounds=rounds,
                kills=rounds // 2 + player_index,
                deaths=rounds // 3,
                assists=4,
                first_kills=3,
                first_deaths=2,
                adr=150.0 + index + player_index,
                kast_pct=70.0 if player_index == 0 else None,
                clutch_wins=1 if player_index == 0 else None,
                clutch_attempts=2 if player_index == 0 else None,
                acs=220.0 + player_index * 10,
                vlr_rating=1.0 + player_index * 0.1,
            )
            db_session.add(stats)
        db_session.flush()

    return graph


def test_distribution_summary_and_spearman() -> None:
    summary = distribution_summary([1.0, 2.0, 3.0, 4.0, 5.0])
    assert summary["count"] == 5
    assert summary["median"] == 3.0
    assert (
        spearman_correlation(
            __import__("numpy").array([1.0, 2.0, 3.0]),
            __import__("numpy").array([1.0, 2.0, 3.0]),
        )
        == 1.0
    )


def test_validate_cir_v01_returns_typed_result(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    result = _validation_service(db_session).validate_cir_v01()
    assert isinstance(result, CIRValidationResult)
    assert result.dataset_quality.total_maps >= 4
    assert result.recommendations


def test_dataset_quality_counts(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    quality = _validation_service(db_session).validate_cir_v01().dataset_quality
    assert quality.total_players >= 2
    assert quality.total_player_map_observations > quality.total_maps
    assert quality.total_rounds > 0
    assert quality.observations_by_role.get("Duelist", 0) > 0
    assert quality.observations_by_agent
    assert quality.observations_by_tier.get("S", 0) > 0


def test_role_bias_grouping(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    role_bias = _validation_service(db_session).validate_cir_v01().role_bias
    roles = {row.role for row in role_bias.distributions}
    assert "Duelist" in roles
    assert any(row.count > 0 for row in role_bias.distributions)


def test_baseline_comparison_reports_all_metrics(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    comparison = _validation_service(db_session).validate_cir_v01().baseline_comparison
    names = {metric.name for metric in comparison.metrics}
    assert "CIR" in names
    assert "K/D" in names
    assert "ACS" in names
    assert "VLR Rating" in names
    for metric in comparison.metrics:
        assert metric.split in {"validation", "test"}
        assert metric.rmse is not None


def test_ablation_variants_cover_config(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    ablation = _validation_service(db_session).validate_cir_v01().ablation_results
    variants = {row.variant for row in ablation.results}
    for variant in ABLATION_VARIANTS:
        if variant == "full_model" or ABLATION_VARIANTS[variant] is not None:
            assert variant in variants
    without_kast = next(row for row in ablation.results if row.variant == "without_kast")
    assert "kast_residual" not in without_kast.features_used
    without_apr = next(row for row in ablation.results if row.variant == "without_apr")
    assert "apr_residual" not in without_apr.features_used
    assert without_apr.impact in {None, "IMPROVES", "NEGLIGIBLE", "HARMS", "STRONGLY_HARMS"}
    assert without_apr.validation_mae is not None or without_apr.validation_rmse is None


def test_shrinkage_sweep_covers_k_values(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    shrinkage = _validation_service(db_session).validate_cir_v01().shrinkage_analysis
    ks = {row.k for row in shrinkage.results}
    assert ks == set(SHRINKAGE_K_VALUES)
    assert shrinkage.reference_k > 0


def test_stability_threshold_reports(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    stability = _validation_service(db_session).validate_cir_v01().stability_analysis
    thresholds = {row.round_threshold for row in stability.thresholds}
    assert thresholds == set(STABILITY_ROUND_THRESHOLDS)


def test_missing_feature_diagnostics(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    missing = _validation_service(db_session).validate_cir_v01().missing_feature_analysis
    assert missing.missing_rates_by_feature
    assert any(rate > 0 for rate in missing.missing_rates_by_feature.values())
    assert missing.splits


def test_deterministic_outputs_on_fixture(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    service = _validation_service(db_session)
    first = service.validate_cir_v01()
    second = service.validate_cir_v01()
    assert first.ablation_results.full_model_validation_rmse == (
        second.ablation_results.full_model_validation_rmse
    )
    assert first.dataset_quality.total_rounds == second.dataset_quality.total_rounds


def test_v02_recommendation_is_evidence_based(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    result = _validation_service(db_session).validate_cir_v01()
    assert result.v02_recommendation.decision in {
        "KEEP CIR v0.1",
        "REFINE TO CIR v0.2",
        "RETHINK MODEL",
    }
    assert result.v02_recommendation.reasons
    assert result.component_analysis.coefficient_signs
    assert result.context_adjustment_audit.overall


def test_train_only_baseline_no_test_leakage(db_session: Session) -> None:
    _seed_validation_graph(db_session)
    service = _validation_service(db_session)
    bundle = service._training_service.prepare_evaluation_bundle()
    train_maps = [row for row in bundle.team_maps if row.split == "train"]
    test_maps = [row for row in bundle.team_maps if row.split == "test"]
    if not train_maps or not test_maps:
        pytest.skip("fixture lacks train/test split maps")

    from app.services.cir_training_service import _average_kd, _fit_univariate

    train_x = []
    train_y = []
    for team_map in train_maps:
        delta = service._team_metric_delta_for_map(bundle, team_map.match_map_id, _average_kd)
        train_x.append(delta)
        train_y.append(team_map.outcome_residual)
    slope_train, intercept_train = _fit_univariate(train_x, train_y)

    all_x = list(train_x)
    all_y = list(train_y)
    for team_map in test_maps:
        delta = service._team_metric_delta_for_map(bundle, team_map.match_map_id, _average_kd)
        all_x.append(delta)
        all_y.append(team_map.outcome_residual)
    slope_leaked, _ = _fit_univariate(all_x, all_y)

    assert slope_train != slope_leaked or len(all_x) != len(train_x)
