from pydantic import BaseModel


class PlayerStats(BaseModel):
    matches: int
    acs: float
    kd: float
    hs_percent: float
    adr: float
    win_rate: float


class PlayerProfile(BaseModel):
    id: str
    display_name: str
    riot_id: str
    team: str | None
    region: str
    rank: str
    stats: PlayerStats


class PlayerComparison(BaseModel):
    players: list[PlayerProfile]
    notes: str
