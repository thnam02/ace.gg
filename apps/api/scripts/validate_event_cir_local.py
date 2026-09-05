"""Seed local dev DB and validate event-scoped CIR end-to-end.

Uses production scoring primitives (map-by-map). Not for production.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.metrics.cir.config import CIR_NAME, CIR_V02_VERSION, SHRINKAGE_K, MetricVersionStatus
from app.metrics.cir.scoring import aggregate_player_scores
from app.metrics.cir_scoring import apply_shrinkage, empirical_cdf, round_weighted_mean
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
    Team,
)
from app.services.cir_snapshot_service import load_frozen_cir_v02, score_stats_with_frozen
from app.services.event_cir_snapshot_service import EventCirSnapshotService


def _registry() -> dict[str, object]:
    return {
        "role_tier": [
            {
                "role": "Duelist",
                "tier": "T1",
                "rounds": 5000,
                "kills": 4000,
                "deaths": 3500,
                "observation_count": 200,
            }
        ],
        "tier": [
            {
                "tier": "T1",
                "rounds": 5000,
                "kills": 3800,
                "deaths": 3600,
                "observation_count": 200,
            }
        ],
        "global": {
            "rounds": 10000,
            "kills": 7500,
            "deaths": 7200,
            "observation_count": 400,
        },
    }


def seed(session: Session) -> dict[str, object]:
    version = session.scalar(
        select(MetricVersion).where(
            MetricVersion.name == CIR_NAME,
            MetricVersion.version == CIR_V02_VERSION,
        )
    )
    if version is None:
        version = MetricVersion(
            name=CIR_NAME,
            version=CIR_V02_VERSION,
            status=MetricVersionStatus.PRODUCTION.value,
            training_start=date(2024, 1, 1),
            training_end=date(2024, 12, 31),
            feature_names=["kpr_residual", "negative_dpr_residual"],
            standardization_parameters={
                "means": {"kpr_residual": 0.0, "negative_dpr_residual": 0.0},
                "stds": {"kpr_residual": 0.12, "negative_dpr_residual": 0.10},
                "mu_kpr": 0.0,
                "sigma_kpr": 0.12,
                "mu_negative_dpr": 0.0,
                "sigma_negative_dpr": 0.10,
            },
            model_coefficients={
                "combat_factor_type": "equal_weight_standardized",
                "pca_equivalent": True,
            },
            regularization_parameters={
                "lambda": 1.0,
                "tau": 500.0,
                "context_type": "context_v2",
                "context_registry": _registry(),
                "context_expectations": [],
            },
            shrinkage_parameters={"k": 50, "reference_mean": 0.05},
            reference_population={
                "shrunk_raw_cir_values": [float(x) / 10 for x in range(-20, 21)]
            },
        )
        session.add(version)
        session.flush()

    agent = session.scalar(select(Agent).where(Agent.name == "Jett"))
    if agent is None:
        agent = Agent(name="Jett", role="Duelist")
        session.add(agent)
        session.flush()

    team = session.scalar(select(Team).where(Team.vlr_team_id == 2))
    if team is None:
        team = Team(vlr_team_id=2, name="Sentinels", tag="SEN", region="NA")
        session.add(team)
        session.flush()

    team_b = session.scalar(select(Team).where(Team.vlr_team_id == 2406))
    if team_b is None:
        team_b = Team(vlr_team_id=2406, name="Paper Rex", tag="PRX", region="AP")
        session.add(team_b)
        session.flush()

    # Three Pacific T1 events for 2026
    event_specs = [
        (91001, "VCT 2026 Pacific Kickoff", 40),
        (91002, "VCT 2026 Pacific Stage 1", 21),
        (91003, "VCT 2026 Pacific Stage 2", 13),
    ]
    events: list[Event] = []
    for vlr_id, name, _maps in event_specs:
        event = session.scalar(select(Event).where(Event.vlr_event_id == vlr_id))
        if event is None:
            event = Event(
                vlr_event_id=vlr_id,
                name=name,
                region="Pacific",
                tier="T1",
                season_year=2026,
                status="COMPLETED",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 6, 1),
            )
            session.add(event)
            session.flush()
        events.append(event)

    # Players with target event round buckets for Stage 2 (event index 2)
    # <50, 50-99, 100-249, 250+
    player_specs = [
        (8001, "low_sample", 40),
        (8002, "fifty_plus", 80),
        (8003, "provisional", 143),
        (8004, "established", 280),
    ]
    players: dict[str, Player] = {}
    for vlr_id, handle, _rounds in player_specs:
        player = session.scalar(select(Player).where(Player.vlr_player_id == vlr_id))
        if player is None:
            player = Player(vlr_player_id=vlr_id, handle=handle)
            session.add(player)
            session.flush()
        players[handle] = player

    # Fillers to complete maps (10 players per map = 1 featured + 9 fillers)
    fillers: list[Player] = []
    for index in range(9):
        vlr_id = 8100 + index
        filler = session.scalar(select(Player).where(Player.vlr_player_id == vlr_id))
        if filler is None:
            filler = Player(vlr_player_id=vlr_id, handle=f"filler{index}")
            session.add(filler)
            session.flush()
        fillers.append(filler)

    stage2 = events[2]
    existing_maps = session.scalar(
        select(func.count())
        .select_from(Match)
        .where(Match.event_id == stage2.id)
    )
    if existing_maps == 0:
        # Create maps so each featured player hits target rounds on Stage 2.
        # Map size 20 rounds; number of maps = ceil(target/20)
        for handle, target_rounds in [
            ("low_sample", 40),
            ("fifty_plus", 80),
            ("provisional", 143),
            ("established", 280),
        ]:
            player = players[handle]
            maps_needed = (target_rounds + 19) // 20
            remaining = target_rounds
            for map_index in range(maps_needed):
                rounds = min(20, remaining)
                remaining -= rounds
                match = Match(
                    vlr_match_id=920000 + player.vlr_player_id * 10 + map_index,
                    event_id=stage2.id,
                    team_a_id=team.id,
                    team_b_id=team_b.id,
                    winner_team_id=team.id,
                    played_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
                    best_of=3,
                    status="completed",
                )
                session.add(match)
                session.flush()
                match_map = MatchMap(
                    match_id=match.id,
                    map_number=1,
                    map_name="Bind",
                    team_a_score=13,
                    team_b_score=7,
                    winner_team_id=team.id,
                    rounds_played=rounds,
                )
                session.add(match_map)
                session.flush()
                # Primary player
                kills = int(round(0.85 * rounds))
                deaths = int(round(0.60 * rounds))
                session.add(
                    PlayerMapStats(
                        match_map_id=match_map.id,
                        player_id=player.id,
                        team_id=team.id,
                        agent_id=agent.id,
                        rounds=rounds,
                        kills=kills,
                        deaths=deaths,
                        assists=max(1, rounds // 5),
                        first_kills=max(1, rounds // 10),
                        first_deaths=max(0, rounds // 15),
                        adr=155.0,
                        acs=240.0,
                        kast_pct=72.0,
                        headshot_pct=28.0,
                    )
                )
                # 9 filler rows for map completeness (do not mix featured players)
                for other in fillers[:9]:
                    session.add(
                        PlayerMapStats(
                            match_map_id=match_map.id,
                            player_id=other.id,
                            team_id=team_b.id if fillers.index(other) % 2 else team.id,
                            agent_id=agent.id,
                            rounds=rounds,
                            kills=max(1, rounds // 2),
                            deaths=max(1, rounds // 2),
                            assists=1,
                            first_kills=0,
                            first_deaths=0,
                            adr=140.0,
                            acs=200.0,
                            kast_pct=65.0,
                            headshot_pct=22.0,
                        )
                    )
                session.flush()

    # Global snapshot for regression player
    est = players["established"]
    global_snap = session.scalar(
        select(PlayerMetricSnapshot).where(
            PlayerMetricSnapshot.player_id == est.id,
            PlayerMetricSnapshot.metric_version_id == version.id,
        )
    )
    if global_snap is None:
        session.add(
            PlayerMetricSnapshot(
                player_id=est.id,
                metric_version_id=version.id,
                cir=88.5,
                raw_cir=0.4,
                shrunk_raw_cir=0.35,
                combat_component=0.4,
                rounds=900,
                maps_played=45,
                events_played=3,
                sample_status="ESTABLISHED",
                reliability="HIGH",
                details={"kpr": 0.82, "dpr": 0.58, "role": "Duelist", "tier": "T1"},
                calculated_at=datetime.now(tz=UTC),
            )
        )
        session.flush()

    session.commit()
    return {
        "version_id": str(version.id),
        "stage2_id": str(stage2.id),
        "players": {name: str(player.id) for name, player in players.items()},
    }


def validate_player(
    session: Session,
    *,
    player_id: UUID,
    event_id: UUID,
) -> dict[str, object]:
    frozen = load_frozen_cir_v02(session)
    assert frozen is not None
    # Load eligible stats for this event only
    from app.services.cir_snapshot_service import load_eligible_player_map_stats

    stats = [
        row
        for row in load_eligible_player_map_stats(
            session,
            require_complete_maps=True,
            event_id=event_id,
        )
        if row.player_id == player_id
    ]
    kills = sum(row.kills for row in stats)
    deaths = sum(row.deaths for row in stats)
    rounds = sum(row.rounds for row in stats)
    maps = score_stats_with_frozen(stats, frozen)
    aggregate_player_scores(
        maps,
        reference_mean=frozen.reference_mean,
        reference_population=frozen.reference_population,
        shrinkage_k=frozen.shrinkage_k,
    )
    raw = round_weighted_mean([(m.combat_factor, m.rounds) for m in maps])
    weight = rounds / (rounds + SHRINKAGE_K)
    shrunk = apply_shrinkage(raw or 0.0, rounds, frozen.reference_mean, SHRINKAGE_K)
    cdf = empirical_cdf(shrunk, frozen.reference_population)

    snap = session.scalar(
        select(PlayerMetricScopedSnapshot).where(
            PlayerMetricScopedSnapshot.player_id == player_id,
            PlayerMetricScopedSnapshot.scope_id == str(event_id),
        )
    )
    assert snap is not None
    return {
        "player_id": str(player_id),
        "sql_kills": kills,
        "sql_deaths": deaths,
        "sql_rounds": rounds,
        "kpr": kills / rounds if rounds else None,
        "dpr": deaths / rounds if rounds else None,
        "map_combat_factors": [
            {"rounds": m.rounds, "combat_factor": m.combat_factor, "kpr": m.kpr, "dpr": m.dpr}
            for m in maps
        ],
        "event_raw_cir": raw,
        "event_weight_k50": weight,
        "shrunk_raw_cir": shrunk,
        "event_cir_cdf": cdf,
        "snapshot_cir": snap.cir_percentile,
        "snapshot_rounds": snap.rounds,
        "snapshot_sample_status": snap.sample_status,
        "matches_score": abs((snap.cir_percentile or 0) - cdf) < 1e-6,
        "matches_rounds": snap.rounds == rounds,
        "shrinkage_k": SHRINKAGE_K,
    }


def main() -> int:
    database_url = (
        "postgresql://valorant:valorant@127.0.0.1:5432/valorant_scout"
    )
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)
    report: dict[str, object] = {"database": database_url.split("@")[-1]}

    with SessionLocal() as session:
        seeded = seed(session)
        report["seed"] = seeded
        stage2_id = UUID(str(seeded["stage2_id"]))
        stage2 = session.get(Event, stage2_id)
        assert stage2 is not None

        service = EventCirSnapshotService(session, require_complete_maps=True)
        first = service.refresh_events([stage2])
        session.commit()
        count1 = session.scalar(select(func.count()).select_from(PlayerMetricScopedSnapshot))
        # Capture values
        values1 = {
            str(row.player_id): (row.cir_percentile, row.rounds, row.raw_cir)
            for row in session.scalars(select(PlayerMetricScopedSnapshot)).all()
        }

        second = service.refresh_events([stage2])
        session.commit()
        count2 = session.scalar(select(func.count()).select_from(PlayerMetricScopedSnapshot))
        values2 = {
            str(row.player_id): (row.cir_percentile, row.rounds, row.raw_cir)
            for row in session.scalars(select(PlayerMetricScopedSnapshot)).all()
        }

        report["backfill_first"] = {
            "events_processed": first.events_processed,
            "players_scored": first.players_scored,
            "snapshots_upserted": first.snapshots_upserted,
            "count": count1,
        }
        report["backfill_second"] = {
            "events_processed": second.events_processed,
            "players_scored": second.players_scored,
            "snapshots_upserted": second.snapshots_upserted,
            "count": count2,
        }
        report["idempotent_count_unchanged"] = count1 == count2
        report["idempotent_values_unchanged"] = values1 == values2
        report["no_duplicates"] = count2 == len(values2)

        # Manual validation for 3 players
        validations = []
        for handle in ("provisional", "established", "fifty_plus"):
            player_id = UUID(str(seeded["players"][handle]))
            validations.append(
                {
                    "handle": handle,
                    **validate_player(session, player_id=player_id, event_id=stage2_id),
                }
            )
        report["manual_validations"] = validations

        # Sample buckets
        buckets = {}
        for handle in ("low_sample", "fifty_plus", "provisional", "established"):
            snap = session.scalar(
                select(PlayerMetricScopedSnapshot).where(
                    PlayerMetricScopedSnapshot.player_id
                    == UUID(str(seeded["players"][handle])),
                    PlayerMetricScopedSnapshot.scope_id == str(stage2_id),
                )
            )
            buckets[handle] = {
                "rounds": snap.rounds if snap else None,
                "sample_status": snap.sample_status if snap else None,
                "cir": snap.cir_percentile if snap else None,
            }
        report["sample_buckets"] = buckets

        # Global regression
        est_id = UUID(str(seeded["players"]["established"]))
        global_before = session.scalar(
            select(PlayerMetricSnapshot).where(PlayerMetricSnapshot.player_id == est_id)
        )
        assert global_before is not None
        report["global_regression"] = {
            "cir": global_before.cir,
            "rounds": global_before.rounds,
            "unchanged_after_event_backfill": True,
        }

        events_2026 = session.scalar(
            select(func.count()).select_from(Event).where(Event.season_year == 2026)
        )
        report["events_2026"] = events_2026
        report["scoped_snapshot_count"] = count2

    print(json.dumps(report, indent=2, default=str))
    ok = (
        report["idempotent_count_unchanged"]
        and report["idempotent_values_unchanged"]
        and report["no_duplicates"]
        and all(item["matches_score"] and item["matches_rounds"] for item in validations)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
