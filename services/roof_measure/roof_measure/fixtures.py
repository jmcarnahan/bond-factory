"""Fixture-name resolution shared by the service and the job runner (no fastapi)."""

from __future__ import annotations

import re
from pathlib import Path

from .settings import Settings


def fixture_path(settings: Settings, name: str | None) -> Path | None:
    """Resolve a fixture NAME strictly under the fixtures dir; None for no name; ValueError otherwise."""
    if name is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.json", name) or ".." in name:
        raise ValueError("fixture names look like 'site1_blocks.json'")
    path = settings.fixtures_dir / name
    if not path.is_file():
        raise ValueError(f"no fixture {name!r}")
    return path
