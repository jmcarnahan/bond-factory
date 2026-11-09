"""The lost-response retry rule (rotation_id) and the IdP liveness probe."""

import pytest
from sessions_support import (
    T0,
    AuthSession,
    Revocation,
    at,
    db,
    factory,
    issue,
    loader,
    rotate,
    rows,
    scope,
    settings_with,
    store,
)

from bond_auth_py import RefreshRevoked, ReuseDetected, SessionStore

__all__ = ["db", "factory", "store"]


def test_retry_with_the_same_rotation_id_issues_a_sibling_and_revokes_the_unused_child(db, store):
    first = issue(store, db)
    lost = rotate(store, db, first.refresh_token, now=T0 + 100, rid="rid-1")  # the response never arrived
    retry = rotate(store, db, first.refresh_token, now=T0 + 400, rid="rid-1")  # far past the 20 s grace
    stored = rows(db, first.family_id)
    assert len(stored) == 3 and lost.refresh_token != retry.refresh_token
    by_reason = {r.revoke_reason for r in stored if r.revoked_at}
    assert by_reason == {"retry"} and sum(1 for r in stored if r.revoked_at) == 1
    with pytest.raises(RefreshRevoked):  # the child whose response was lost is dead
        rotate(store, db, lost.refresh_token, now=T0 + 410)
    assert rotate(store, db, retry.refresh_token, now=T0 + 420).family_id == first.family_id


def test_a_thief_with_a_forged_rotation_id_after_grace_is_reuse(db, store):
    first = issue(store, db)
    rotate(store, db, first.refresh_token, now=T0 + 100, rid="real-id")
    with pytest.raises(ReuseDetected):
        rotate(store, db, first.refresh_token, now=T0 + 400, rid="forged-id")
    assert all(r.revoked_at is not None for r in rows(db))


@pytest.mark.parametrize("rid", [None, "", "x" * 65])
def test_without_a_usable_rotation_id_only_the_grace_rule_applies(db, store, rid):
    first = issue(store, db)
    rotate(store, db, first.refresh_token, now=T0 + 100, rid=rid)
    with pytest.raises(ReuseDetected):
        rotate(store, db, first.refresh_token, now=T0 + 400, rid=rid)


def test_retry_is_refused_once_the_child_was_used(db, store):
    first = issue(store, db)
    child = rotate(store, db, first.refresh_token, now=T0 + 100, rid="rid-1")
    rotate(store, db, child.refresh_token, now=T0 + 200)  # the client did receive it
    with pytest.raises(ReuseDetected):
        rotate(store, db, first.refresh_token, now=T0 + 300, rid="rid-1")


def test_retry_window_is_ten_minutes_from_the_first_rotation(db, store):
    first = issue(store, db)
    rotate(store, db, first.refresh_token, now=T0 + 100, rid="rid-1")
    with pytest.raises(ReuseDetected):
        rotate(store, db, first.refresh_token, now=T0 + 100 + 601, rid="rid-1")


def test_repeated_retries_cannot_slide_the_window(db, store):
    first = issue(store, db)
    rotate(store, db, first.refresh_token, now=T0 + 100, rid="rid-1")
    rotate(store, db, first.refresh_token, now=T0 + 600, rid="rid-1")  # 500 s after the rotation: retry
    with pytest.raises(ReuseDetected):  # 910 s after it: refused although the latest sibling is only 310 s old
        rotate(store, db, first.refresh_token, now=T0 + 1010, rid="rid-1")
    assert all(r.revoked_at is not None for r in rows(db))


def test_probe_false_revokes_the_family_and_the_raise_survives_a_rolling_back_scope(factory, db, store):
    first = issue(store, db)
    calls = []

    def dead(user_id, provider):
        calls.append((user_id, provider))
        return False

    with pytest.raises(RefreshRevoked), scope(factory) as session:
        rotate(store, session, first.refresh_token, now=T0 + 10, probe=dead, commit=False)
    assert calls == [("u1", "google")]
    stored = rows(db)
    assert len(stored) == 1 and stored[0].revoked_at is not None and stored[0].revoke_reason == "admin"


@pytest.mark.parametrize("answer", [True, None])
def test_probe_true_or_none_stamps_the_child_and_waits_a_day(db, store, answer):
    first = issue(store, db)
    calls = []

    def probe(user_id, provider):
        calls.append(provider)
        return answer

    child = rotate(store, db, first.refresh_token, now=T0 + 10, probe=probe)
    assert len(calls) == 1 and rows(db)[1].last_probed_at is not None
    grandchild = rotate(store, db, child.refresh_token, now=T0 + 3600, probe=probe)
    assert len(calls) == 1  # inside 24 h: no new probe, the stamp is carried forward
    assert rows(db)[2].last_probed_at == rows(db)[1].last_probed_at
    rotate(store, db, grandchild.refresh_token, now=T0 + 10 + 24 * 3600, probe=probe)
    assert len(calls) == 2


def test_no_probe_leaves_the_column_empty(db, store):
    first = issue(store, db)
    rotate(store, db, first.refresh_token, now=T0 + 10)
    assert [r.last_probed_at for r in rows(db)] == [None, None]


def test_a_stale_family_is_not_probed(db, store):
    first = issue(store, db)
    calls = []
    with pytest.raises(RefreshRevoked):
        rotate(store, db, first.refresh_token, now=T0 + 10, revocation=Revocation(at(T0 + 6)),
               probe=lambda u, p: calls.append(p))
    assert calls == []


def test_a_raising_probe_still_rotates_stamps_and_logs_only_the_type(db, store, caplog):
    first = issue(store, db)
    calls = []

    def boom(user_id, provider):
        calls.append(1)
        raise TimeoutError("idp down: secret-detail")

    child = rotate(store, db, first.refresh_token, now=T0 + 10, probe=boom)
    stored = rows(db)
    assert stored[0].rotated_at is not None and stored[1].last_probed_at is not None
    assert "TimeoutError" in caplog.text and "secret-detail" not in caplog.text
    rotate(store, db, child.refresh_token, now=T0 + 3600, probe=boom)
    assert len(calls) == 1  # an outage costs one probe per day, not one per refresh


def test_the_device_label_is_kept_and_capped(db, store):
    first = issue(store, db, device_label="x" * 200)
    child = rotate(store, db, first.refresh_token, now=T0 + 5)
    assert child.family_id == first.family_id
    assert [r.device_label for r in rows(db)] == ["x" * 80, "x" * 80]


def test_the_session_model_has_the_planned_indexes_and_columns():
    table = AuthSession.__table__
    names = {i.name: (tuple(c.name for c in i.columns), i.unique) for i in table.indexes}
    assert names == {
        "uq_auth_sessions_token_hash": (("token_hash",), True),
        "ix_auth_sessions_family_id": (("family_id",), False),
        "ix_auth_sessions_user_revoked": (("user_id", "revoked_at"), False),
        "ix_auth_sessions_expires_at": (("expires_at",), False),
    }
    assert table.c.token_hash.type.length == 43 and table.c.rotation_id.type.length == 64
    assert table.c.last_probed_at.nullable and not table.c.user_id.nullable


class NoTouch:
    """A session that fails the test on any use."""

    def __getattr__(self, name):
        raise AssertionError(f"the table was touched: {name}")


@pytest.mark.parametrize("token", ["", "   ", "x" * 300])
def test_empty_and_oversized_tokens_are_refused_before_any_query(store, token):
    with pytest.raises(RefreshRevoked):
        store.rotate(NoTouch(), refresh_token=token, rotation_id=None, loader=loader, revocation=Revocation(),
                     now=T0)
    assert store.revoke_token(NoTouch(), refresh_token=token) is False


def test_probe_is_never_called_when_hours_is_zero(db):
    off = SessionStore(AuthSession, settings_with(refresh_probe_hours=0))
    first = issue(off, db)
    calls = []
    rotate(off, db, first.refresh_token, now=T0 + 10, probe=lambda u, p: calls.append(p) or False)
    assert calls == [] and rows(db)[1].revoked_at is None and rows(db)[1].last_probed_at is None
