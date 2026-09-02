from pydantic import BaseModel


class OpponentStrengthFeatures(BaseModel):
    team_rating_pre_match: float | None = None
    opponent_rating_pre_match: float | None = None
    expected_team_win_probability: float | None = None


class TeamRatingRebuildSummary(BaseModel):
    matches_processed: int = 0
    matches_skipped: int = 0
    snapshots_written: int = 0
