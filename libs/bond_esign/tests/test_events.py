import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import NOW, T, new_request
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from bond_esign import KINDS, RequestContext, append, canonical, chain, events, row_hash, verify_chain


def make(session, pdf_bytes):
    request = new_request(session, pdf_bytes)  # writes the "created" event as seq 1
    return request


def test_kinds_are_the_fifteen_of_the_contract():
    assert len(KINDS) == 15 and len(set(KINDS)) == 15
    assert set(KINDS) == {
        "created", "token_issued", "viewed", "code_sent", "code_verified", "code_failed", "consent_given",
        "signed", "declined", "voided", "expired", "document_built", "completed", "copy_delivered", "downloaded",
    }  # fmt: skip


def test_first_event_links_to_zeros_and_each_row_to_the_one_before(session, pdf_bytes):
    request = make(session, pdf_bytes)
    first = chain(session, T, request)[0]
    assert (first.seq, first.kind, first.prev_hash) == (1, "created", "0" * 64)
    second = append(session, T, request, events.VIEWED, data={"n": 1}, now=NOW + timedelta(seconds=5))
    assert (second.seq, second.prev_hash) == (2, first.row_hash)
    assert verify_chain(session, T, request).ok and verify_chain(session, T, request).count == 2


def test_hash_is_sha256_of_prev_plus_canonical_json_with_pinned_shape(session, pdf_bytes):
    request = make(session, pdf_bytes)
    ctx = RequestContext(ip="203.0.113.5", user_agent="UA/1", actor="staff-1")
    ev = append(session, T, request, events.VIEWED, ctx=ctx, data={"b": 1, "a": "é"}, now=NOW)
    payload = {
        "request_id": request.id, "seq": ev.seq, "signer_id": None, "kind": "viewed",
        "at": "2026-11-08T10:00:00Z", "ip": "203.0.113.5", "user_agent": "UA/1", "actor": "staff-1",
        "data": {"b": 1, "a": "é"},
    }  # fmt: skip
    assert canonical(payload) == json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert b'"a":"\xc3\xa9"' in canonical(payload)  # UTF-8, not é
    assert ev.row_hash == row_hash(ev.prev_hash, payload)


def test_at_is_whole_seconds_utc_and_round_trips(session, pdf_bytes):
    request = make(session, pdf_bytes)
    aware = datetime(2026, 11, 8, 5, 0, 7, 654321, tzinfo=timezone(timedelta(hours=-5)))
    ev = append(session, T, request, events.VIEWED, now=aware)
    assert ev.at == datetime(2026, 11, 8, 10, 0, 7) and ev.at.tzinfo is None
    session.expire_all()
    assert verify_chain(session, T, request).ok


def test_floats_and_foreign_types_are_rejected_so_the_hash_cannot_drift(session, pdf_bytes):
    request = make(session, pdf_bytes)
    for bad in ({"x": 1.5}, {"x": [1, {"y": 2.0}]}, {"x": datetime(2026, 1, 1)}, {1: "a"}, {"x": {"y": b"z"}}):
        with pytest.raises(TypeError):
            append(session, T, request, events.VIEWED, data=bad, now=NOW)
    assert len(chain(session, T, request)) == 1  # nothing was written
    ok = append(session, T, request, events.VIEWED, data={"a": [1, True, None, "s", {"k": 0}]}, now=NOW)
    assert ok.data == {"a": [1, True, None, "s", {"k": 0}]}


def test_unknown_kind_is_refused(session, pdf_bytes):
    with pytest.raises(ValueError):
        append(session, T, make(session, pdf_bytes), "invented", now=NOW)


def _chain_of_four(session, pdf_bytes):
    request = make(session, pdf_bytes)
    for n in range(3):
        append(session, T, request, events.VIEWED, data={"n": n}, now=NOW + timedelta(seconds=n + 1))
    session.commit()
    return request


def _tamper(session, sql, **params):
    session.execute(text(sql), params)
    session.commit()
    session.expire_all()


def test_tampering_with_data_is_found_at_that_seq(session, pdf_bytes):
    request = _chain_of_four(session, pdf_bytes)
    assert verify_chain(session, T, request).ok
    _tamper(session, "update esign_events set data=:d where seq=3", d=json.dumps({"n": 99}))
    check = verify_chain(session, T, request)
    assert (check.ok, check.count, check.broken_seq) == (False, 4, 3)


def test_editing_only_the_prev_hash_of_a_middle_row_is_found_at_that_seq(session, pdf_bytes):
    request = _chain_of_four(session, pdf_bytes)
    _tamper(session, "update esign_events set prev_hash=:p where seq=3", p="f" * 64)
    check = verify_chain(session, T, request)
    assert (check.ok, check.count, check.broken_seq) == (False, 4, 3)


def test_a_forged_gap_with_recomputed_hashes_is_still_found_by_the_seq_check(session, pdf_bytes):
    """Delete seq 2 and re-hash 3 and 4 against their new predecessors: only ``seq == position`` sees it."""
    request = _chain_of_four(session, pdf_bytes)
    rows = chain(session, T, request)
    prev = rows[0].row_hash
    _tamper(session, "delete from esign_events where seq=2")
    for row in rows[2:]:
        payload = events._payload(row.request_id, row.seq, row.signer_id, row.kind, row.at, row.ip, row.user_agent,
                                  row.actor, row.data)  # fmt: skip
        new = row_hash(prev, payload)
        _tamper(session, "update esign_events set prev_hash=:p, row_hash=:h where seq=:s", p=prev, h=new, s=row.seq)
        prev = new
    check = verify_chain(session, T, request)
    assert (check.ok, check.count, check.broken_seq) == (False, 3, 2)


def test_swapping_two_seq_values_is_found_at_the_first_swapped_position(session, pdf_bytes):
    request = _chain_of_four(session, pdf_bytes)
    _tamper(session, "update esign_events set seq=99 where seq=3")
    _tamper(session, "update esign_events set seq=3 where seq=4")
    _tamper(session, "update esign_events set seq=4 where seq=99")
    assert verify_chain(session, T, request).broken_seq == 3


def test_moving_the_last_event_of_one_request_onto_another_breaks_the_other_chain_at_that_seq(session, pdf_bytes):
    a, b = new_request(session, pdf_bytes), new_request(session, pdf_bytes)
    append(session, T, a, events.VIEWED, data={}, now=NOW + timedelta(seconds=5))
    moved = chain(session, T, a)[-1]
    assert moved.seq == 2 and len(chain(session, T, b)) == 1  # b lacks seq 2
    _tamper(session, "update esign_events set request_id=:b where id=:i", b=b.id, i=moved.id)
    check = verify_chain(session, T, b)
    assert (check.ok, check.count, check.broken_seq) == (False, 2, 2)
    assert verify_chain(session, T, a).ok  # dropping the newest row of a is invisible to its own chain

def test_tampering_with_at_is_found_at_that_seq(session, pdf_bytes):
    request = _chain_of_four(session, pdf_bytes)
    _tamper(session, "update esign_events set at='2026-11-08 11:11:11' where seq=2")
    assert verify_chain(session, T, request).broken_seq == 2


def test_swapping_two_rows_seq_is_found_at_the_first_swapped_position(session, pdf_bytes):
    request = _chain_of_four(session, pdf_bytes)
    _tamper(session, "update esign_events set seq=99 where seq=2")
    _tamper(session, "update esign_events set seq=2 where seq=3")
    _tamper(session, "update esign_events set seq=3 where seq=99")
    check = verify_chain(session, T, request)
    assert (check.ok, check.broken_seq) == (False, 2)


def test_a_deleted_middle_row_is_a_gap_and_found(session, pdf_bytes):
    request = _chain_of_four(session, pdf_bytes)
    _tamper(session, "delete from esign_events where seq=2")
    check = verify_chain(session, T, request)
    assert (check.ok, check.count, check.broken_seq) == (False, 3, 2)


def test_a_rewritten_row_with_a_recomputed_own_hash_still_breaks_the_next_link(session, pdf_bytes):
    request = _chain_of_four(session, pdf_bytes)
    rows = chain(session, T, request)
    forged = {
        "request_id": request.id, "seq": 2, "signer_id": None, "kind": "viewed", "at": "2026-11-08T10:00:01Z",
        "ip": None, "user_agent": None, "actor": None, "data": {"n": 42},
    }  # fmt: skip
    _tamper(session, "update esign_events set data=:d, row_hash=:h where seq=2", d=json.dumps({"n": 42}),
            h=row_hash(rows[1].prev_hash, forged))  # fmt: skip
    assert verify_chain(session, T, request).broken_seq == 3


def test_duplicate_seq_is_an_integrity_error_not_a_silent_second_row(session, pdf_bytes):
    request = make(session, pdf_bytes)
    session.commit()
    dup = T.event(request_id=request.id, seq=1, kind="viewed", at=NOW, data={}, prev_hash="0" * 64, row_hash="f" * 64)
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    assert len(chain(session, T, request)) == 1


def test_events_are_deleted_only_with_their_request_by_the_database(session, pdf_bytes):
    request = make(session, pdf_bytes)
    session.commit()
    session.execute(text("delete from esign_requests where id=:i"), {"i": request.id})
    assert session.execute(select(T.event)).first() is None  # FK ON DELETE CASCADE (foreign_keys pragma is on)


def test_the_library_source_never_updates_or_deletes_events():
    import pathlib
    import re

    src = pathlib.Path(events.__file__).parent
    for path in src.glob("*.py"):
        body = path.read_text()
        assert not re.search(r"session\.delete\(|delete\(t\.event|update\(t\.event", body), path.name
