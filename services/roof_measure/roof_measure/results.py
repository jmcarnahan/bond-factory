"""Result cache: finished envelopes by cache key, plus input-address aliases for the fast path at POST time."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .jobs import ensure_dir, write_json_atomic

KEY_RE = re.compile(r"[0-9a-f]{64}")


class ResultCache:
    def __init__(self, data_dir: str | Path):
        self.root = ensure_dir(Path(data_dir) / "results")

    def _read(self, path: Path) -> Any | None:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def get(self, key: str) -> dict[str, Any] | None:
        return self._read(self.root / f"{key}.json") if KEY_RE.fullmatch(key) else None

    def put(self, key: str, envelope: dict[str, Any]) -> None:
        write_json_atomic(self.root / f"{key}.json", envelope)

    def alias_get(self, alias: str) -> str | None:
        doc = self._read(self.root / f"alias_{alias}.json")
        return doc.get("key") if isinstance(doc, dict) else None

    def alias_put(self, alias: str, key: str) -> None:
        write_json_atomic(self.root / f"alias_{alias}.json", {"key": key})

    def purge(self, days: float, now: float | None = None) -> int:
        """Delete result and alias files not touched for ``days`` days; returns how many."""
        cutoff = (time.time() if now is None else now) - days * 86400
        n = 0
        for f in self.root.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    n += 1
            except OSError:
                continue
        return n
