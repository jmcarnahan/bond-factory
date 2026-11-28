"""Pure text helpers (no heavy imports): the file-name slug."""

from __future__ import annotations

import re


def slug(text: str) -> str:
    """File-name slug of an address or label."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "model"
