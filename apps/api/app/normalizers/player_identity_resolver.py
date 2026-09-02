from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.normalizers.vlr_api_parsing import (
    as_dict,
    as_list,
    normalize_player_name,
    parse_team_roster_players,
    parse_vlr_id,
)
from app.schemas.ingestion_diagnostics import IngestionDiagnostics

if TYPE_CHECKING:
    from app.services.historical_player_identity import HistoricalPlayerIdentityResolver


class PlayerIdentityResolver:
    """Resolve VLR player IDs with explicit priority and diagnostics."""

    def __init__(
        self,
        roster_map: dict[str, int],
        *,
        ambiguous_names: set[str] | None = None,
        known_handles: dict[str, int] | None = None,
        known_ambiguous: set[str] | None = None,
        history_index: dict[tuple[str, int], set[int]] | None = None,
        player_teams: dict[int, set[int]] | None = None,
        identity_lookup: HistoricalPlayerIdentityResolver | None = None,
        diagnostics: IngestionDiagnostics | None = None,
    ) -> None:
        self._roster_map = dict(roster_map)
        self._ambiguous_names = set(ambiguous_names or ())
        self._known_handles = {
            normalize_player_name(key): value for key, value in (known_handles or {}).items()
        }
        self._known_ambiguous = {normalize_player_name(name) for name in (known_ambiguous or ())}
        self._history_index: dict[tuple[str, int], set[int]] = defaultdict(set)
        for key, ids in (history_index or {}).items():
            self._history_index[key] = set(ids)
        self._player_teams: dict[int, set[int]] = defaultdict(set)
        for player_id, teams in (player_teams or {}).items():
            self._player_teams[player_id] = set(teams)
        self._identity_lookup = identity_lookup
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
        history_index: dict[tuple[str, int], set[int]] | None = None,
        player_teams: dict[int, set[int]] | None = None,
        identity_lookup: HistoricalPlayerIdentityResolver | None = None,
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
            history_index=history_index,
            player_teams=player_teams,
            identity_lookup=identity_lookup,
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

    def remember(self, handle: str, team_vlr_id: int | None, player_id: int) -> None:
        normalized = normalize_player_name(handle)
        if not normalized:
            return
        self._known_handles.setdefault(normalized, player_id)
        if team_vlr_id is None:
            return
        self._history_index[(normalized, team_vlr_id)].add(player_id)
        self._player_teams[player_id].add(team_vlr_id)

    def resolve(
        self,
        handle: str,
        explicit_id: int | None = None,
        *,
        team_vlr_id: int | None = None,
        team_name: str | None = None,
        team_tag: str | None = None,
        match_date: datetime | None = None,
        event_id: int | None = None,
    ) -> int | None:
        normalized = normalize_player_name(handle)
        if not normalized:
            self._record_unresolved(handle)
            return None

        if explicit_id is not None:
            self._record_resolved("id")
            self.remember(handle, team_vlr_id, explicit_id)
            return explicit_id

        if normalized not in self._ambiguous_names:
            roster_id = self._roster_map.get(normalized)
            if roster_id is not None:
                self._record_resolved("event_roster")
                self.remember(handle, team_vlr_id, roster_id)
                return roster_id

        if team_vlr_id is not None:
            team_ambiguous = self._team_ambiguous.get(team_vlr_id, set())
            if normalized not in team_ambiguous:
                team_id = self._team_rosters.get(team_vlr_id, {}).get(normalized)
                if team_id is not None:
                    self._record_resolved("team_roster")
                    self.remember(handle, team_vlr_id, team_id)
                    return team_id

        if team_vlr_id is not None:
            history_ids = self._history_index.get((normalized, team_vlr_id), set())
            if len(history_ids) == 1:
                history_id = next(iter(history_ids))
                self._record_resolved("history")
                self.remember(handle, team_vlr_id, history_id)
                return history_id
            if len(history_ids) > 1:
                self._record_ambiguous(handle)
                return None

        if normalized not in self._known_ambiguous:
            known_id = self._known_handles.get(normalized)
            if (
                known_id is not None
                and team_vlr_id is not None
                and team_vlr_id in self._player_teams.get(known_id, set())
            ):
                self._record_resolved("db_identity")
                self.remember(handle, team_vlr_id, known_id)
                return known_id

        if self._identity_lookup is not None:
            from app.services.historical_player_identity import IdentityLookupStatus

            result = self._identity_lookup.lookup(
                handle,
                match_team_id=team_vlr_id,
                match_date=match_date,
                event_id=event_id,
                team_name=team_name,
                team_tag=team_tag,
            )
            if result.status is IdentityLookupStatus.RESOLVED and result.vlr_player_id is not None:
                self._record_resolved("search")
                self.remember(handle, team_vlr_id, result.vlr_player_id)
                return result.vlr_player_id
            if result.status is IdentityLookupStatus.AMBIGUOUS:
                self._record_ambiguous(handle)
                return None

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
        elif method == "history":
            identity.resolved_by_history += 1
        elif method == "db_identity":
            identity.resolved_by_db_identity += 1
        elif method == "search":
            identity.resolved_by_search += 1

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
