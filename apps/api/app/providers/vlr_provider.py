from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class VLRProvider(Protocol):
    """Source of raw VLR HTML."""

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
    """In-memory VLR HTML keyed by resource ID."""

    def __init__(
        self,
        matches: Mapping[int, str],
        *,
        events: Mapping[int, str] | None = None,
        event_matches: Mapping[int, str] | None = None,
    ) -> None:
        self._matches = dict(matches)
        self._events = dict(events or {})
        self._event_matches = dict(event_matches or {})

    def get_match(self, match_id: int) -> str:
        try:
            return self._matches[match_id]
        except KeyError as exc:
            raise FileNotFoundError(
                f"No VLR match HTML registered for match_id={match_id}"
            ) from exc

    def get_event(self, event_id: int) -> str:
        try:
            return self._events[event_id]
        except KeyError as exc:
            raise FileNotFoundError(
                f"No VLR event HTML registered for event_id={event_id}"
            ) from exc

    def get_event_matches(self, event_id: int) -> str:
        if event_id in self._event_matches:
            return self._event_matches[event_id]
        if event_id in self._events:
            return self._events[event_id]
        raise FileNotFoundError(
            f"No VLR event match listing registered for event_id={event_id}"
        )


class FileVLRProvider(_UnimplementedVLRResources):
    """Load VLR HTML fixtures from disk."""

    def __init__(
        self,
        matches_dir: str | Path,
        *,
        events_dir: str | Path | None = None,
    ) -> None:
        self._matches_dir = Path(matches_dir)
        if events_dir is not None:
            events_path = Path(events_dir)
        else:
            events_path = self._matches_dir.parent / "events"
        self._events_dir = events_path

    def get_match(self, match_id: int) -> str:
        return self._read_fixture(self._matches_dir, match_id, resource_label="match")

    def get_event(self, event_id: int) -> str:
        return self._read_fixture(self._events_dir, event_id, resource_label="event")

    def get_event_matches(self, event_id: int) -> str:
        matches_fixture = self._events_dir / f"{event_id}_matches.html"
        if matches_fixture.is_file():
            return matches_fixture.read_text(encoding="utf-8")
        return self.get_event(event_id)

    def _read_fixture(self, directory: Path, resource_id: int, *, resource_label: str) -> str:
        exact = directory / f"{resource_id}.html"
        if exact.is_file():
            return exact.read_text(encoding="utf-8")

        matches = sorted(
            path
            for path in directory.glob(f"{resource_id}_*.html")
            if not path.name.endswith("_matches.html")
        )
        if len(matches) == 1:
            return matches[0].read_text(encoding="utf-8")
        if len(matches) > 1:
            raise FileNotFoundError(
                f"Multiple HTML fixtures found for {resource_label}_id={resource_id} in {directory}"
            )
        raise FileNotFoundError(
            f"No VLR {resource_label} HTML fixture for {resource_label}_id={resource_id}"
        )
