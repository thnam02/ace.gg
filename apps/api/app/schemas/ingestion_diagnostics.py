from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlayerIdentityDiagnostics:
    resolved_by_id: int = 0
    resolved_by_event_roster: int = 0
    resolved_by_team_roster: int = 0
    resolved_by_history: int = 0
    resolved_by_db_identity: int = 0
    resolved_by_search: int = 0
    unresolved: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)


@dataclass
class IngestionDiagnostics:
    player_identity: PlayerIdentityDiagnostics = field(default_factory=PlayerIdentityDiagnostics)
    missing_rounds: int = 0
    missing_kast: int = 0
    missing_clutch: int = 0
    rejected_stat_rows: list[str] = field(default_factory=list)
    invalid_agent_values: list[str] = field(default_factory=list)
    unknown_agent_rows: int = 0
    maps_complete: int = 0
    maps_incomplete: int = 0
    maps_empty: int = 0
    team_profiles_fetched: int = 0
    team_profiles_cached: int = 0
    player_searches_fetched: int = 0
    player_searches_cached: int = 0
    player_profiles_fetched: int = 0
    player_profiles_cached: int = 0

    def unresolved_player_count(self) -> int:
        return len(self.player_identity.unresolved)

    def ambiguous_player_count(self) -> int:
        return len(self.player_identity.ambiguous)

    def record_invalid_agent(self, raw_value: str) -> None:
        if raw_value and raw_value not in self.invalid_agent_values:
            self.invalid_agent_values.append(raw_value)
