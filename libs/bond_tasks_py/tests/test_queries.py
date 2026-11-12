from datetime import date, datetime

from conftest import NOW, LinkIndex, Task
from support_read import mk

from bond_tasks_py import TaskCreate, TaskFilters, list_tasks, service, summary

TODAY = date(2026, 11, 8)


def add(session, owner="u1", **fields):
    data = TaskCreate(**{"title": "t", **fields})
    return service.create(session, task_model=Task, owner_user_id=owner, actor_user_id=owner, data=data, now=NOW)


def titles(session, user="u1", limit=25, offset=0, **filters):
    rows, total = list_tasks(session, task_model=Task, user_id=user, filters=TaskFilters(**filters), limit=limit,
                             offset=offset)
    return [t.title for t in rows], total


def seed(session):
    add(session, title="late", due_date=date(2026, 11, 1))
    add(session, title="today-b", due_date=TODAY, due_time="15:00")
    add(session, title="today-a", due_date=TODAY, due_time="09:00")
    add(session, title="later", due_date=date(2026, 11, 20))
    add(session, title="undated")
    add(session, title="theirs", owner="u2", due_date=TODAY)
    add(session, title="given", owner="u2", assigned_user_id="u1", due_date=TODAY)
    done = add(session, title="finished", due_date=TODAY)
    service.complete(session, done, "u1", NOW)
    session.flush()


def test_default_lists_my_open_tasks_soonest_first_undated_last(session):
    seed(session)
    names, total = titles(session)
    assert names[:3] == ["late", "today-a", "today-b"] and names[-1] == "undated" and total == 6
    assert "theirs" not in names and "finished" not in names


def test_scope_all_includes_other_peoples_tasks(session):
    seed(session)
    assert "theirs" in titles(session, scope="all")[0]


def test_status_done_and_all(session):
    seed(session)
    assert titles(session, status="done")[0] == ["finished"]
    assert "finished" in titles(session, status="all")[0]


def test_cancelled_shows_only_under_all(session):
    seed(session)
    service.cancel(session, add(session, title="dropped"), "u1", NOW)
    session.flush()
    assert "dropped" not in titles(session)[0] and "dropped" in titles(session, status="all")[0]


def test_on_or_before_excludes_undated_unless_asked(session):
    seed(session)
    assert titles(session, on_or_before=TODAY)[0] == ["late", "today-a", "today-b", "given"]
    assert titles(session, on_or_before=TODAY, include_undated=True)[0][-1] == "undated"


def test_due_window(session):
    seed(session)
    assert titles(session, due_from=date(2026, 11, 8), due_to=date(2026, 11, 8))[0] == ["today-a", "today-b", "given"]


def test_no_date_filter(session):
    seed(session)
    assert titles(session, no_date=True)[0] == ["undated"]


def test_owner_and_assignee_filters(session):
    seed(session)
    assert sorted(titles(session, scope="all", owner_user_id="u2")[0]) == ["given", "theirs"]
    assert titles(session, scope="all", assigned_user_id="u1")[0] == ["given"]
    assert titles(session, assigned_to_me=True)[0] == ["given"]


def test_paging_reports_the_total(session):
    seed(session)
    names, total = titles(session, limit=2, offset=2)
    assert len(names) == 2 and total == 6


def test_link_filter_lists_everything_on_the_record(session):
    add(session, title="a", links=[{"kind": "loan", "id": "L1"}])
    add(session, title="b", owner="u2", links=[{"kind": "loan", "id": "L1"}])
    add(session, title="c", links=[{"kind": "contact", "id": "L1"}])
    add(session, title="d", links=[{"kind": "loan", "id": "L10"}])
    session.flush()
    assert sorted(titles(session, scope="all", link_kind="loan", link_id="L1")[0]) == ["a", "b"]
    assert titles(session, scope="all", link_id="L1")[1] == 3  # kind is optional
    assert sorted(titles(session, link_id="L1")[0]) == ["a", "c"]  # scope mine stays mine, link filter or not
    assert titles(session, scope="all", link_kind="loan", link_id="L1", limit=1)[1] == 2


def test_link_ids_with_odd_characters_are_matched_exactly(session):
    add(session, title="a", links=[{"kind": "x", "id": "50%_off"}])
    add(session, title="b", links=[{"kind": "x", "id": "50xyoff"}])
    session.flush()
    assert titles(session, scope="all", link_id="50%_off")[0] == ["a"]


def test_summary_counts_my_open_tasks(session):
    seed(session)
    assert summary(session, task_model=Task, user_id="u1", today=TODAY) == {
        "open": 6, "overdue": 1, "due_today": 3, "no_date": 1}


def test_summary_ignores_other_users(session):
    seed(session)
    assert summary(session, task_model=Task, user_id="u3", today=TODAY) == {
        "open": 0, "overdue": 0, "due_today": 0, "no_date": 0}


# --- viewer zone and the link index ---

def viewer_rows(session, zone="America/Los_Angeles", **filters):
    rows, total = list_tasks(session, task_model=Task, user_id="u1", filters=TaskFilters(**filters), viewer_zone=zone)
    return [t.id for t in rows], total


def seed_instants(session):
    mk(session, Task, "none")
    mk(session, Task, "eod", due=date(2026, 3, 11), due_at=datetime(2026, 3, 12, 0))  # date-only, 17:00 in LA
    mk(session, Task, "late-night", due=date(2026, 3, 11), due_time="23:00", due_at=datetime(2026, 3, 12, 6))
    mk(session, Task, "morning", due=date(2026, 3, 11), due_time="08:00", due_at=datetime(2026, 3, 11, 15))
    mk(session, Task, "next", due=date(2026, 3, 12), due_time="08:00", due_at=datetime(2026, 3, 12, 15))
    mk(session, Task, "stale", due=date(2026, 3, 10))  # dated, instant not computed yet


def test_viewer_zone_orders_by_instant_nulls_last(session):
    seed_instants(session)
    ids, total = viewer_rows(session)
    assert ids[:4] == ["morning", "eod", "late-night", "next"] and ids[-2:] == ["none", "stale"] and total == 6
    # the two undated-instant rows tie on created_at, so they come by id


def test_viewer_zone_ranges_use_the_viewers_day(session):
    seed_instants(session)
    # 23:00 on the 11th in LA is 06:00Z on the 12th: still the 11th for an LA viewer, the 12th for UTC
    day = date(2026, 3, 11)
    assert sorted(viewer_rows(session, due_from=day, due_to=day)[0]) == ["eod", "late-night", "morning"]
    assert sorted(viewer_rows(session, "UTC", due_from=day, due_to=day)[0]) == ["eod", "morning"]  # eod: its date
    assert sorted(viewer_rows(session, on_or_before=date(2026, 3, 10))[0]) == ["stale"]
    assert viewer_rows(session, on_or_before=day, include_undated=True)[1] == 5


def test_without_viewer_zone_the_old_ranges_hold(session):
    seed_instants(session)
    day = date(2026, 3, 11)
    rows, _ = list_tasks(session, task_model=Task, user_id="u1", filters=TaskFilters(due_from=day, due_to=day))
    assert sorted(t.id for t in rows) == ["eod", "late-night", "morning"]


def test_summary_with_a_viewer_counts_by_instant(session):
    seed_instants(session)
    got = summary(session, task_model=Task, user_id="u1", today=date(2000, 1, 1), now=datetime(2026, 3, 11, 20, 0),
                  viewer_zone="America/Los_Angeles")
    assert got == {"open": 6, "overdue": 2, "due_today": 2, "no_date": 1}  # morning and stale are overdue


def test_link_filter_through_the_index_pages_in_sql(session):
    for n in range(7):
        link = {"kind": "contact", "id": "c1" if n % 2 == 0 else "c2", "label": "L"}
        mk(session, Task, f"t{n}", links=[link], index_model=LinkIndex)
    mk(session, Task, "other-kind", links=[{"kind": "project", "id": "c1", "label": "P"}], index_model=LinkIndex)
    filters = TaskFilters(link_kind="contact", link_id="c1")
    old, old_total = list_tasks(session, task_model=Task, user_id="u1", filters=filters)
    page, total = list_tasks(session, task_model=Task, user_id="u1", filters=filters, link_index_model=LinkIndex,
                             limit=2, offset=2)
    assert total == old_total == 4 and [t.id for t in page] == [t.id for t in old][2:4]
    anykind, n = list_tasks(session, task_model=Task, user_id="u1", filters=TaskFilters(link_id="c1"),
                            link_index_model=LinkIndex)
    assert n == 5 and len(anykind) == 5
