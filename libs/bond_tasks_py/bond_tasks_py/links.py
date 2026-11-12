"""Keeping task links true when the thing they point at changes."""

from typing import Any

from sqlalchemy import select

from bond_tasks_py.link_index import reindex_links


def _tasks_with(session: Any, task_model: Any, index_model: Any, kind: str, ref_id: str) -> list[Any]:
    ids = select(index_model.task_id).where(index_model.kind == kind, index_model.ref_id == ref_id)
    return list(session.execute(select(task_model).where(task_model.id.in_(ids)).order_by(task_model.id)).scalars())


def retarget_links(session: Any, *, task_model: Any, index_model: Any, kind: str, old_id: str, new_id: str,
                   new_label: str | None = None) -> int:
    """Point every link (kind, old_id) at new_id (a merged contact). Returns tasks changed.

    A task that already links ``new_id`` keeps one link (the existing one). The label is left alone unless
    ``new_label`` is given. The JSON list is replaced, not edited, so the change is tracked; the index follows."""
    if old_id == new_id and new_label is None:
        return 0
    tasks = _tasks_with(session, task_model, index_model, kind, old_id)
    for task in tasks:
        has_new = any(k.get("kind") == kind and k.get("id") == new_id for k in task.links or [])
        links: list[dict] = []
        for link in task.links or []:
            if link.get("kind") == kind and link.get("id") == old_id:
                if has_new:
                    continue  # the existing link to new_id stands
                link = {**link, "id": new_id, **({"label": new_label} if new_label is not None else {})}
            elif new_label is not None and has_new and link.get("kind") == kind and link.get("id") == new_id:
                link = {**link, "label": new_label}
            links.append(link)
        task.links = links
        reindex_links(session, index_model, task)
    return len(tasks)


def remove_links(session: Any, *, task_model: Any, index_model: Any, kind: str, ref_id: str) -> int:
    """Drop every link (kind, ref_id) and keep the tasks (a deleted contact). Returns tasks changed."""
    tasks = _tasks_with(session, task_model, index_model, kind, ref_id)
    for task in tasks:
        task.links = [k for k in task.links or [] if not (k.get("kind") == kind and k.get("id") == ref_id)]
        reindex_links(session, index_model, task)
    return len(tasks)
