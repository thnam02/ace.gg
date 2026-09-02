from __future__ import annotations

from typing import Any

from app.parsers.numbers import parse_optional_int


def resolve_map_rounds(
    team_a_score: int | None,
    team_b_score: int | None,
) -> int | None:
    if team_a_score is None or team_b_score is None:
        return None
    return team_a_score + team_b_score


def resolve_player_rounds(
    player_row: dict[str, Any],
    *,
    map_rounds: int | None,
) -> tuple[int | None, str]:
    from_row = parse_optional_int(player_row.get("rounds"))
    if from_row is not None:
        return from_row, "player_row"

    if map_rounds is not None:
        return map_rounds, "map_score"

    return None, "unresolved"
