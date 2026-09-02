from __future__ import annotations

from app.models.player_map_stats import PlayerMapStats
from app.schemas.ingestion import NormalizedPlayerMapStats
from app.schemas.mir import EconomyFeatureAvailability

_ECONOMY_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("pistol_rounds", "vlrggapi / PlayerMapStats", "round"),
    ("eco_rounds", "vlrggapi / PlayerMapStats", "round"),
    ("semi_buy_rounds", "vlrggapi / PlayerMapStats", "round"),
    ("full_buy_rounds", "vlrggapi / PlayerMapStats", "round"),
    ("economy_category", "vlrggapi / PlayerMapStats", "round"),
    ("loadout_value", "vlrggapi / PlayerMapStats", "round"),
    ("team_economy_state", "vlrggapi / MatchMap", "team-round"),
)


def inspect_economy_availability() -> list[EconomyFeatureAvailability]:
    """Static inventory: no economy fields exist on models or the vlrggapi normalizer."""
    model_fields = set(PlayerMapStats.__table__.columns.keys())
    ingest_fields = set(NormalizedPlayerMapStats.model_fields)
    rows: list[EconomyFeatureAvailability] = []
    for field, source, granularity in _ECONOMY_FIELDS:
        present = field in model_fields or field in ingest_fields
        rows.append(
            EconomyFeatureAvailability(
                field=field,
                source=source,
                coverage=1.0 if present else 0.0,
                granularity=granularity if present else "unavailable",
                historical_availability="none",
                missing_pct=0.0 if present else 100.0,
                usable_for_mir=present,
                notes=(
                    "Present on the canonical model."
                    if present
                    else (
                        "Not stored on PlayerMapStats or NormalizedPlayerMapStats; "
                        "not parsed from vlrggapi."
                    )
                ),
            )
        )
    return rows


def economy_is_usable(rows: list[EconomyFeatureAvailability] | None = None) -> bool:
    inventory = rows if rows is not None else inspect_economy_availability()
    return any(item.usable_for_mir for item in inventory)
