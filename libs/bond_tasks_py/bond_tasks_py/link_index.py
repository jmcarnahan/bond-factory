"""Link index: one row per (task, kind, ref) so "tasks linked to X" is an indexed join, not a JSON text match.

Rebuilt in the same write as the task: delete the task's rows, insert the new ones.
"""

from typing import Any

from sqlalchemy import Column, Index, String
from sqlalchemy.orm import declared_attr

from bond_tasks_py.protocols import AfterWrite

#: column name -> nullable. The literal contract of ``task_link_index``; tests pin it.
TASK_LINK_INDEX_COLUMNS: dict[str, bool] = {
    "task_id": False,
    "kind": False,
    "ref_id": False,
}


class TaskLinkIndexMixin:
    __tablename__ = "task_link_index"

    @declared_attr.directive
    def __table_args__(cls):
        return (Index("ix_task_link_ref", "kind", "ref_id", "task_id"),)

    task_id = Column(String, primary_key=True)
    kind = Column(String(32), primary_key=True)
    ref_id = Column(String(128), primary_key=True)


def reindex_links(session: Any, index_model: Any, task: Any) -> None:
    """Replace the task's index rows with its current ``links``."""
    raise NotImplementedError("link_index.reindex_links is not implemented yet")


def make_link_hook(index_model: Any) -> AfterWrite:
    """An ``after_write`` hook that calls ``reindex_links``."""
    raise NotImplementedError("link_index.make_link_hook is not implemented yet")
