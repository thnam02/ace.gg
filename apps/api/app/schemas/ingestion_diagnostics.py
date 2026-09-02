from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlayerIdentityDiagnostics:
    resolved_by_id: int = 0
    resolved_by_roster: int = 0
    resolved_by_name: int = 0
    unresolved: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)


@dataclass
class IngestionDiagnostics:
    player_identity: PlayerIdentityDiagnostics = field(default_factory=PlayerIdentityDiagnostics)
    missing_rounds: int = 0
    missing_kast: int = 0
    missing_clutch: int = 0
    rejected_stat_rows: list[str] = field(default_factory=list)

    def unresolved_player_count(self) -> int:
        return len(self.player_identity.unresolved)

    def ambiguous_player_count(self) -> int:
        return len(self.player_identity.ambiguous)
