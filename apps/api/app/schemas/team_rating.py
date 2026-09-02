from pydantic import BaseModel, Field


class OpponentStrengthFeatures(BaseModel):
    team_rating_pre_match: float | None = None
    opponent_rating_pre_match: float | None = None
    expected_team_win_probability: float | None = None


class HighestRatedTeam(BaseModel):
    team_id: str
    team_name: str
    rating: float


class TeamRatingRebuildSummary(BaseModel):
    matches_processed: int = 0
    matches_skipped: int = 0
    snapshots_written: int = 0
    teams_rated: int = 0
    rating_min: float | None = None
    rating_p25: float | None = None
    rating_median: float | None = None
    rating_p75: float | None = None
    rating_max: float | None = None
    highest_rated_teams: list[HighestRatedTeam] = Field(default_factory=list)
