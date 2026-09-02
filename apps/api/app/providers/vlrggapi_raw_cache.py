from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class VlrggApiRawCache:
    """Persist raw vlrggapi JSON responses outside canonical DB tables."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def save(self, resource_type: str, resource_id: int, payload: dict[str, Any]) -> Path:
        directory = self._cache_dir / resource_type
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{resource_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load(self, resource_type: str, resource_id: int) -> dict[str, Any] | None:
        path = self._cache_dir / resource_type / f"{resource_id}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    def exists(self, resource_type: str, resource_id: int) -> bool:
        return (self._cache_dir / resource_type / f"{resource_id}.json").is_file()
