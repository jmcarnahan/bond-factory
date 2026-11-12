"""Link index: one row per (task, kind, ref) so "tasks linked to X" is an indexed join, not a JSON text match.

Rebuilt in the same write as the task: delete the task's rows, insert the new ones.
"""

from typing import Any

from sqlalchemy import Column, Index, String, delete
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
    """Replace the task's index rows with its current ``links``: one row per distinct (kind, id). Flushes."""
    session.flush()  # a pending task or earlier index rows must be visible to the delete below
    session.execute(delete(index_model).where(index_model.task_id == task.id))
    pairs = {(str(link["kind"]), str(link["id"])) for link in task.links or [] if link.get("kind") and link.get("id")}
    session.add_all(index_model(task_id=task.id, kind=kind, ref_id=ref) for kind, ref in sorted(pairs))
    session.flush()


def make_link_hook(index_model: Any) -> AfterWrite:
    """An ``after_write`` hook that calls ``reindex_links``."""

    def hook(session: Any, task: Any) -> None:
        reindex_links(session, index_model, task)

    return hook
