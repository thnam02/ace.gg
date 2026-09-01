from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class VLRProvider(Protocol):
    """Source of raw VLR HTML. Only match fetching is implemented for now."""

    def get_match(self, match_id: int) -> str: ...

    def get_event(self, event_id: int) -> str: ...

    def get_event_matches(self, event_id: int) -> str: ...

    def get_player(self, player_id: int) -> str: ...

    def get_team(self, team_id: int) -> str: ...


class UnsupportedVLRResourceError(NotImplementedError):
    pass


class _UnimplementedVLRResources:
    def get_event(self, event_id: int) -> str:
        raise UnsupportedVLRResourceError("Event fetching is not implemented yet.")

    def get_event_matches(self, event_id: int) -> str:
        raise UnsupportedVLRResourceError("Event match listing is not implemented yet.")

    def get_player(self, player_id: int) -> str:
        raise UnsupportedVLRResourceError("Player page fetching is not implemented yet.")

    def get_team(self, team_id: int) -> str:
        raise UnsupportedVLRResourceError("Team page fetching is not implemented yet.")


class StaticVLRProvider(_UnimplementedVLRResources):
    """In-memory VLR match HTML keyed by match ID. No IDs are hard-coded."""

    def __init__(self, matches: Mapping[int, str]) -> None:
        self._matches = dict(matches)

    def get_match(self, match_id: int) -> str:
        try:
            return self._matches[match_id]
        except KeyError as exc:
            raise FileNotFoundError(
                f"No VLR match HTML registered for match_id={match_id}"
            ) from exc


class FileVLRProvider(_UnimplementedVLRResources):
    """Load match HTML from `{match_id}.html` or `{match_id}_*.html` files."""

    def __init__(self, fixtures_dir: str | Path) -> None:
        self._fixtures_dir = Path(fixtures_dir)

    def get_match(self, match_id: int) -> str:
        exact = self._fixtures_dir / f"{match_id}.html"
        if exact.is_file():
            return exact.read_text(encoding="utf-8")

        matches = sorted(self._fixtures_dir.glob(f"{match_id}_*.html"))
        if len(matches) == 1:
            return matches[0].read_text(encoding="utf-8")
        if len(matches) > 1:
            raise FileNotFoundError(
                f"Multiple HTML fixtures found for match_id={match_id} in {self._fixtures_dir}"
            )
        raise FileNotFoundError(f"No VLR match HTML fixture for match_id={match_id}")
