"""Cache layer for per-session facet data with atomic writes."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import SessionFacet


def _default_cache_dir() -> Path:
    """Resolve the default facet cache directory per platform."""
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "opencode-usage" / "facets"


class FacetCache:
    """Per-session facet caching with atomic writes."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize cache with optional custom cache directory."""
        if cache_dir is None:
            cache_dir = _default_cache_dir()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def has(self, session_id: str) -> bool:
        """Check if cached facet exists for session."""
        return (self.cache_dir / f"{session_id}.json").exists()

    def get(self, session_id: str) -> SessionFacet | None:
        """Read and deserialize cached facet, return None if missing or corrupt."""
        json_file = self.cache_dir / f"{session_id}.json"
        if not json_file.exists():
            return None
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            from .types import SessionFacet

            return SessionFacet(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def put(self, session_id: str, facet: SessionFacet) -> None:
        """Atomically write facet to cache using .tmp then os.rename()."""
        data = asdict(facet)
        tmp_path = self.cache_dir / f"{session_id}.json.tmp"
        json_path = self.cache_dir / f"{session_id}.json"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.rename(tmp_path, json_path)

    def clear(self) -> None:
        """Remove all cached *.json files."""
        for json_file in self.cache_dir.glob("*.json"):
            json_file.unlink()
