from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.metrics.cir.config import (
    CIR_NAME,
    CIR_V02_VERSION,
    LAMBDA,
    SHRINKAGE_K,
    TAU,
    MetricVersionStatus,
)
from app.metrics.cir.context import load_combat_registry
from app.metrics.cir.sanity import sanity_failures
from app.metrics.cir.scoring import (
    CirMapScore,
    CirPlayerScore,
    aggregate_player_scores,
    score_observation,
)
from app.metrics.cir_standardization import StandardizationParams
from app.metrics.context_v2 import ContextV2Registry
from app.models import (
    MetricVersion,
    PlayerMapStats,
    PlayerMetricSnapshot,
)
from app.parsers.agents import UNKNOWN_AGENT_NAME, is_known_agent
from app.services.context_baseline_service import observation_from_player_map_stats
from app.services.map_completeness import (
    filter_stats_to_complete_maps,
    summarize_map_completeness,
)
from app.services.stats_engine_service import StatsEngineService


@dataclass(frozen=True)
class FrozenCirV02:
    metric_version: MetricVersion
    registry: ContextV2Registry
    standardization: StandardizationParams
    reference_mean: float
    reference_population: list[float]
    shrinkage_k: float
    tau: float
    lambda_: float


def load_eligible_player_map_stats(
    session: Session,
    *,
    stats_service: StatsEngineService | None = None,
    require_complete_maps: bool = True,
) -> list[PlayerMapStats]:
    service = stats_service or StatsEngineService(session)
    all_stats = service.load_player_map_stats(None)
    if require_complete_maps:
        completeness = summarize_map_completeness(session)
        all_stats = filter_stats_to_complete_maps(all_stats, completeness.complete_map_ids)
    return _exclude_unknown_agent_maps(all_stats)


def load_frozen_cir_v02(
    session: Session,
    *,
    version: str = CIR_V02_VERSION,
) -> FrozenCirV02 | None:
    metric_version = session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_NAME,
            MetricVersion.version == version,
        )
    )
    if metric_version is None:
        return None
    params = metric_version.regularization_parameters or {}
    shrinkage = metric_version.shrinkage_parameters or {}
    reference = metric_version.reference_population or {}
    registry_payload = params.get("context_registry")
    if not isinstance(registry_payload, dict):
        return None
    std_payload = metric_version.standardization_parameters
    population = reference.get("shrunk_raw_cir_values") or []
    return FrozenCirV02(
        metric_version=metric_version,
        registry=load_combat_registry(registry_payload),
        standardization=StandardizationParams.from_dict(std_payload),
        reference_mean=float(shrinkage.get("reference_mean") or 0.0),
        reference_population=[float(value) for value in population],
        shrinkage_k=float(shrinkage.get("k") or SHRINKAGE_K),
        tau=float(params.get("tau") or TAU),
        lambda_=float(params.get("lambda") or LAMBDA),
    )


def production_metric_version(session: Session) -> MetricVersion | None:
    return session.scalar(
        select(MetricVersion)
        .where(
            MetricVersion.name == CIR_NAME,
            MetricVersion.status == MetricVersionStatus.PRODUCTION.value,
        )
        .order_by(MetricVersion.created_at.desc())
    )


class CirSnapshotService:
    """Score eligible players with a frozen MetricVersion. Does not refit parameters."""

    def __init__(
        self,
        session: Session,
        *,
        stats_service: StatsEngineService | None = None,
        require_complete_maps: bool = True,
    ) -> None:
        self._session = session
        self._stats_service = stats_service or StatsEngineService(session)
        self._require_complete_maps = require_complete_maps

    def score_maps(self, frozen: FrozenCirV02) -> list[CirMapScore]:
        stats = load_eligible_player_map_stats(
            self._session,
            stats_service=self._stats_service,
            require_complete_maps=self._require_complete_maps,
        )
        return score_stats_with_frozen(stats, frozen)

    def score_players(self, frozen: FrozenCirV02) -> list[CirPlayerScore]:
        maps = self.score_maps(frozen)
        return aggregate_player_scores(
            maps,
            reference_mean=frozen.reference_mean,
            reference_population=frozen.reference_population,
            shrinkage_k=frozen.shrinkage_k,
        )

    def upsert_snapshots(
        self,
        *,
        metric_version: MetricVersion,
        players: list[CirPlayerScore],
    ) -> None:
        calculated_at = datetime.now(tz=UTC)
        player_ids = {player.player_id for player in players}
        existing = list(
            self._session.scalars(
                select(PlayerMetricSnapshot.player_id).where(
                    PlayerMetricSnapshot.metric_version_id == metric_version.id
                )
            ).all()
        )
        stale = [player_id for player_id in existing if player_id not in player_ids]
        if stale:
            self._session.execute(
                delete(PlayerMetricSnapshot).where(
                    PlayerMetricSnapshot.metric_version_id == metric_version.id,
                    PlayerMetricSnapshot.player_id.in_(stale),
                )
            )
        for player in players:
            payload = _snapshot_values(metric_version.id, player, calculated_at)
            payload["id"] = uuid4()
            statement = insert(PlayerMetricSnapshot).values(**payload)
            update_fields = {
                key: statement.excluded[key]
                for key in payload
                if key not in {"id", "player_id", "metric_version_id"}
            }
            statement = statement.on_conflict_do_update(
                constraint="uq_player_metric_snapshots_player_id_metric_version_id",
                set_=update_fields,
            )
            self._session.execute(statement)
        self._session.flush()

    def refresh(
        self,
        *,
        version: str = CIR_V02_VERSION,
    ) -> tuple[FrozenCirV02, list[CirPlayerScore], list[str]]:
        frozen = load_frozen_cir_v02(self._session, version=version)
        if frozen is None:
            raise ValueError(f"No frozen CIR MetricVersion {version}")
        players = self.score_players(frozen)
        std = frozen.standardization
        params = frozen.metric_version.regularization_parameters or {}
        context_rows = params.get("context_expectations") or []
        failures = sanity_failures(
            players=players,
            standardization=std,
            reference_population=frozen.reference_population,
            context_rows=context_rows if isinstance(context_rows, list) else [],
        )
        self.upsert_snapshots(metric_version=frozen.metric_version, players=players)
        return frozen, players, failures


def score_stats_with_frozen(
    stats: list[PlayerMapStats],
    frozen: FrozenCirV02,
) -> list[CirMapScore]:
    scores: list[CirMapScore] = []
    for row in stats:
        if row.player is None or row.rounds <= 0:
            continue
        observation = observation_from_player_map_stats(row)
        match = row.match_map.match
        event = match.event
        scored = score_observation(
            observation,
            registry=frozen.registry,
            standardization=frozen.standardization,
            player_id=row.player_id,
            handle=row.player.handle,
            match_map_id=row.match_map_id,
            event_id=event.id if event is not None else None,
            vlr_event_id=event.vlr_event_id if event is not None else None,
            agent_name=row.agent.name if row.agent is not None else None,
            tau=frozen.tau,
        )
        if scored is not None:
            scores.append(scored)
    return scores


def _snapshot_values(
    metric_version_id: UUID,
    player: CirPlayerScore,
    calculated_at: datetime,
) -> dict[str, Any]:
    return {
        "player_id": player.player_id,
        "metric_version_id": metric_version_id,
        "raw_cir": player.raw_cir,
        "shrunk_raw_cir": player.shrunk_raw_cir,
        "cir": player.cir,
        "combat_component": player.combat_factor,
        "opening_component": None,
        "team_component": None,
        "clutch_component": None,
        "rounds": player.rounds,
        "maps_played": player.maps,
        "events_played": player.events,
        "sample_weight": player.sample_weight,
        "sample_status": player.sample_status,
        "reliability": player.reliability,
        "details": player.details(),
        "period_start": player.period_start,
        "period_end": player.period_end,
        "calculated_at": calculated_at,
    }


def _exclude_unknown_agent_maps(stats: list[PlayerMapStats]) -> list[PlayerMapStats]:
    unknown_map_ids: set[UUID] = set()
    for row in stats:
        agent_name = row.agent.name if row.agent is not None else UNKNOWN_AGENT_NAME
        if agent_name == UNKNOWN_AGENT_NAME or not is_known_agent(agent_name):
            unknown_map_ids.add(row.match_map_id)
    if not unknown_map_ids:
        return stats
    return [row for row in stats if row.match_map_id not in unknown_map_ids]
