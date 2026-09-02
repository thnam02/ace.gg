from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.normalizers.vlr_api_parsing import as_dict, as_list, parse_vlr_id
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
        diagnostics: IngestionDiagnostics | None = None,
    ) -> None:
        self._roster_map = dict(roster_map)
        self._ambiguous_names = set(ambiguous_names or ())
        self._known_handles = {
            normalize_player_name(key): value for key, value in (known_handles or {}).items()
        }
        self._diagnostics = diagnostics

    @classmethod
    def from_event_teams(
        cls,
        event_data: dict[str, Any],
        *,
        known_handles: dict[str, int] | None = None,
        diagnostics: IngestionDiagnostics | None = None,
    ) -> PlayerIdentityResolver:
        segments = as_dict(event_data.get("segments"))
        name_ids: dict[str, set[int]] = defaultdict(set)
        for team in as_list(segments.get("teams")):
            team_row = as_dict(team)
            for player in as_list(team_row.get("players")):
                player_row = as_dict(player)
                player_id = parse_vlr_id(player_row.get("id"))
                handle = str(player_row.get("name") or "").strip()
                if player_id is None or not handle:
                    continue
                name_ids[normalize_player_name(handle)].add(player_id)

        ambiguous = {name for name, ids in name_ids.items() if len(ids) > 1}
        roster = {
            name: next(iter(ids))
            for name, ids in name_ids.items()
            if len(ids) == 1
        }
        return cls(
            roster,
            ambiguous_names=ambiguous,
            known_handles=known_handles,
            diagnostics=diagnostics,
        )

    def resolve(self, handle: str, explicit_id: int | None = None) -> int | None:
        normalized = normalize_player_name(handle)
        if not normalized:
            self._record_unresolved(handle)
            return None

        if explicit_id is not None:
            self._record_resolved("id")
            return explicit_id

        if normalized in self._ambiguous_names:
            self._record_ambiguous(handle)
            return None

        roster_id = self._roster_map.get(normalized)
        if roster_id is not None:
            self._record_resolved("roster")
            return roster_id

        known_id = self._known_handles.get(normalized)
        if known_id is not None:
            self._record_resolved("name")
            return known_id

        self._record_unresolved(handle)
        return None

    def _record_resolved(self, method: str) -> None:
        if self._diagnostics is None:
            return
        identity = self._diagnostics.player_identity
        if method == "id":
            identity.resolved_by_id += 1
        elif method == "roster":
            identity.resolved_by_roster += 1
        elif method == "name":
            identity.resolved_by_name += 1

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
