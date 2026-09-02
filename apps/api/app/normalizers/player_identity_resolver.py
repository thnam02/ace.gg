from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.normalizers.vlr_api_parsing import (
    as_dict,
    as_list,
    parse_team_roster_players,
    parse_vlr_id,
)
from app.schemas.ingestion_diagnostics import IngestionDiagnostics


def normalize_player_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


class PlayerIdentityResolver:
    """Resolve VLR player IDs with explicit priority and diagnostics."""

    def __init__(
        self,
        roster_map: dict[str, int],
        *,
        ambiguous_names: set[str] | None = None,
        known_handles: dict[str, int] | None = None,
        known_ambiguous: set[str] | None = None,
        diagnostics: IngestionDiagnostics | None = None,
    ) -> None:
        self._roster_map = dict(roster_map)
        self._ambiguous_names = set(ambiguous_names or ())
        self._known_handles = {
            normalize_player_name(key): value for key, value in (known_handles or {}).items()
        }
        self._known_ambiguous = {normalize_player_name(name) for name in (known_ambiguous or ())}
        self._team_rosters: dict[int, dict[str, int]] = {}
        self._team_ambiguous: dict[int, set[str]] = {}
        self._diagnostics = diagnostics

    @classmethod
    def from_event_teams(
        cls,
        event_data: dict[str, Any],
        *,
        known_handles: dict[str, int] | None = None,
        known_ambiguous: set[str] | None = None,
        diagnostics: IngestionDiagnostics | None = None,
    ) -> PlayerIdentityResolver:
        segments = as_dict(event_data.get("segments"))
        name_ids: dict[str, set[int]] = defaultdict(set)
        for team in as_list(segments.get("teams")):
            team_row = as_dict(team)
            for player in as_list(team_row.get("players")):
                player_row = as_dict(player)
                player_id = parse_vlr_id(player_row.get("id"))
                handle = str(player_row.get("name") or player_row.get("alias") or "").strip()
                if player_id is None or not handle:
                    continue
                name_ids[normalize_player_name(handle)].add(player_id)

        ambiguous = {name for name, ids in name_ids.items() if len(ids) > 1}
        roster = {name: next(iter(ids)) for name, ids in name_ids.items() if len(ids) == 1}
        return cls(
            roster,
            ambiguous_names=ambiguous,
            known_handles=known_handles,
            known_ambiguous=known_ambiguous,
            diagnostics=diagnostics,
        )

    def add_team_roster(self, team_vlr_id: int, team_payload: dict[str, Any]) -> None:
        name_ids: dict[str, set[int]] = defaultdict(set)
        for player_id, handle in parse_team_roster_players(team_payload):
            name_ids[normalize_player_name(handle)].add(player_id)
        unique: dict[str, int] = {}
        ambiguous: set[str] = set()
        for name, ids in name_ids.items():
            if len(ids) == 1:
                unique[name] = next(iter(ids))
            else:
                ambiguous.add(name)
        self._team_rosters[team_vlr_id] = unique
        self._team_ambiguous[team_vlr_id] = ambiguous

    def resolve(
        self,
        handle: str,
        explicit_id: int | None = None,
        *,
        team_vlr_id: int | None = None,
    ) -> int | None:
        normalized = normalize_player_name(handle)
        if not normalized:
            self._record_unresolved(handle)
            return None

        if explicit_id is not None:
            self._record_resolved("id")
            return explicit_id

        if normalized not in self._ambiguous_names:
            roster_id = self._roster_map.get(normalized)
            if roster_id is not None:
                self._record_resolved("event_roster")
                return roster_id

        if team_vlr_id is not None:
            team_ambiguous = self._team_ambiguous.get(team_vlr_id, set())
            if normalized not in team_ambiguous:
                team_id = self._team_rosters.get(team_vlr_id, {}).get(normalized)
                if team_id is not None:
                    self._record_resolved("team_roster")
                    return team_id

        if normalized not in self._known_ambiguous:
            known_id = self._known_handles.get(normalized)
            if known_id is not None:
                self._record_resolved("db_handle")
                return known_id

        if (
            normalized in self._ambiguous_names
            or (
                team_vlr_id is not None
                and normalized in self._team_ambiguous.get(team_vlr_id, set())
            )
            or normalized in self._known_ambiguous
        ):
            self._record_ambiguous(handle)
            return None

        self._record_unresolved(handle)
        return None

    def _record_resolved(self, method: str) -> None:
        if self._diagnostics is None:
            return
        identity = self._diagnostics.player_identity
        if method == "id":
            identity.resolved_by_id += 1
        elif method == "event_roster":
            identity.resolved_by_event_roster += 1
        elif method == "team_roster":
            identity.resolved_by_team_roster += 1
        elif method == "db_handle":
            identity.resolved_by_db_handle += 1

    def _record_unresolved(self, handle: str) -> None:
        if self._diagnostics is None:
            return
        if handle not in self._diagnostics.player_identity.unresolved:
            self._diagnostics.player_identity.unresolved.append(handle)

    def _record_ambiguous(self, handle: str) -> None:
        if self._diagnostics is None:
            return
        if handle not in self._diagnostics.player_identity.ambiguous:
            self._diagnostics.player_identity.ambiguous.append(handle)
