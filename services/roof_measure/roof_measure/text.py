"""Pure text helpers (no heavy imports): file-name slugs and feet-inches formatting."""

from __future__ import annotations

import re


def slug(text: str) -> str:
    """File-name slug of an address or label."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "model"


def ft_in(v: float) -> str:
    total = round(v * 12)
    return f"{total // 12}ft {total % 12}in"
