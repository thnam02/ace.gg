from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_UNSAFE_KEY = re.compile(r"[^a-zA-Z0-9._-]+")


class VlrggApiRawCache:
    """Persist raw vlrggapi JSON responses outside canonical DB tables."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def save(self, resource_type: str, resource_id: int, payload: dict[str, Any]) -> Path:
        return self.save_key(resource_type, str(resource_id), payload)

    def load(self, resource_type: str, resource_id: int) -> dict[str, Any] | None:
        return self.load_key(resource_type, str(resource_id))

    def exists(self, resource_type: str, resource_id: int) -> bool:
        return self.exists_key(resource_type, str(resource_id))

    def save_key(self, resource_type: str, resource_key: str, payload: dict[str, Any]) -> Path:
        directory = self._cache_dir / resource_type
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{_safe_cache_key(resource_key)}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_key(self, resource_type: str, resource_key: str) -> dict[str, Any] | None:
        path = self._cache_dir / resource_type / f"{_safe_cache_key(resource_key)}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    def exists_key(self, resource_type: str, resource_key: str) -> bool:
        return (self._cache_dir / resource_type / f"{_safe_cache_key(resource_key)}.json").is_file()


def _safe_cache_key(key: str) -> str:
    cleaned = _UNSAFE_KEY.sub("_", key.strip().lower()).strip("_")
    if not cleaned:
        cleaned = "empty"
    if len(cleaned) > 80:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        cleaned = f"{cleaned[:60]}_{digest}"
    return cleaned
