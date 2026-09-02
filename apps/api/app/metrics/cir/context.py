from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.metrics.cir.config import TAU
from app.metrics.context_baselines import ContextExposure, ContextObservation
from app.metrics.context_v2 import (
    ContextV2Level,
    ContextV2Registry,
    hierarchical_mean,
    rate_from_exposure,
)
from app.metrics.derived import safe_ratio


def observed_kpr(kills: int, rounds: int) -> float | None:
    return safe_ratio(kills, rounds)


def observed_dpr(deaths: int, rounds: int) -> float | None:
    return safe_ratio(deaths, rounds)


def dummy_observation(role: str, tier: str | None) -> ContextObservation:
    return ContextObservation(
        observation_id=uuid4(),
        role=role,
        agent_name="Unknown",
        map_name="Unknown",
        tier=tier,
        played_at=None,
        rounds=1,
        kills=0,
        deaths=0,
        assists=0,
        first_kills=0,
        first_deaths=0,
        kast_pct=None,
        clutch_wins=None,
        clutch_attempts=None,
    )


def expected_rates(
    registry: ContextV2Registry,
    observation: ContextObservation,
    *,
    tau: float = TAU,
) -> tuple[float | None, float | None]:
    expected_kpr, _level = hierarchical_mean(
        registry, observation, ContextV2Level.ROLE_TIER, "kpr", tau
    )
    expected_dpr, _level = hierarchical_mean(
        registry, observation, ContextV2Level.ROLE_TIER, "dpr", tau
    )
    return expected_kpr, expected_dpr


def serialize_combat_registry(registry: ContextV2Registry) -> dict[str, Any]:
    return {
        "role_tier": [
            _exposure_payload({"role": role, "tier": tier}, exposure)
            for (role, tier), exposure in sorted(
                registry.role_tier.items(), key=lambda item: (item[0][0], str(item[0][1]))
            )
        ],
        "tier": [
            _exposure_payload({"tier": tier}, exposure)
            for tier, exposure in sorted(registry.tier.items(), key=lambda item: str(item[0]))
        ],
        "global": _exposure_fields(registry.global_exposure),
    }


def load_combat_registry(payload: dict[str, Any]) -> ContextV2Registry:
    registry = ContextV2Registry()
    for row in payload.get("role_tier", []):
        role = str(row["role"])
        tier = row.get("tier")
        registry.role_tier[(role, tier if tier is None else str(tier))] = _exposure_from_row(row)
    for row in payload.get("tier", []):
        tier = row.get("tier")
        registry.tier[tier if tier is None else str(tier)] = _exposure_from_row(row)
    global_row = payload.get("global") or {}
    registry.global_exposure = _exposure_from_row(global_row)
    return registry


def context_expectation_table(
    registry: ContextV2Registry,
    *,
    tau: float = TAU,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (role, tier), exposure in sorted(
        registry.role_tier.items(), key=lambda item: (item[0][0], str(item[0][1]))
    ):
        parent = registry.tier.get(tier, ContextExposure())
        observation = dummy_observation(role, tier)
        shrunk_kpr, _ = hierarchical_mean(
            registry, observation, ContextV2Level.ROLE_TIER, "kpr", tau
        )
        shrunk_dpr, _ = hierarchical_mean(
            registry, observation, ContextV2Level.ROLE_TIER, "dpr", tau
        )
        rows.append(
            {
                "role": role,
                "tier": tier,
                "context": f"{role}|{tier}",
                "exposure": exposure.rounds,
                "raw_expected_kpr": rate_from_exposure(exposure, "kpr"),
                "parent_expected_kpr": rate_from_exposure(parent, "kpr"),
                "shrunk_expected_kpr": shrunk_kpr,
                "raw_expected_dpr": rate_from_exposure(exposure, "dpr"),
                "parent_expected_dpr": rate_from_exposure(parent, "dpr"),
                "shrunk_expected_dpr": shrunk_dpr,
                "tau": tau,
            }
        )
    return rows


def _exposure_payload(keys: dict[str, Any], exposure: ContextExposure) -> dict[str, Any]:
    payload = dict(keys)
    payload.update(_exposure_fields(exposure))
    return payload


def _exposure_fields(exposure: ContextExposure) -> dict[str, Any]:
    return {
        "rounds": exposure.rounds,
        "kills": exposure.kills,
        "deaths": exposure.deaths,
        "observation_count": exposure.observation_count,
    }


def _exposure_from_row(row: dict[str, Any]) -> ContextExposure:
    return ContextExposure(
        rounds=int(row.get("rounds") or 0),
        kills=int(row.get("kills") or 0),
        deaths=int(row.get("deaths") or 0),
        observation_count=int(row.get("observation_count") or 0),
    )
