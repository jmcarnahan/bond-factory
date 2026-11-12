from datetime import datetime

from conftest import LinkIndex, Task
from sqlalchemy import select
from support_read import mk

from bond_tasks_py import TaskCreate, TaskFilters, list_tasks, service
from bond_tasks_py.link_index import make_link_hook, reindex_links
from bond_tasks_py.links import remove_links, retarget_links

NOW = datetime(2026, 11, 8, 12, 0)


def link(id, kind="contact", label=None):
    return {"kind": kind, "id": id, "label": label or f"label-{id}"}


def index_rows(session):
    rows = session.execute(select(LinkIndex.task_id, LinkIndex.kind, LinkIndex.ref_id)).all()
    return sorted(tuple(r) for r in rows)


def assert_index_agrees(session):
    """Every task's links and its index rows say the same set of (kind, id)."""
    expected = sorted((t.id, k["kind"], k["id"]) for t in session.execute(select(Task)).scalars()
                      for k in t.links)
    assert index_rows(session) == sorted(set(expected))


def add(session, id, links):
    return mk(session, Task, id, links=links, index_model=LinkIndex)


def run(fn, session, **kw):
    return fn(session, task_model=Task, index_model=LinkIndex, kind="contact", **kw)


def test_reindex_one_row_per_distinct_pair_and_replaces_old_rows(session):
    task = add(session, "t1", [link("a"), link("b"), link("a", label="again"), link("a", kind="project")])
    assert index_rows(session) == [("t1", "contact", "a"), ("t1", "contact", "b"), ("t1", "project", "a")]
    task.links = [link("c")]
    reindex_links(session, LinkIndex, task)
    assert index_rows(session) == [("t1", "contact", "c")]
    task.links = []
    reindex_links(session, LinkIndex, task)
    assert index_rows(session) == []


def test_hook_keeps_the_index_in_step_with_create_and_update(session):
    hook = make_link_hook(LinkIndex)
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1", now=NOW,
                          data=TaskCreate(title="t", links=[{"kind": "contact", "id": "a", "label": "A"}]),
                          after_write=hook)
    assert index_rows(session) == [(task.id, "contact", "a")]
    hook(session, task)  # idempotent
    assert index_rows(session) == [(task.id, "contact", "a")]


def test_retarget_moves_links_in_json_and_index(session):
    add(session, "only", [link("old")])
    add(session, "several", [link("x"), link("old", label="Old name"), link("y", kind="project")])
    add(session, "other", [link("keep")])
    assert run(retarget_links, session, old_id="old", new_id="new") == 2
    by_id = {t.id: t for t in session.execute(select(Task)).scalars()}
    assert by_id["only"].links == [link("new", label="label-old")]  # label unchanged without new_label
    assert [k["id"] for k in by_id["several"].links] == ["x", "new", "y"]  # others kept, order kept
    assert by_id["other"].links == [link("keep")]
    assert_index_agrees(session)
    rows, total = list_tasks(session, task_model=Task, user_id="u1", link_index_model=LinkIndex,
                             filters=TaskFilters(link_kind="contact", link_id="new"))
    assert total == 2 and {t.id for t in rows} == {"only", "several"}


def test_retarget_with_new_label_and_persisted_as_a_new_list(session):
    task = add(session, "t", [link("old")])
    before = task.links
    run(retarget_links, session, old_id="old", new_id="new", new_label="New name")
    session.commit()
    session.expire_all()
    assert session.get(Task, "t").links == [link("new", label="New name")] and session.get(Task, "t").links is not before


def test_retarget_dedupes_when_the_new_id_is_already_linked(session):
    add(session, "both", [link("old", label="Old"), link("new", label="New")])
    add(session, "both-reversed", [link("new", label="New"), link("old", label="Old")])
    assert run(retarget_links, session, old_id="old", new_id="new") == 2
    for task in session.execute(select(Task)).scalars():
        assert task.links == [link("new", label="New")]
    assert_index_agrees(session)


def test_retarget_leaves_other_kinds_with_the_same_id_alone(session):
    add(session, "t", [link("old", kind="project")])
    assert run(retarget_links, session, old_id="old", new_id="new") == 0
    assert session.get(Task, "t").links == [link("old", kind="project")]


def test_remove_drops_the_link_and_keeps_the_task(session):
    add(session, "only", [link("gone")])
    add(session, "several", [link("gone"), link("stay"), link("gone", kind="project")])
    add(session, "other", [link("stay")])
    assert run(remove_links, session, ref_id="gone") == 2
    by_id = {t.id: t for t in session.execute(select(Task)).scalars()}
    assert by_id["only"].links == []
    assert [(k["kind"], k["id"]) for k in by_id["several"].links] == [("contact", "stay"), ("project", "gone")]
    assert set(by_id) == {"only", "several", "other"}
    assert_index_agrees(session)
    assert run(remove_links, session, ref_id="gone") == 0
