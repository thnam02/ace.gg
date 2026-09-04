from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.metrics.cir.config import (
    CIR_NAME,
    CIR_V02_VERSION,
    ESTABLISHED_ROUNDS,
    LOW_SAMPLE_ROUNDS,
    PUBLIC_DESCRIPTION,
    PUBLIC_INTERPRETATION,
    PUBLIC_TOOLTIP,
    SHRINKAGE_K,
    SampleStatus,
)
from app.metrics.cir.ranking_explore import (
    event_ranking_region,
    pick_ranking_region,
    snapshot_event_ids,
)
from app.metrics.cir.reliability import reliability_pct as reliability_pct_for_rounds
from app.metrics.cir.role_mix import build_role_mix
from app.metrics.cir.scope import ScopeType, event_scope_id
from app.models import (
    Agent,
    Event,
    Match,
    MatchMap,
    MetricVersion,
    Player,
    PlayerMapStats,
    PlayerMetricScopedSnapshot,
    PlayerMetricSnapshot,
    PlayerTeamHistory,
    Team,
)
from app.schemas.cir_ranking import (
    CirCompareEntry,
    CirCompareResponse,
    CirMetricMetadata,
    CirPlayerDetail,
    CirRankingPlayer,
    CirRankingResponse,
    PlayerOption,
    PlayerOptionsResponse,
    RankingScope,
)
from app.schemas.player_api import PlayerCompareCir, TeamRef
from app.schemas.vct_circuit import CircuitName, EventStatus
from app.services.cir_snapshot_service import load_frozen_cir_v02, production_metric_version
from app.services.event_cir_snapshot_service import EventCirSnapshotService, EventScopedPlayerBundle
from app.services.player_query import PlayerNotFoundError, PlayerQueryService
from app.services.vct_sync_service import latest_match_played_at, latest_sync_run

_EVENT_CIR_NOTE = (
    "Stats shown are calculated from this event only. "
    "CIR uses the frozen v0.2 reference population."
)
_NO_MAPS_NOTE = "No completed maps yet."
_EVENT_RANK_LABEL = "Event rank"

# Older clients used scope="season"; RankingScope is required by the new schema.
_GLOBAL_SCOPE = RankingScope(type="GLOBAL_2026", label="2026 CIR", season_year=2026)

_SORTABLE_FIELDS = frozenset(
    {
        "cir",
        "rounds",
        "maps",
        "kpr",
        "dpr",
        "acs",
        "adr",
        "kast",
        "opening_efficiency",
        "opening_frequency",
        "kd",
        "apr",
        "win_rate",
        "fk_per_round",
        "fd_per_round",
        "hs_pct",
    }
)


class CirRankingService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._players = PlayerQueryService(session)

    def resolve_metric_version(
        self,
        *,
        metric_version: str | None = None,
        metric_version_id: UUID | None = None,
    ) -> MetricVersion:
        if metric_version_id is not None:
            row = self._session.get(MetricVersion, metric_version_id)
            if row is None:
                raise ValueError("Metric version not found")
            return row
        if metric_version:
            row = self._session.scalar(
                select(MetricVersion).where(
                    MetricVersion.name == CIR_NAME,
                    MetricVersion.version == metric_version,
                )
            )
            if row is None:
                raise ValueError(f"Unknown CIR version {metric_version}")
            return row
        production = production_metric_version(self._session)
        if production is not None:
            return production
        frozen = load_frozen_cir_v02(self._session, version=CIR_V02_VERSION)
        if frozen is not None:
            return frozen.metric_version
        raise ValueError("No production CIR MetricVersion is available")

    def list_rankings(
        self,
        *,
        metric_version: str | None = None,
        role: str | None = None,
        tier: str | None = None,
        team: str | None = None,
        region: str | None = None,
        agent: str | None = None,
        event: str | None = None,
        min_rounds: int | None = None,
        include_provisional: bool = False,
        include_low_sample: bool = False,
        sample_status: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CirRankingResponse:
        version = self.resolve_metric_version(metric_version=metric_version)
        statuses = _allowed_statuses(
            include_provisional=include_provisional,
            include_low_sample=include_low_sample,
            sample_status=sample_status,
        )
        query = self._base_query(version.id).where(PlayerMetricSnapshot.sample_status.in_(statuses))
        if min_rounds is not None:
            query = query.where(PlayerMetricSnapshot.rounds >= min_rounds)
        if team:
            team_uuid = _as_uuid(team)
            if team_uuid is not None:
                query = query.where(Team.id == team_uuid)
            else:
                query = query.where(or_(Team.tag.ilike(team), Team.name.ilike(team)))
        if region:
            query = query.where(func.lower(Team.region) == region.lower())

        rows = list(self._session.execute(query).unique().all())
        filtered = [
            (snapshot, player, team_row)
            for snapshot, player, team_row in rows
            if _matches_details(snapshot, role=role, tier=tier, agent=agent, event=event)
        ]
        if search:
            filtered = [
                (snapshot, player, team_row)
                for snapshot, player, team_row in filtered
                if _matches_player_search(player, team_row, search)
            ]
        filtered.sort(key=_season_row_sort_key(sort=sort, order=order))
        total = len(filtered)
        page = filtered[offset : offset + limit]
        event_regions = self._event_region_lookup(page)
        role_counts = self._role_counts_lookup([player.id for _snapshot, player, _team in page])
        players = [
            _to_ranking_player(
                rank=offset + index + 1,
                snapshot=snapshot,
                player=player,
                team=team_row,
                version=version,
                event_regions=event_regions,
                role_counts=role_counts.get(player.id, {}),
            )
            for index, (snapshot, player, team_row) in enumerate(page)
        ]
        return CirRankingResponse(
            metric_name=version.name,
            metric_version=version.version,
            metric_version_id=str(version.id),
            total=total,
            limit=limit,
            offset=offset,
            players=players,
            scope=_GLOBAL_SCOPE,
            event_id=None,
            vlr_event_id=None,
            event_name=None,
            event_region=None,
            event_tier=None,
            event_status=None,
        )

    def list_event_rankings_by_id(
        self,
        event_id: str,
        *,
        role: str | None = None,
        tier: str | None = None,
        region: str | None = None,
        min_rounds: int | None = None,
        include_provisional: bool = True,
        include_low_sample: bool = True,
        sample_status: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        search: str | None = None,
        metric_version: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> CirRankingResponse:
        event_uuid = _as_uuid(event_id)
        if event_uuid is None:
            raise ValueError(f"Event {event_id} not found")
        event = self._session.get(Event, event_uuid)
        if event is None:
            raise ValueError(f"Event {event_id} not found")
        return self._list_event_rankings_for_event(
            event,
            role=role,
            tier=tier,
            region=region,
            min_rounds=min_rounds,
            include_provisional=include_provisional,
            include_low_sample=include_low_sample,
            sample_status=sample_status,
            sort=sort,
            order=order,
            search=search,
            metric_version=metric_version,
            limit=limit,
            offset=offset,
        )

    def list_event_rankings(
        self,
        *,
        vlr_event_id: int,
        role: str | None = None,
        tier: str | None = None,
        region: str | None = None,
        min_rounds: int | None = None,
        include_provisional: bool = True,
        include_low_sample: bool = True,
        sample_status: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        search: str | None = None,
        metric_version: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> CirRankingResponse:
        event = self._session.scalar(select(Event).where(Event.vlr_event_id == vlr_event_id))
        if event is None:
            raise ValueError(f"Event {vlr_event_id} not found")
        return self._list_event_rankings_for_event(
            event,
            role=role,
            tier=tier,
            region=region,
            min_rounds=min_rounds,
            include_provisional=include_provisional,
            include_low_sample=include_low_sample,
            sample_status=sample_status,
            sort=sort,
            order=order,
            search=search,
            metric_version=metric_version,
            limit=limit,
            offset=offset,
        )

    def _list_event_rankings_for_event(
        self,
        event: Event,
        *,
        role: str | None = None,
        tier: str | None = None,
        region: str | None = None,
        min_rounds: int | None = None,
        include_provisional: bool = True,
        include_low_sample: bool = True,
        sample_status: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        search: str | None = None,
        metric_version: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> CirRankingResponse:
        event_region = event_ranking_region(region=event.region, name=event.name)
        scope = _event_ranking_scope(event, event_region=event_region)

        frozen = load_frozen_cir_v02(
            self._session,
            version=metric_version or CIR_V02_VERSION,
        )
        if frozen is None:
            raise ValueError("No frozen CIR MetricVersion is available")
        version = frozen.metric_version

        if (event.status or "").upper() == EventStatus.UPCOMING.value:
            return CirRankingResponse(
                metric_name=version.name,
                metric_version=version.version,
                metric_version_id=str(version.id),
                total=0,
                limit=limit,
                offset=offset,
                players=[],
                scope=scope,
                event_id=str(event.id),
                vlr_event_id=event.vlr_event_id,
                event_name=event.name,
                event_region=event_region,
                event_tier=event.tier,
                event_status=event.status,
                note=_NO_MAPS_NOTE,
            )

        scoped_rows = self._load_event_scoped_rows(version.id, event.id)
        if scoped_rows:
            player_ids = [player.id for _snapshot, player, _team in scoped_rows]
            role_counts = self._role_counts_lookup(player_ids, event_id=event.id)
            candidates = [
                _to_scoped_ranking_player(
                    rank=0,
                    snapshot=snapshot,
                    player=player,
                    team=team_row,
                    version=version,
                    event_region=event_region,
                    role_counts=role_counts.get(player.id, {}),
                )
                for snapshot, player, team_row in scoped_rows
            ]
        else:
            bundles = EventCirSnapshotService(
                self._session,
                require_complete_maps=True,
            ).score_event_bundles(
                frozen,
                event_id=event.id,
                vlr_event_id=event.vlr_event_id,
            )
            players_by_id = self._players_by_ids([bundle.score.player_id for bundle in bundles])
            role_counts = self._role_counts_lookup(
                [bundle.score.player_id for bundle in bundles],
                event_id=event.id,
            )
            candidates = [
                _to_bundle_ranking_player(
                    rank=0,
                    bundle=bundle,
                    player=players_by_id.get(bundle.score.player_id),
                    version=version,
                    event_region=event_region,
                    role_counts=role_counts.get(bundle.score.player_id, {}),
                )
                for bundle in bundles
            ]

        statuses = set(
            _allowed_statuses(
                include_provisional=include_provisional,
                include_low_sample=include_low_sample,
                sample_status=sample_status,
            )
        )
        role_needle = role.lower() if role else None
        tier_needle = tier.lower() if tier else None
        region_needle = region.lower() if region else None

        filtered = [
            player
            for player in candidates
            if (player.sample_status in statuses)
            and (role_needle is None or (player.role or "").lower() == role_needle)
            and (tier_needle is None or (player.tier or "").lower() == tier_needle)
            and (min_rounds is None or player.rounds >= min_rounds)
            and (
                region_needle is None
                or (player.region or "").lower() == region_needle
            )
            and (search is None or _matches_ranking_player_search(player, search))
        ]
        filtered.sort(key=_ranking_player_sort_key(sort=sort, order=order))
        total = len(filtered)
        page = filtered[offset : offset + limit]
        players = [
            player.model_copy(update={"rank": offset + index + 1})
            for index, player in enumerate(page)
        ]
        return CirRankingResponse(
            metric_name=version.name,
            metric_version=version.version,
            metric_version_id=str(version.id),
            total=total,
            limit=limit,
            offset=offset,
            players=players,
            scope=scope,
            event_id=str(event.id),
            vlr_event_id=event.vlr_event_id,
            event_name=event.name,
            event_region=event_region,
            event_tier=event.tier,
            event_status=event.status,
            note=_EVENT_CIR_NOTE,
        )

    def player_cir(
        self,
        player_ref: str,
        *,
        metric_version: str | None = None,
        event_id: str | None = None,
    ) -> CirPlayerDetail:
        if event_id:
            return self._player_cir_for_event(
                player_ref,
                event_id=event_id,
                metric_version=metric_version,
            )
        player = self._players._require_player(player_ref)
        version = self.resolve_metric_version(metric_version=metric_version)
        snapshot = self._session.scalar(
            select(PlayerMetricSnapshot).where(
                PlayerMetricSnapshot.metric_version_id == version.id,
                PlayerMetricSnapshot.player_id == player.id,
            )
        )
        if snapshot is None:
            raise PlayerNotFoundError(player_ref)
        details = snapshot.details or {}
        identity = self._players._to_identity(player)
        ranks = self._rank_lookup(version.id)
        cir_role = _detail_str(details, "role")
        role_counts = self._role_counts_lookup([player.id]).get(player.id, {})
        return CirPlayerDetail(
            player_id=str(player.id),
            handle=player.handle,
            team=identity.team,
            role=cir_role,
            roles=build_role_mix(role_counts, cir_role),
            tier=_detail_str(details, "tier"),
            rank=ranks.get(player.id),
            established_count=len(ranks),
            cir=snapshot.cir,
            raw_cir=snapshot.raw_cir,
            shrunk_raw_cir=snapshot.shrunk_raw_cir,
            reliability=snapshot.reliability,
            reliability_pct=_detail_float(details, "reliability_pct"),
            sample_status=snapshot.sample_status,
            rounds=snapshot.rounds,
            maps=snapshot.maps_played,
            events=snapshot.events_played,
            combat_factor=snapshot.combat_component,
            kpr=_detail_float(details, "kpr"),
            dpr=_detail_float(details, "dpr"),
            expected_kpr=_detail_float(details, "expected_kpr"),
            expected_dpr=_detail_float(details, "expected_dpr"),
            kpr_residual=_detail_float(details, "kpr_residual"),
            negative_dpr_residual=_detail_float(details, "negative_dpr_residual"),
            sample_weight=snapshot.sample_weight,
            metric_version=version.version,
            metric_version_id=str(version.id),
            reference_period_start=(
                version.training_start.isoformat() if version.training_start else None
            ),
            reference_period_end=version.training_end.isoformat() if version.training_end else None,
            interpretation=PUBLIC_INTERPRETATION,
        )

    def _player_cir_for_event(
        self,
        player_ref: str,
        *,
        event_id: str,
        metric_version: str | None = None,
    ) -> CirPlayerDetail:
        player = self._players._require_player(player_ref)
        event_uuid = _as_uuid(event_id)
        if event_uuid is None:
            raise ValueError(f"Event {event_id} not found")
        event = self._session.get(Event, event_uuid)
        if event is None:
            raise ValueError(f"Event {event_id} not found")

        frozen = load_frozen_cir_v02(
            self._session,
            version=metric_version or CIR_V02_VERSION,
        )
        if frozen is None:
            raise ValueError("No frozen CIR MetricVersion is available")
        version = frozen.metric_version
        event_region = event_ranking_region(region=event.region, name=event.name)
        scope = _event_ranking_scope(event, event_region=event_region)

        if (event.status or "").upper() == EventStatus.UPCOMING.value:
            raise PlayerNotFoundError(player_ref)

        scoped_rows = self._load_event_scoped_rows(version.id, event.id)
        if scoped_rows:
            ranked = sorted(
                scoped_rows,
                key=lambda item: (
                    -(item[0].cir_percentile or 0.0),
                    -item[0].rounds,
                    item[1].handle.lower(),
                ),
            )
            event_player_count = len(ranked)
            player_row = next(
                (
                    (index, snapshot, row_player, team_row)
                    for index, (snapshot, row_player, team_row) in enumerate(ranked)
                    if row_player.id == player.id
                ),
                None,
            )
            if player_row is None:
                raise PlayerNotFoundError(player_ref)
            event_rank, snapshot, _row_player, team_row = player_row
            role_counts = self._role_counts_lookup(
                [player.id],
                event_id=event.id,
            ).get(player.id, {})
            identity_team = _team_ref(player, team_row)
            cir_role = snapshot.role
            return CirPlayerDetail(
                player_id=str(player.id),
                handle=player.handle,
                team=identity_team,
                role=cir_role,
                roles=build_role_mix(role_counts, cir_role),
                tier=snapshot.tier,
                event_rank=event_rank + 1,
                event_player_count=event_player_count,
                cir=snapshot.cir_percentile,
                raw_cir=snapshot.raw_cir,
                shrunk_raw_cir=snapshot.shrunk_raw_cir,
                reliability=snapshot.reliability,
                reliability_pct=reliability_pct_for_rounds(snapshot.rounds),
                sample_status=snapshot.sample_status,
                rounds=snapshot.rounds,
                maps=snapshot.maps,
                matches=snapshot.matches,
                events=1,
                combat_factor=snapshot.combat_factor,
                kpr=snapshot.kpr,
                dpr=snapshot.dpr,
                expected_kpr=snapshot.expected_kpr,
                expected_dpr=snapshot.expected_dpr,
                kpr_residual=snapshot.kpr_residual,
                negative_dpr_residual=snapshot.negative_dpr_residual,
                sample_weight=snapshot.sample_weight,
                acs=snapshot.acs,
                adr=snapshot.adr,
                kd=snapshot.kd,
                hs_pct=snapshot.hs_pct,
                apr=snapshot.apr,
                kast=snapshot.kast,
                opening_frequency=snapshot.opening_frequency,
                opening_efficiency=snapshot.opening_efficiency,
                fk_per_round=snapshot.fk_per_round,
                fd_per_round=snapshot.fd_per_round,
                win_rate=snapshot.win_rate,
                clutch=snapshot.clutch,
                metric_version=version.version,
                metric_version_id=str(version.id),
                reference_period_start=(
                    version.training_start.isoformat() if version.training_start else None
                ),
                reference_period_end=(
                    version.training_end.isoformat() if version.training_end else None
                ),
                interpretation=PUBLIC_INTERPRETATION,
                scope=scope,
                note=_EVENT_CIR_NOTE,
            )

        bundles = EventCirSnapshotService(
            self._session,
            require_complete_maps=True,
        ).score_event_bundles(
            frozen,
            event_id=event.id,
            vlr_event_id=event.vlr_event_id,
        )
        ranked_bundles = sorted(
            bundles,
            key=lambda item: (
                -(item.score.cir or 0.0),
                -item.score.rounds,
                (item.score.handle or "").lower(),
            ),
        )
        event_player_count = len(ranked_bundles)
        match = next(
            (
                (index, bundle)
                for index, bundle in enumerate(ranked_bundles)
                if bundle.score.player_id == player.id
            ),
            None,
        )
        if match is None:
            raise PlayerNotFoundError(player_ref)
        event_rank, bundle = match
        score = bundle.score
        identity = self._players._to_identity(player)
        role_counts = self._role_counts_lookup(
            [player.id],
            event_id=event.id,
        ).get(player.id, {})
        return CirPlayerDetail(
            player_id=str(player.id),
            handle=player.handle,
            team=identity.team,
            role=score.role,
            roles=build_role_mix(role_counts, score.role),
            tier=score.tier,
            event_rank=event_rank + 1,
            event_player_count=event_player_count,
            cir=score.cir,
            raw_cir=score.raw_cir,
            shrunk_raw_cir=score.shrunk_raw_cir,
            reliability=score.reliability,
            reliability_pct=score.reliability_pct,
            sample_status=score.sample_status,
            rounds=score.rounds,
            maps=score.maps,
            matches=bundle.matches,
            events=1,
            combat_factor=score.combat_factor,
            kpr=score.kpr,
            dpr=score.dpr,
            expected_kpr=score.expected_kpr,
            expected_dpr=score.expected_dpr,
            kpr_residual=score.kpr_residual,
            negative_dpr_residual=score.negative_dpr_residual,
            sample_weight=score.sample_weight,
            acs=bundle.acs,
            adr=bundle.adr,
            kd=bundle.kd,
            hs_pct=bundle.hs_pct,
            apr=bundle.apr,
            kast=bundle.kast,
            opening_frequency=bundle.opening_frequency,
            opening_efficiency=bundle.opening_efficiency,
            fk_per_round=bundle.fk_per_round,
            fd_per_round=bundle.fd_per_round,
            win_rate=bundle.win_rate,
            clutch=bundle.clutch,
            metric_version=version.version,
            metric_version_id=str(version.id),
            reference_period_start=(
                version.training_start.isoformat() if version.training_start else None
            ),
            reference_period_end=version.training_end.isoformat() if version.training_end else None,
            interpretation=PUBLIC_INTERPRETATION,
            scope=scope,
            note=_EVENT_CIR_NOTE,
        )

    def list_options(
        self,
        *,
        search: str | None = None,
        team: str | None = None,
        role: str | None = None,
        tier: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PlayerOptionsResponse:
        version = self.resolve_metric_version()
        rows = list(self._session.execute(self._base_query(version.id)).unique().all())
        needle = search.strip().lower() if search else ""
        team_needle = team.strip().lower() if team else ""
        role_needle = role.strip().lower() if role else ""
        tier_needle = tier.strip().lower() if tier else ""
        options: list[PlayerOption] = []
        for snapshot, player, team_row in rows:
            details = snapshot.details or {}
            option_role = _detail_str(details, "role")
            option_tier = _detail_str(details, "tier")
            team_ref = _team_ref(player, team_row)
            if role_needle and (option_role or "").lower() != role_needle:
                continue
            if tier_needle and (option_tier or "").lower() != tier_needle:
                continue
            if team_needle:
                team_haystack = " ".join(
                    [
                        team_ref.name if team_ref else "",
                        team_ref.tag if team_ref else "",
                    ]
                ).lower()
                if team_needle not in team_haystack:
                    continue
            if needle:
                haystack = " ".join(
                    [
                        player.handle,
                        player.real_name or "",
                        team_ref.name if team_ref else "",
                        team_ref.tag if team_ref else "",
                        option_role or "",
                    ]
                ).lower()
                if needle not in haystack:
                    continue
            options.append(
                PlayerOption(
                    id=str(player.id),
                    handle=player.handle,
                    real_name=player.real_name,
                    team=team_ref,
                    role=option_role,
                    tier=option_tier,
                    cir=snapshot.cir,
                    rounds=snapshot.rounds,
                    sample_status=snapshot.sample_status,
                    reliability=snapshot.reliability,
                )
            )
        options.sort(key=lambda item: item.handle.lower())
        total = len(options)
        page = options[offset : offset + limit]
        return PlayerOptionsResponse(total=total, limit=limit, offset=offset, players=page)

    def compare(
        self,
        player_refs: list[str],
        *,
        metric_version: str | None = None,
    ) -> CirCompareResponse:
        version = self.resolve_metric_version(metric_version=metric_version)
        entries: list[CirCompareEntry] = []
        ranks = self._rank_lookup(version.id)
        for ref in player_refs:
            player = self._players._require_player(ref)
            snapshot = self._session.scalar(
                select(PlayerMetricSnapshot).where(
                    PlayerMetricSnapshot.metric_version_id == version.id,
                    PlayerMetricSnapshot.player_id == player.id,
                )
            )
            identity = self._players._to_identity(player)
            details = snapshot.details if snapshot is not None else {}
            entries.append(
                CirCompareEntry(
                    player_id=str(player.id),
                    handle=player.handle,
                    team=identity.team,
                    role=_detail_str(details, "role") if details else None,
                    cir=snapshot.cir if snapshot is not None else None,
                    rank=ranks.get(player.id),
                    reliability=snapshot.reliability if snapshot is not None else None,
                    rounds=snapshot.rounds if snapshot is not None else 0,
                    maps=snapshot.maps_played if snapshot is not None else 0,
                    kpr=_detail_float(details, "kpr") if details else None,
                    expected_kpr=_detail_float(details, "expected_kpr") if details else None,
                    kpr_residual=_detail_float(details, "kpr_residual") if details else None,
                    dpr=_detail_float(details, "dpr") if details else None,
                    expected_dpr=_detail_float(details, "expected_dpr") if details else None,
                    negative_dpr_residual=(
                        _detail_float(details, "negative_dpr_residual") if details else None
                    ),
                    combat_factor=snapshot.combat_component if snapshot is not None else None,
                    sample_status=snapshot.sample_status if snapshot is not None else None,
                    metric_version=version.version,
                )
            )
        return CirCompareResponse(
            players=entries,
            notes="CIR inputs are context-adjusted combat only. Other stats are descriptive.",
        )

    def compare_block(self, player_id: UUID, *, version: MetricVersion) -> PlayerCompareCir | None:
        snapshot = self._session.scalar(
            select(PlayerMetricSnapshot).where(
                PlayerMetricSnapshot.metric_version_id == version.id,
                PlayerMetricSnapshot.player_id == player_id,
            )
        )
        if snapshot is None:
            return None
        details = snapshot.details or {}
        ranks = self._rank_lookup(version.id)
        return PlayerCompareCir(
            cir=snapshot.cir,
            role=_detail_str(details, "role"),
            tier=_detail_str(details, "tier"),
            rank=ranks.get(player_id),
            reliability=snapshot.reliability,
            rounds=snapshot.rounds,
            maps=snapshot.maps_played,
            kpr=_detail_float(details, "kpr"),
            expected_kpr=_detail_float(details, "expected_kpr"),
            kpr_residual=_detail_float(details, "kpr_residual"),
            dpr=_detail_float(details, "dpr"),
            expected_dpr=_detail_float(details, "expected_dpr"),
            negative_dpr_residual=_detail_float(details, "negative_dpr_residual"),
            combat_factor=snapshot.combat_component,
            sample_status=snapshot.sample_status,
            metric_version=version.version,
        )

    def metadata(self, *, metric_version: str | None = None) -> CirMetricMetadata:
        version = self.resolve_metric_version(metric_version=metric_version)
        sync_run = latest_sync_run(self._session)
        played_at = latest_match_played_at(self._session)
        return CirMetricMetadata(
            name=version.name,
            version=version.version,
            status=version.status,
            description=PUBLIC_DESCRIPTION,
            tooltip=PUBLIC_TOOLTIP,
            interpretation=PUBLIC_INTERPRETATION,
            features=["context-adjusted KPR", "context-adjusted death avoidance"],
            context="role + competitive tier",
            scale="0–100 percentile",
            established_sample=ESTABLISHED_ROUNDS,
            provisional_sample=f"{LOW_SAMPLE_ROUNDS}–{ESTABLISHED_ROUNDS - 1} rounds",
            low_sample=f"<{LOW_SAMPLE_ROUNDS} rounds",
            shrinkage_k=SHRINKAGE_K,
            reference_period_start=(
                version.training_start.isoformat() if version.training_start else None
            ),
            reference_period_end=version.training_end.isoformat() if version.training_end else None,
            last_data_sync_at=sync_run.finished_at.isoformat()
            if sync_run is not None and sync_run.finished_at is not None
            else None,
            latest_match_played_at=played_at.isoformat() if played_at is not None else None,
            season=2026,
            circuit=CircuitName.VCT.value,
        )

    def _base_query(
        self, metric_version_id: UUID
    ) -> Select[tuple[PlayerMetricSnapshot, Player, Team]]:
        current_team = (
            select(PlayerTeamHistory.team_id)
            .where(PlayerTeamHistory.player_id == Player.id)
            .order_by(
                PlayerTeamHistory.is_current.desc(),
                PlayerTeamHistory.joined_at.desc().nulls_last(),
            )
            .limit(1)
            .scalar_subquery()
        )
        return (
            select(PlayerMetricSnapshot, Player, Team)
            .join(Player, Player.id == PlayerMetricSnapshot.player_id)
            .outerjoin(Team, Team.id == current_team)
            .where(PlayerMetricSnapshot.metric_version_id == metric_version_id)
            .options(selectinload(Player.team_history).selectinload(PlayerTeamHistory.team))
        )

    def _scoped_base_query(
        self, metric_version_id: UUID, scope_id: str
    ) -> Select[tuple[PlayerMetricScopedSnapshot, Player, Team]]:
        current_team = (
            select(PlayerTeamHistory.team_id)
            .where(PlayerTeamHistory.player_id == Player.id)
            .order_by(
                PlayerTeamHistory.is_current.desc(),
                PlayerTeamHistory.joined_at.desc().nulls_last(),
            )
            .limit(1)
            .scalar_subquery()
        )
        return (
            select(PlayerMetricScopedSnapshot, Player, Team)
            .join(Player, Player.id == PlayerMetricScopedSnapshot.player_id)
            .outerjoin(Team, Team.id == current_team)
            .where(
                PlayerMetricScopedSnapshot.metric_version_id == metric_version_id,
                PlayerMetricScopedSnapshot.scope_type == ScopeType.EVENT.value,
                PlayerMetricScopedSnapshot.scope_id == scope_id,
            )
            .options(selectinload(Player.team_history).selectinload(PlayerTeamHistory.team))
        )

    def _load_event_scoped_rows(
        self, metric_version_id: UUID, event_id: UUID
    ) -> list[tuple[PlayerMetricScopedSnapshot, Player, Team | None]]:
        rows = (
            self._session.execute(
                self._scoped_base_query(metric_version_id, event_scope_id(event_id))
            )
            .unique()
            .all()
        )
        return [(snapshot, player, team) for snapshot, player, team in rows]

    def _event_region_lookup(
        self,
        rows: list[tuple[PlayerMetricSnapshot, Player, Team | None]],
    ) -> dict[UUID, str | None]:
        ids: set[UUID] = set()
        for snapshot, _player, _team in rows:
            ids.update(snapshot_event_ids(snapshot.details or {}))
        if not ids:
            return {}
        events = self._session.scalars(select(Event).where(Event.id.in_(ids))).all()
        return {
            event.id: event_ranking_region(region=event.region, name=event.name) for event in events
        }

    def _role_counts_lookup(
        self,
        player_ids: list[UUID],
        *,
        event_id: UUID | None = None,
    ) -> dict[UUID, dict[str, int]]:
        if not player_ids:
            return {}
        query = (
            select(PlayerMapStats.player_id, Agent.role, func.sum(PlayerMapStats.rounds))
            .join(Agent, Agent.id == PlayerMapStats.agent_id)
            .where(PlayerMapStats.player_id.in_(player_ids))
        )
        if event_id is not None:
            query = (
                query.join(MatchMap, MatchMap.id == PlayerMapStats.match_map_id)
                .join(Match, Match.id == MatchMap.match_id)
                .where(Match.event_id == event_id)
            )
        rows = self._session.execute(
            query.group_by(PlayerMapStats.player_id, Agent.role)
        ).all()
        counts: dict[UUID, dict[str, int]] = {}
        for player_id, role, rounds in rows:
            counts.setdefault(player_id, {})[str(role)] = int(rounds or 0)
        return counts

    def _players_by_ids(self, player_ids: list[UUID]) -> dict[UUID, Player]:
        if not player_ids:
            return {}
        rows = self._session.scalars(
            select(Player)
            .where(Player.id.in_(player_ids))
            .options(selectinload(Player.team_history).selectinload(PlayerTeamHistory.team))
        ).all()
        return {player.id: player for player in rows}

    def _rank_lookup(self, metric_version_id: UUID) -> dict[UUID, int]:
        rows = list(
            self._session.execute(
                select(PlayerMetricSnapshot, Player)
                .join(Player, Player.id == PlayerMetricSnapshot.player_id)
                .where(
                    PlayerMetricSnapshot.metric_version_id == metric_version_id,
                    PlayerMetricSnapshot.sample_status == SampleStatus.ESTABLISHED.value,
                )
            ).all()
        )
        rows.sort(key=lambda item: (-(item[0].cir or 0.0), -item[0].rounds, item[1].handle.lower()))
        return {snapshot.player_id: index + 1 for index, (snapshot, _player) in enumerate(rows)}


def _event_ranking_scope(event: Event, *, event_region: str | None) -> RankingScope:
    return RankingScope(
        type=ScopeType.EVENT.value,
        label=event.name,
        event_id=str(event.id),
        vlr_event_id=event.vlr_event_id,
        tier=event.tier,
        region=event_region,
        status=event.status,
        season_year=event.season_year,
    )


def _allowed_statuses(
    *,
    include_provisional: bool,
    include_low_sample: bool,
    sample_status: str | None,
) -> list[str]:
    if sample_status:
        return [sample_status]
    statuses = [SampleStatus.ESTABLISHED.value]
    if include_provisional:
        statuses.append(SampleStatus.PROVISIONAL.value)
    if include_low_sample:
        statuses.append(SampleStatus.LOW_SAMPLE.value)
    return statuses


def _matches_details(
    snapshot: PlayerMetricSnapshot,
    *,
    role: str | None,
    tier: str | None,
    agent: str | None,
    event: str | None,
) -> bool:
    details = snapshot.details or {}
    if role and str(details.get("role") or "").lower() != role.lower():
        return False
    if tier and str(details.get("tier") or "").lower() != tier.lower():
        return False
    if agent and str(details.get("primary_agent") or "").lower() != agent.lower():
        return False
    if event:
        event_ids = {str(value) for value in details.get("event_ids") or []}
        vlr_ids = {str(value) for value in details.get("vlr_event_ids") or []}
        if event not in event_ids and event not in vlr_ids:
            return False
    return True


def _matches_player_search(player: Player, team: Team | None, search: str) -> bool:
    needle = search.strip().lower()
    if not needle:
        return True
    team_ref = _team_ref(player, team)
    haystack = " ".join(
        [
            player.handle,
            team_ref.name if team_ref else "",
            team_ref.tag if team_ref else "",
        ]
    ).lower()
    return needle in haystack


def _matches_ranking_player_search(player: CirRankingPlayer, search: str) -> bool:
    needle = search.strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        [
            player.handle,
            player.team.name if player.team else "",
            player.team.tag if player.team else "",
        ]
    ).lower()
    return needle in haystack


def _season_row_sort_key(
    *,
    sort: str | None,
    order: str | None,
) -> Callable[[tuple[PlayerMetricSnapshot, Player, Team | None]], tuple[object, ...]]:
    descending = (order or "desc").lower() != "asc"
    if sort is None:

        def default_key(
            item: tuple[PlayerMetricSnapshot, Player, Team | None],
        ) -> tuple[object, ...]:
            snapshot, player, _team = item
            return (
                -(snapshot.cir or 0.0),
                -snapshot.rounds,
                player.handle.lower(),
            )

        return default_key

    field = sort.lower()
    if field not in _SORTABLE_FIELDS:
        field = "cir"

    def key(item: tuple[PlayerMetricSnapshot, Player, Team | None]) -> tuple[object, ...]:
        snapshot, player, _team = item
        if field == "cir":
            value = snapshot.cir
        elif field == "rounds":
            value = snapshot.rounds
        elif field == "maps":
            value = snapshot.maps_played
        elif field == "kpr":
            value = _detail_float(snapshot.details or {}, "kpr")
        elif field == "dpr":
            value = _detail_float(snapshot.details or {}, "dpr")
        else:
            # Extra descriptive fields are None on season snapshots.
            value = None
        return (_sort_tuple(value, descending), -snapshot.rounds, player.handle.lower())

    return key


def _ranking_player_sort_key(
    *,
    sort: str | None,
    order: str | None,
) -> Callable[[CirRankingPlayer], tuple[object, ...]]:
    descending = (order or "desc").lower() != "asc"
    if sort is None:

        def default_key(player: CirRankingPlayer) -> tuple[object, ...]:
            return (
                -(player.cir or 0.0),
                -player.rounds,
                player.handle.lower(),
            )

        return default_key

    field = sort.lower()
    if field not in _SORTABLE_FIELDS:
        field = "cir"

    def key(player: CirRankingPlayer) -> tuple[object, ...]:
        value = getattr(player, field, None)
        return (_sort_tuple(value, descending), -player.rounds, player.handle.lower())

    return key


def _sort_tuple(value: float | int | None, descending: bool) -> tuple[int, float]:
    if value is None:
        return (1, 0.0)
    numeric = float(value)
    return (0, -numeric if descending else numeric)


def _team_ref(player: Player, team: Team | None) -> TeamRef | None:
    if team is not None:
        return _as_team_ref(team)
    current = next((entry for entry in player.team_history if entry.is_current), None)
    if current is None and player.team_history:
        current = max(player.team_history, key=lambda entry: entry.joined_at or "")
    if current is None:
        return None
    return _as_team_ref(current.team)


def _as_team_ref(team: Team) -> TeamRef:
    return TeamRef(
        id=str(team.id),
        vlr_team_id=team.vlr_team_id,
        name=team.name,
        tag=team.tag,
        region=team.region,
    )


def _to_ranking_player(
    *,
    rank: int,
    snapshot: PlayerMetricSnapshot,
    player: Player,
    team: Team | None,
    version: MetricVersion,
    event_regions: dict[UUID, str | None],
    role_counts: dict[str, int],
) -> CirRankingPlayer:
    details = snapshot.details or {}
    team_ref = _team_ref(player, team)
    region = pick_ranking_region(
        team_region=team_ref.region if team_ref is not None else None,
        event_regions=[event_regions.get(event_id) for event_id in snapshot_event_ids(details)],
    )
    cir_role = _detail_str(details, "role")
    return CirRankingPlayer(
        rank=rank,
        player_id=str(player.id),
        handle=player.handle,
        team=team_ref,
        role=cir_role,
        roles=build_role_mix(role_counts, cir_role),
        tier=_detail_str(details, "tier"),
        region=region,
        primary_agent=_detail_str(details, "primary_agent"),
        cir=snapshot.cir,
        reliability=snapshot.reliability,
        reliability_pct=_detail_float(details, "reliability_pct"),
        rounds=snapshot.rounds,
        maps=snapshot.maps_played,
        matches=None,
        kpr=_detail_float(details, "kpr"),
        dpr=_detail_float(details, "dpr"),
        acs=None,
        adr=None,
        kd=None,
        hs_pct=None,
        apr=None,
        kast=None,
        opening_frequency=None,
        opening_efficiency=None,
        fk_per_round=None,
        fd_per_round=None,
        win_rate=None,
        clutch=None,
        sample_status=snapshot.sample_status,
        metric_version=version.version,
        metric_version_id=str(version.id),
        rank_label=None,
    )


def _to_scoped_ranking_player(
    *,
    rank: int,
    snapshot: PlayerMetricScopedSnapshot,
    player: Player,
    team: Team | None,
    version: MetricVersion,
    event_region: str | None,
    role_counts: dict[str, int],
) -> CirRankingPlayer:
    team_ref = _team_ref(player, team)
    region = pick_ranking_region(
        team_region=team_ref.region if team_ref is not None else None,
        event_regions=[event_region],
    )
    return CirRankingPlayer(
        rank=rank,
        player_id=str(player.id),
        handle=player.handle,
        team=team_ref,
        role=snapshot.role,
        roles=build_role_mix(role_counts, snapshot.role),
        tier=snapshot.tier,
        region=region,
        primary_agent=snapshot.primary_agent,
        cir=snapshot.cir_percentile,
        reliability=snapshot.reliability,
        reliability_pct=reliability_pct_for_rounds(snapshot.rounds),
        rounds=snapshot.rounds,
        maps=snapshot.maps,
        matches=snapshot.matches,
        kpr=snapshot.kpr,
        dpr=snapshot.dpr,
        acs=snapshot.acs,
        adr=snapshot.adr,
        kd=snapshot.kd,
        hs_pct=snapshot.hs_pct,
        apr=snapshot.apr,
        kast=snapshot.kast,
        opening_frequency=snapshot.opening_frequency,
        opening_efficiency=snapshot.opening_efficiency,
        fk_per_round=snapshot.fk_per_round,
        fd_per_round=snapshot.fd_per_round,
        win_rate=snapshot.win_rate,
        clutch=snapshot.clutch,
        sample_status=snapshot.sample_status,
        metric_version=version.version,
        metric_version_id=str(version.id),
        rank_label=_EVENT_RANK_LABEL,
    )


def _to_bundle_ranking_player(
    *,
    rank: int,
    bundle: EventScopedPlayerBundle,
    player: Player | None,
    version: MetricVersion,
    event_region: str | None,
    role_counts: dict[str, int],
) -> CirRankingPlayer:
    score = bundle.score
    team_ref = _team_ref(player, None) if player is not None else None
    region = pick_ranking_region(
        team_region=team_ref.region if team_ref is not None else None,
        event_regions=[event_region],
    )
    return CirRankingPlayer(
        rank=rank,
        player_id=str(score.player_id),
        handle=player.handle if player is not None else (score.handle or ""),
        team=team_ref,
        role=score.role,
        roles=build_role_mix(role_counts, score.role),
        tier=score.tier,
        region=region,
        primary_agent=score.primary_agent,
        cir=score.cir,
        reliability=score.reliability,
        reliability_pct=score.reliability_pct,
        rounds=score.rounds,
        maps=score.maps,
        matches=bundle.matches,
        kpr=score.kpr,
        dpr=score.dpr,
        acs=bundle.acs,
        adr=bundle.adr,
        kd=bundle.kd,
        hs_pct=bundle.hs_pct,
        apr=bundle.apr,
        kast=bundle.kast,
        opening_frequency=bundle.opening_frequency,
        opening_efficiency=bundle.opening_efficiency,
        fk_per_round=bundle.fk_per_round,
        fd_per_round=bundle.fd_per_round,
        win_rate=bundle.win_rate,
        clutch=bundle.clutch,
        sample_status=score.sample_status,
        metric_version=version.version,
        metric_version_id=str(version.id),
        rank_label=_EVENT_RANK_LABEL,
    )


def _detail_str(details: dict[str, object], key: str) -> str | None:
    value = details.get(key)
    return str(value) if value is not None else None


def _detail_float(details: dict[str, object], key: str) -> float | None:
    value = details.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _as_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
