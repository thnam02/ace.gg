from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.metrics.cir.config import CIR_V02_VERSION, SHRINKAGE_K
from app.metrics.cir.ranking_explore import event_ranking_region
from app.metrics.cir.scope import ScopeType, event_scope_id
from app.metrics.cir.scoring import CirPlayerScore, aggregate_player_scores
from app.metrics.derived import aggregate_raw, compute_derived, safe_ratio, weighted_average
from app.metrics.stats_engine import player_map_stats_to_raw
from app.models import Event, PlayerMapStats, PlayerMetricScopedSnapshot
from app.schemas.vct_circuit import EventStatus
from app.services.cir_snapshot_service import (
    FrozenCirV02,
    load_eligible_player_map_stats,
    load_frozen_cir_v02,
    score_stats_with_frozen,
)


@dataclass(frozen=True)
class EventScopedPlayerBundle:
    score: CirPlayerScore
    maps_rows: list[PlayerMapStats]
    acs: float | None
    adr: float | None
    kd: float | None
    hs_pct: float | None
    apr: float | None
    kast: float | None
    opening_frequency: float | None
    opening_efficiency: float | None
    fk_per_round: float | None
    fd_per_round: float | None
    win_rate: float | None
    clutch: float | None
    matches: int


@dataclass
class EventCirBackfillResult:
    events_processed: int = 0
    players_scored: int = 0
    snapshots_upserted: int = 0
    snapshots_deleted: int = 0
    errors: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)


class EventCirSnapshotService:
    """Persist event-scoped CIR using frozen CIR v0.2 parameters.

    Observation window = eligible maps inside the selected event.
    Model definition (expectations, μ/σ, k=50, reference CDF) stays frozen.
    """

    def __init__(
        self,
        session: Session,
        *,
        require_complete_maps: bool = True,
    ) -> None:
        self._session = session
        self._require_complete_maps = require_complete_maps

    def score_event_bundles(
        self,
        frozen: FrozenCirV02,
        *,
        event_id: UUID,
        vlr_event_id: int | None = None,
    ) -> list[EventScopedPlayerBundle]:
        stats = load_eligible_player_map_stats(
            self._session,
            require_complete_maps=self._require_complete_maps,
            event_id=event_id,
            vlr_event_id=vlr_event_id,
        )
        maps = score_stats_with_frozen(stats, frozen)
        scores = aggregate_player_scores(
            maps,
            reference_mean=frozen.reference_mean,
            reference_population=frozen.reference_population,
            shrinkage_k=frozen.shrinkage_k,
        )
        by_player: dict[UUID, list[PlayerMapStats]] = defaultdict(list)
        for row in stats:
            by_player[row.player_id].append(row)

        bundles: list[EventScopedPlayerBundle] = []
        for score in scores:
            rows = by_player.get(score.player_id, [])
            if not rows:
                continue
            bundles.append(_bundle_from_score_and_rows(score, rows))
        return bundles

    def upsert_event_snapshots(
        self,
        *,
        frozen: FrozenCirV02,
        event: Event,
        bundles: list[EventScopedPlayerBundle],
        force: bool = False,
    ) -> tuple[int, int]:
        """Upsert scoped snapshots for one event. Returns (upserted, deleted)."""
        del force  # upsert is always version-safe; force kept for CLI symmetry
        scope_type = ScopeType.EVENT.value
        scope_id = event_scope_id(event.id)
        calculated_at = datetime.now(tz=UTC)
        player_ids = {bundle.score.player_id for bundle in bundles}

        existing = list(
            self._session.scalars(
                select(PlayerMetricScopedSnapshot.player_id).where(
                    PlayerMetricScopedSnapshot.metric_version_id == frozen.metric_version.id,
                    PlayerMetricScopedSnapshot.scope_type == scope_type,
                    PlayerMetricScopedSnapshot.scope_id == scope_id,
                )
            ).all()
        )
        stale = [player_id for player_id in existing if player_id not in player_ids]
        deleted = 0
        if stale:
            result = self._session.execute(
                delete(PlayerMetricScopedSnapshot).where(
                    PlayerMetricScopedSnapshot.metric_version_id == frozen.metric_version.id,
                    PlayerMetricScopedSnapshot.scope_type == scope_type,
                    PlayerMetricScopedSnapshot.scope_id == scope_id,
                    PlayerMetricScopedSnapshot.player_id.in_(stale),
                )
            )
            deleted = int(result.rowcount or 0)

        upserted = 0
        for bundle in bundles:
            payload = _scoped_snapshot_values(
                metric_version_id=frozen.metric_version.id,
                scope_type=scope_type,
                scope_id=scope_id,
                bundle=bundle,
                calculated_at=calculated_at,
            )
            payload["id"] = uuid4()
            statement = insert(PlayerMetricScopedSnapshot).values(**payload)
            update_fields = {
                key: statement.excluded[key]
                for key in payload
                if key
                not in {
                    "id",
                    "player_id",
                    "metric_version_id",
                    "scope_type",
                    "scope_id",
                }
            }
            statement = statement.on_conflict_do_update(
                constraint="uq_player_metric_scoped_snapshots_version_player_scope",
                set_=update_fields,
            )
            self._session.execute(statement)
            upserted += 1
        self._session.flush()
        return upserted, deleted

    def refresh_event(
        self,
        event: Event,
        *,
        version: str = CIR_V02_VERSION,
        dry_run: bool = False,
        force: bool = False,
    ) -> tuple[list[EventScopedPlayerBundle], int, int]:
        frozen = load_frozen_cir_v02(self._session, version=version)
        if frozen is None:
            raise ValueError(f"No frozen CIR MetricVersion {version}")
        bundles = self.score_event_bundles(
            frozen,
            event_id=event.id,
            vlr_event_id=event.vlr_event_id,
        )
        if dry_run:
            return bundles, 0, 0
        upserted, deleted = self.upsert_event_snapshots(
            frozen=frozen,
            event=event,
            bundles=bundles,
            force=force,
        )
        return bundles, upserted, deleted

    def refresh_events(
        self,
        events: list[Event],
        *,
        version: str = CIR_V02_VERSION,
        dry_run: bool = False,
        force: bool = False,
    ) -> EventCirBackfillResult:
        result = EventCirBackfillResult()
        for event in events:
            try:
                bundles, upserted, deleted = self.refresh_event(
                    event,
                    version=version,
                    dry_run=dry_run,
                    force=force,
                )
            except Exception as exc:  # noqa: BLE001 — collect per-event errors for CLI
                result.errors.append(f"{event.id}: {exc}")
                continue
            result.events_processed += 1
            result.players_scored += len(bundles)
            result.snapshots_upserted += upserted
            result.snapshots_deleted += deleted
            result.event_ids.append(str(event.id))
        return result

    def list_backfill_events(
        self,
        *,
        year: int | None = None,
        event_id: UUID | None = None,
        tier: str | None = None,
        region: str | None = None,
    ) -> list[Event]:
        rows = list(self._session.scalars(select(Event)).all())
        selected: list[Event] = []
        for event in rows:
            if event_id is not None and event.id != event_id:
                continue
            if year is not None and event.season_year != year:
                continue
            if tier and (event.tier or "").upper() != tier.upper():
                continue
            if region:
                canonical = event_ranking_region(region=event.region, name=event.name)
                if (canonical or "").lower() != region.lower() and (
                    event.region or ""
                ).lower() != region.lower():
                    continue
            status = (event.status or "").upper()
            if status == EventStatus.UPCOMING.value:
                continue
            if status and status not in {
                EventStatus.COMPLETED.value,
                EventStatus.ONGOING.value,
            }:
                continue
            selected.append(event)
        selected.sort(key=lambda item: (item.start_date or date.min, item.name))
        return selected


def _bundle_from_score_and_rows(
    score: CirPlayerScore,
    rows: list[PlayerMapStats],
) -> EventScopedPlayerBundle:
    raw_rows = [player_map_stats_to_raw(row) for row in rows]
    aggregated = aggregate_raw(raw_rows)
    derived = compute_derived(aggregated)
    kills = aggregated.kills
    deaths = aggregated.deaths
    rounds = aggregated.rounds
    apr = safe_ratio(aggregated.assists, rounds)
    fk = safe_ratio(aggregated.first_kills, rounds)
    fd = safe_ratio(aggregated.first_deaths, rounds)
    opening_duels = aggregated.first_kills + aggregated.first_deaths
    opening_frequency = safe_ratio(opening_duels, rounds)
    opening_efficiency = (
        safe_ratio(aggregated.first_kills, opening_duels) if opening_duels > 0 else None
    )
    hs_pct = weighted_average(
        [(row.headshot_pct, row.rounds) for row in rows if row.headshot_pct is not None]
    )
    win_rate = _map_win_rate(rows)
    clutch = derived.raw_clutch_rate
    matches = len({row.match_map.match_id for row in rows})

    # CIR combat residuals stay from the frozen CIR path (score.*).
    # Descriptive rates use totals / round-weighted aggregates.
    return EventScopedPlayerBundle(
        score=score,
        maps_rows=rows,
        acs=aggregated.acs,
        adr=aggregated.adr,
        kd=_kill_death_ratio(kills, deaths),
        hs_pct=hs_pct,
        apr=apr if apr is not None else derived.apr,
        kast=aggregated.kast_pct,
        opening_frequency=(
            opening_frequency if opening_frequency is not None else derived.opening_frequency
        ),
        opening_efficiency=(
            opening_efficiency if opening_efficiency is not None else derived.opening_efficiency
        ),
        fk_per_round=fk if fk is not None else derived.fkpr,
        fd_per_round=fd if fd is not None else derived.fdpr,
        win_rate=win_rate,
        clutch=clutch,
        matches=matches,
    )


def _map_win_rate(rows: list[PlayerMapStats]) -> float | None:
    """Canonical win rate: maps won / maps played (same for global + event views)."""
    map_results: dict[UUID, bool | None] = {}
    for row in rows:
        match_map = row.match_map
        if match_map.id in map_results:
            continue
        if match_map.winner_team_id is None:
            map_results[match_map.id] = None
        else:
            map_results[match_map.id] = match_map.winner_team_id == row.team_id
    decided = [won for won in map_results.values() if won is not None]
    if not decided:
        return None
    return sum(1 for won in decided if won) / len(decided)


def _kill_death_ratio(kills: int, deaths: int) -> float | None:
    if deaths == 0:
        return float(kills) if kills else None
    return kills / deaths


def _scoped_snapshot_values(
    *,
    metric_version_id: UUID,
    scope_type: str,
    scope_id: str,
    bundle: EventScopedPlayerBundle,
    calculated_at: datetime,
) -> dict[str, Any]:
    score = bundle.score
    # Prefer totals-based KPR/DPR when available; fall back to CIR score weights.
    return {
        "player_id": score.player_id,
        "metric_version_id": metric_version_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "cir_percentile": score.cir,
        "raw_cir": score.raw_cir,
        "shrunk_raw_cir": score.shrunk_raw_cir,
        "combat_factor": score.combat_factor,
        "rounds": score.rounds,
        "maps": score.maps,
        "matches": bundle.matches,
        "sample_weight": score.sample_weight,
        "sample_status": score.sample_status,
        "reliability": score.reliability,
        "kpr": score.kpr,
        "dpr": score.dpr,
        "expected_kpr": score.expected_kpr,
        "expected_dpr": score.expected_dpr,
        "kpr_residual": score.kpr_residual,
        "negative_dpr_residual": score.negative_dpr_residual,
        "acs": bundle.acs,
        "adr": bundle.adr,
        "kd": bundle.kd,
        "hs_pct": bundle.hs_pct,
        "apr": bundle.apr,
        "kast": bundle.kast,
        "opening_frequency": bundle.opening_frequency,
        "opening_efficiency": bundle.opening_efficiency,
        "fk_per_round": bundle.fk_per_round,
        "fd_per_round": bundle.fd_per_round,
        "win_rate": bundle.win_rate,
        "clutch": bundle.clutch,
        "role": score.role,
        "tier": score.tier,
        "primary_agent": score.primary_agent,
        "calculated_at": calculated_at,
    }


# Re-export for tests that assert shrinkage k.
EVENT_SHRINKAGE_K = SHRINKAGE_K
