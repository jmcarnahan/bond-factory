import logging
import threading
from datetime import UTC, datetime

import pytest
from conftest import Item, make_host, op
from sqlalchemy.exc import DataError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from bond_sync_py import (
    Ctx,
    DbUnavailable,
    Rejected,
    UploadRequest,
    apply,
    is_database_down,
    rejected,
    upload,
)
from bond_sync_py.dispatcher import reject_for


def wire(factory, host, ctx, o):
    return apply(factory, host, ctx, o).wire()


def test_put_ok_and_row_written(factory, host, ctx):
    assert wire(factory, host, ctx, op(title="A")) == {"seq": 0, "status": "ok"}
    with factory() as s:
        assert s.get(Item, "i-1").owner == "user-1"


def test_resolved_id_is_returned(factory, host, ctx):
    assert wire(factory, host, ctx, op(title="resolve"))["resolved_id"] == "server-1"


def test_handler_rejection_keeps_its_code_and_message(factory, host, ctx):
    assert wire(factory, host, ctx, op(title="")) == {
        "seq": 0, "status": "rejected", "code": "invalid", "message": "title_required"}


def test_skipped_already(factory, host, ctx):
    assert wire(factory, host, ctx, op(kind="delete", action="remove", id_="nope")) == {
        "seq": 0, "status": "skipped", "code": "already"}


def test_not_found_from_handler(factory, host, ctx):
    r = wire(factory, host, ctx, op(kind="patch", action="edit", id_="nope", title="x"))
    assert (r["code"], r["message"]) == ("not_found", "Not found")


def test_unknown_table_is_unsupported(factory, host, ctx):
    r = wire(factory, host, ctx, op(table="widgets"))
    assert (r["status"], r["code"], r["message"]) == ("rejected", "unsupported", "Not supported")


def test_op_not_allowed_by_route_is_unsupported(factory, host, ctx):
    assert wire(factory, host, ctx, op(kind="patch", title="x"))["code"] == "unsupported"


def test_rest_only_table_says_use_rest(factory, host, ctx):
    r = wire(factory, host, ctx, op(table="rest"))
    assert (r["code"], r["message"]) == ("unsupported", "Use the REST route")


def test_single_action_table_ignores_stray_action(factory, host, ctx):
    assert wire(factory, host, ctx, op(table="single", action="whatever", title="x"))["status"] == "ok"


def test_multi_action_table_needs_its_action(factory, host, ctx):
    assert wire(factory, host, ctx, op(kind="delete", action="bogus", id_="a"))["code"] == "unsupported"


def test_conflict_when_row_belongs_to_someone_else(factory, host):
    assert apply(factory, host, Ctx(user="other"), op(title="A")).status == "ok"
    r = wire(factory, host, Ctx(user="user-1"), op(title="A"))
    assert (r["status"], r["code"]) == ("rejected", "conflict")


def test_replayed_put_by_same_user_is_ok(factory, host, ctx):
    assert wire(factory, host, ctx, op(title="A"))["status"] == "ok"
    assert wire(factory, host, ctx, op(title="A")) == {"seq": 0, "status": "ok"}


def test_conflict_without_already_written_hook(factory, ctx):
    host = make_host(already_written=None)
    wire(factory, host, ctx, op(title="A"))
    assert wire(factory, host, ctx, op(title="A"))["code"] == "conflict"


@pytest.mark.parametrize("bad", ["", "bad id!", "a.b", "café", "x\n", "x" * 65])
def test_bad_id_is_one_invalid_verdict(factory, host, ctx, bad):
    r = wire(factory, host, ctx, op(id_=bad, title="A"))
    assert (r["status"], r["code"]) == ("rejected", "invalid")


@pytest.mark.parametrize("data", [{"title": "a\x00b"}, {"title": "ok", "meta": '{"a": "\\u0000"}'}, {"title": "ok", "meta": "[\"a\x00\"]"}])
def test_nul_byte_is_invalid(factory, host, ctx, data):
    assert wire(factory, host, ctx, op(**data))["code"] == "invalid"


@pytest.mark.parametrize(
    "data",
    [{"title": 5}, {"title": "x", "count": "abc"}, {"title": "x", "count": 1.5}, {"title": "x", "flag": "maybe"},
     {"title": "x", "meta": "{not json"}],
)
def test_wrong_shapes_are_invalid(factory, host, ctx, data):
    assert wire(factory, host, ctx, op(**data))["code"] == "invalid"


def test_client_values_are_coerced(factory, host, ctx):
    assert wire(factory, host, ctx, op(title="x", count="7", flag=1, meta='{"a": 1}'))["status"] == "ok"
    with factory() as s:
        row = s.get(Item, "i-1")
        assert (row.count, row.flag, row.meta) == (7, True, '{"a": 1}')


def test_unused_malformed_column_cannot_reject(factory, host, ctx):
    assert wire(factory, host, ctx, op(title="x", unrelated=object.__name__))["status"] == "ok"


def test_unmapped_bug_is_server_error_and_logged_once(factory, host, ctx, caplog):
    caplog.set_level(logging.WARNING)
    r = wire(factory, host, ctx, op(table="bugs", id_="bug-1"))
    assert (r["status"], r["code"]) == ("rejected", "server_error")
    wire(factory, host, ctx, op(table="bugs", id_="bug-1"))
    levels = [rec.levelname for rec in caplog.records if "unexpected" in rec.getMessage()]
    assert levels == ["ERROR", "WARNING"]


def _exc(cls, orig=None, **kw):
    return cls("stmt", {}, orig or Exception("x"), **kw)


class Orig(Exception):
    def __init__(self, sqlstate=None):
        super().__init__("db")
        self.sqlstate = sqlstate


@pytest.mark.parametrize("state", ["08006", "40001", "53300", "57P01", None])
def test_database_down_classes_escape(state):
    assert is_database_down(_exc(OperationalError, Orig(state)))


@pytest.mark.parametrize("state", ["57014", "55P03", "23505"])
def test_per_op_sqlstates_are_not_down(state):
    assert not is_database_down(_exc(OperationalError, Orig(state)))


def test_interface_error_and_pool_timeout_are_down():
    assert is_database_down(_exc(InterfaceError))
    assert is_database_down(PoolTimeout("pool exhausted"))
    assert not is_database_down(RuntimeError("x"))


def test_db_down_escapes_apply_as_db_unavailable(factory, ctx):
    def handler(session, ctx_, op_, data):
        raise _exc(OperationalError, Orig("08006"))

    from bond_sync_py import Host, Route

    host = Host(routes={("t", None): Route(frozenset({"put"}), handler)})
    with pytest.raises(DbUnavailable):
        apply(factory, host, ctx, op(table="t"))


def test_statement_timeout_is_server_error_not_escape(factory, ctx):
    def handler(session, ctx_, op_, data):
        raise _exc(OperationalError, Orig("57014"))

    from bond_sync_py import Host, Route

    host = Host(routes={("t", None): Route(frozenset({"put"}), handler)})
    assert wire(factory, host, ctx, op(table="t"))["code"] == "server_error"


def test_host_reject_for_maps_app_errors_first(factory, ctx):
    class Limited(Exception):
        pass

    def handler(session, ctx_, op_, data):
        raise Limited()

    from bond_sync_py import Host, Route

    host = Host(
        routes={("t", None): Route(frozenset({"put"}), handler)},
        reject_for=lambda s, u, o, e: rejected(o.seq, "rate_limited", "Slow down") if isinstance(e, Limited) else None,
    )
    r = wire(factory, host, ctx, op(table="t"))
    assert (r["code"], r["message"]) == ("rate_limited", "Slow down")


def test_data_error_and_integrity_mapping(factory, host):
    o = op(title="x")
    assert reject_for(host, None, "u", o, _exc(DataError)).code == "invalid"
    assert reject_for(host, None, "u", op(kind="patch"), _exc(IntegrityError)).code == "conflict"
    assert reject_for(host, None, "u", o, Rejected("m", code="forbidden")).code == "forbidden"


def test_upload_applies_in_seq_order_and_one_result_each(factory, host, ctx):
    body = UploadRequest(ops=[
        op(seq=2, kind="delete", action="remove", id_="a"),
        op(seq=1, title="A", id_="a"),
    ])
    out = upload(factory, host, ctx, body).wire()
    assert [(r["seq"], r["status"]) for r in out["results"]] == [(1, "ok"), (2, "ok")]
    assert out["server_now"].endswith("Z")


def test_a_refused_op_never_stops_the_next(factory, host, ctx):
    body = UploadRequest(ops=[op(seq=0, title=""), op(seq=1, title="ok", id_="b")])
    statuses = [r.status for r in upload(factory, host, ctx, body).results]
    assert statuses == ["rejected", "ok"]


def test_sqlite_bug_is_a_server_error_not_database_down(factory, ctx):
    import sqlite3

    def handler(session, ctx_, op_, data):
        raise OperationalError("select", {}, sqlite3.OperationalError("no such table: nope"))

    from bond_sync_py import Host, Route

    host = Host(routes={("t", None): Route(frozenset({"put"}), handler)})
    assert wire(factory, host, ctx, op(table="t"))["code"] == "server_error"


@pytest.mark.parametrize("message", ["database is locked", "unable to open database file"])
def test_sqlite_locked_or_unopenable_is_down(message):
    import sqlite3

    assert is_database_down(OperationalError("select", {}, sqlite3.OperationalError(message)))
    assert not is_database_down(OperationalError("select", {}, sqlite3.OperationalError("no such column: x")))


def test_failing_rollback_or_hook_is_a_verdict_not_a_raw_error(factory, ctx):
    from bond_sync_py import Host, Route

    def bad_handler(session, ctx_, op_, data):
        raise RuntimeError("bug")

    def bad_hook(session, user, op_, exc):
        raise LookupError("hook broke")

    host = Host(routes={("t", None): Route(frozenset({"put"}), bad_handler)}, reject_for=bad_hook)
    assert wire(factory, host, ctx, op(table="t"))["code"] == "server_error"

    def down_hook(session, user, op_, exc):
        raise _exc(OperationalError, Orig("08006"))

    host = Host(routes={("t", None): Route(frozenset({"put"}), bad_handler)}, reject_for=down_hook)
    with pytest.raises(DbUnavailable):
        apply(factory, host, ctx, op(table="t"))


def test_handler_keyerror_is_logged_once_and_still_a_verdict(factory, ctx, caplog):
    from bond_sync_py import Host, Route

    def handler(session, ctx_, op_, data):
        return {}["missing"]

    host = Host(routes={("keyerr_table", None): Route(frozenset({"put"}), handler)})
    caplog.set_level(logging.ERROR)
    assert wire(factory, host, ctx, op(table="keyerr_table"))["code"] == "invalid"
    wire(factory, host, ctx, op(table="keyerr_table", id_="i-2"))
    records = [r for r in caplog.records if "handler raised KeyError" in r.getMessage()]
    assert len(records) == 1
    assert records[0].exc_info is not None


def test_bad_client_value_is_not_logged_as_a_handler_bug(factory, host, ctx, caplog):
    caplog.set_level(logging.ERROR)
    assert wire(factory, host, ctx, op(title="x", count="abc"))["code"] == "invalid"
    assert [r for r in caplog.records if "handler raised" in r.getMessage()] == []


def test_mid_batch_db_down_keeps_earlier_ops_and_skips_later(factory, ctx):
    from conftest import _put

    from bond_sync_py import Host, Route

    def down(session, ctx_, op_, data):
        raise _exc(OperationalError, Orig("08006"))

    host = Host(routes={("items", None): Route(frozenset({"put"}), _put, ("title",)),
                        ("down", None): Route(frozenset({"put"}), down)})
    body = UploadRequest(ops=[op(seq=0, title="a", id_="a"), op(seq=1, table="down", id_="d"),
                              op(seq=2, title="c", id_="c")])
    with pytest.raises(DbUnavailable):
        upload(factory, host, ctx, body)
    with factory() as s:
        assert s.get(Item, "a") is not None
        assert s.get(Item, "c") is None


class _Spy:
    """A session wrapper that counts close() calls."""

    def __init__(self, inner):
        self._inner = inner
        self.closed = 0

    def close(self):
        self.closed += 1
        self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _spy_factory(factory):
    made = []

    def make():
        spy = _Spy(factory())
        made.append(spy)
        return spy

    return make, made


def test_apply_closes_the_session_by_default(factory, host, ctx):
    make, made = _spy_factory(factory)
    assert apply(make, host, ctx, op(title="A")).status == "ok"
    assert [s.closed for s in made] == [1]


def test_apply_keeps_session_open_when_asked(factory, host, ctx):
    make, made = _spy_factory(factory)
    assert apply(make, host, ctx, op(title="A"), close_sessions=False).status == "ok"
    assert apply(make, host, ctx, op(seq=1, id_="i-2", title=""), close_sessions=False).status == "rejected"
    assert [s.closed for s in made] == [0, 0]
    with factory() as s:
        assert s.get(Item, "i-1") is not None  # committed even though not closed


def test_upload_passes_close_sessions_through(factory, host, ctx):
    make, made = _spy_factory(factory)
    upload(make, host, ctx, UploadRequest(ops=[op(title="A"), op(seq=1, id_="i-2", title="B")]), close_sessions=False)
    assert [s.closed for s in made] == [0, 0]


def test_upload_server_now_follows_injected_clock(factory, host, ctx):
    pinned = datetime(2030, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)
    resp = upload(factory, host, ctx, UploadRequest(ops=[op(title="A")]), now=lambda: pinned)
    assert resp.server_now == "2030-01-02T03:04:05.678Z"
    assert upload(factory, host, ctx, UploadRequest(ops=[])).server_now != resp.server_now  # default is the real clock


def test_empty_reads_coerces_every_key(factory, ctx):
    from conftest import _put

    from bond_sync_py import Route

    host = make_host(routes={("items", None): Route(frozenset({"put"}), _put)})  # reads left empty
    assert apply(factory, host, ctx, op(title="A", count="not a number")).wire() == {
        "seq": 0, "status": "rejected", "code": "invalid", "message": "invalid"}
    restricted = make_host(routes={("items", None): Route(frozenset({"put"}), _put, ("title",))})
    assert apply(factory, restricted, ctx, op(id_="i-2", title="A", count="not a number")).status == "ok"


def test_logged_bugs_logs_once_across_threads():
    from bond_sync_py import LoggedBugs

    bugs = LoggedBugs()
    firsts = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        firsts.append(bugs.first_time("items", "i-1"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert firsts.count(True) == 1
    assert bugs.first_time("items", "i-2") is True


def test_logged_bugs_evicts_the_oldest():
    from bond_sync_py import LoggedBugs

    bugs = LoggedBugs(maximum=2)
    assert bugs.first_time("t", "a") and bugs.first_time("t", "b")
    assert bugs.first_time("t", "c")  # evicts a
    assert bugs.first_time("t", "a")  # a was forgotten, so it is new again (evicts b)
    assert not bugs.first_time("t", "c")  # c is still remembered


def test_db_unavailable_flag():
    assert DbUnavailable.db_unavailable is True
    assert getattr(DbUnavailable("down"), "db_unavailable", False) is True
    assert getattr(ValueError("x"), "db_unavailable", False) is False
