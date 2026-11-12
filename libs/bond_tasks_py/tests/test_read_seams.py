"""``extra_where`` and the cancelled / active filters on ``list_tasks``; ``labels`` on ``task_items``."""

from datetime import date

from conftest import NOW, Task
from support_core import HostTask
from support_read import mk

from bond_tasks_py import TaskFilters, list_tasks, task_item, task_items

DAY = date(2026, 11, 9)


def listing(session, model=Task, filters=None, **kw):
    return list_tasks(session, task_model=model, user_id="u1", filters=filters, now=NOW, **kw)


def test_list_extra_where_filters_and_counts(host_session):
    session = host_session
    for i in range(5):
        mk(session, HostTask, f"t{i}", due=DAY, contact_id="c1" if i % 2 == 0 else "c2")
    rows, total = listing(session, HostTask, extra_where=[HostTask.contact_id == "c1"], limit=2)
    assert total == 3 and len(rows) == 2 and {r.contact_id for r in rows} == {"c1"}
    rows, total = listing(session, HostTask, extra_where=(HostTask.contact_id == "c1", HostTask.title != "t0"))
    assert total == 2
    rows, total = listing(session, HostTask)  # default unchanged
    assert total == 5


def test_extra_where_also_applies_with_a_link_filter(host_session):
    session = host_session
    link = [{"kind": "contact", "id": "k1", "label": "K"}]
    mk(session, HostTask, "a", links=link, contact_id="c1")
    mk(session, HostTask, "b", links=link, contact_id="c2")
    rows, total = listing(session, HostTask, TaskFilters(link_id="k1"), extra_where=[HostTask.contact_id == "c2"])
    assert [r.id for r in rows] == ["b"] and total == 1


def test_status_cancelled_and_active(session):
    for status in ("open", "done", "cancelled"):
        mk(session, Task, status, status=status)
    ids = lambda status: sorted(t.id for t in listing(session, filters=TaskFilters(status=status))[0])
    assert ids("cancelled") == ["cancelled"]
    assert ids("active") == ["done", "open"]
    assert ids("all") == ["cancelled", "done", "open"]
    assert ids("open") == ["open"] and ids("done") == ["done"]


def test_labels_replace_a_stale_label_and_leave_others(session):
    a = mk(session, Task, "a", links=[{"kind": "contact", "id": "c1", "label": "Old"},
                                      {"kind": "loan", "id": "l1", "label": "Loan 1"}])
    b = mk(session, Task, "b", links=[{"kind": "contact", "id": "c1", "label": "Older"}])
    c = mk(session, Task, "c")
    calls = []

    def labels(links):
        calls.append(links)
        return {("contact", "c1"): "New", ("loan", "zzz"): "unused"}

    items = task_items([a, b, c], today=DAY, now=NOW, labels=labels)
    assert len(calls) == 1 and len(calls[0]) == 3
    assert items[0]["links"] == [{"kind": "contact", "id": "c1", "label": "New"},
                                 {"kind": "loan", "id": "l1", "label": "Loan 1"}]
    assert items[1]["links"][0]["label"] == "New" and items[2]["links"] == []
    assert a.links[0]["label"] == "Old"  # the stored row is not touched
    assert task_items([a], today=DAY, now=NOW)[0]["links"][0]["label"] == "Old"
    assert task_item(a, today=DAY, now=NOW, labels={("loan", "l1"): "L"})["links"][1]["label"] == "L"


def test_labels_not_called_when_the_page_has_no_links(session):
    task = mk(session, Task, "c")
    task_items([task], today=DAY, now=NOW, labels=lambda links: (_ for _ in ()).throw(AssertionError))
