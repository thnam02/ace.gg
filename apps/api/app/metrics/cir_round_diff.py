from __future__ import annotations


def actual_round_diff(team_a_score: int | None, team_b_score: int | None) -> int | None:
    if team_a_score is None or team_b_score is None:
        return None
    return team_a_score - team_b_score


def expected_round_diff_team_a(expected_win_probability_team_a: float, rounds_played: int) -> float:
    """
      Map pre-match win probability to an expected round margin for team A.

      Model: E[round_diff] = (2 * P_A - 1) * (rounds_played / 2)

      At P_A = 0.5 the expected margin is 0. At P_A = 1.0 team A is expected to win
    every round over team B on average for the given total rounds.
    """
    if rounds_played <= 0:
        return 0.0
    return (2.0 * expected_win_probability_team_a - 1.0) * (rounds_played / 2.0)


def outcome_residual(actual_round_diff: int, expected_round_diff: float) -> float:
    return float(actual_round_diff) - expected_round_diff
