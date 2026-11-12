"""Keeping task links true when the thing they point at changes."""

from typing import Any


def retarget_links(session: Any, *, task_model: Any, index_model: Any, kind: str, old_id: str, new_id: str,
                   new_label: str | None = None) -> int:
    """Point every link (kind, old_id) at new_id (a merged contact). Returns tasks changed."""
    raise NotImplementedError("links.retarget_links is not implemented yet")


def remove_links(session: Any, *, task_model: Any, index_model: Any, kind: str, ref_id: str) -> int:
    """Drop every link (kind, ref_id) and keep the tasks (a deleted contact). Returns tasks changed."""
    raise NotImplementedError("links.remove_links is not implemented yet")
