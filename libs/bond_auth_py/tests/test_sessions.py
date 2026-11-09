import pytest
from sessions_support import (
    DAY,
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

from bond_auth_py import (
    RefreshExpired,
    RefreshRevoked,
    ReuseDetected,
    SessionStore,
    decode_claims,
)
from bond_auth_py.sessions_base import token_hash

__all__ = ["db", "factory", "store"]


def test_issue_then_rotate_mints_a_jwt_and_stores_only_hashes(db, store):
    first = issue(store, db)
    second = rotate(store, db, first.refresh_token, now=T0 + 5)  # iat inside the 10 s leeway
    assert second.refresh_token != first.refresh_token and second.family_id == first.family_id
    claims = decode_claims(second.access_jwt, store.settings)
    assert claims.user_id == "u1" and claims.capabilities == ["a.b"] and claims.extra["company_id"] == "c1"
    stored = rows(db)
    assert len(stored) == 2 and all(len(r.token_hash) == 43 for r in stored)
    assert {r.token_hash for r in stored} == {token_hash(first.refresh_token), token_hash(second.refresh_token)}
    dump = repr([[getattr(r, c.name) for c in AuthSession.__table__.columns] for r in stored])
    assert first.refresh_token not in dump and second.refresh_token not in dump
    assert stored[0].rotated_at is not None and stored[1].rotated_at is None and stored[1].parent_id == stored[0].id


def test_access_jwt_carries_sid_and_lasts_sixty_minutes(db, store):
    issued = issue(store, db, now=None)
    claims = decode_claims(issued.access_jwt, store.settings)
    assert claims.extra["sid"] == issued.family_id and issued.expires_in == 3600
    assert claims.exp - claims.iat == pytest.approx(3600, abs=1) and claims.user_id == issued.user_id == "u1"
    rotated = rotate(store, db, issued.refresh_token, now=None)
    again = decode_claims(rotated.access_jwt, store.settings)
    assert again.extra["sid"] == issued.family_id and again.exp - again.iat == pytest.approx(3600, abs=1)


def test_reuse_past_grace_revokes_every_row_and_survives_a_rolling_back_scope(factory, db, store):
    first = issue(store, db)
    live = rotate(store, db, first.refresh_token, now=T0 + 100)
    with pytest.raises(ReuseDetected) as err, scope(factory) as session:  # rolls back on exception, like
        rotate(store, session, first.refresh_token, now=T0 + 130, commit=False)  # the example's session_scope
    assert err.value.code == "refresh_reused" and err.value.status == 401
    stored = rows(db, first.family_id)
    assert len(stored) == 2 and all(r.revoked_at is not None for r in stored)
    assert {r.revoke_reason for r in stored} == {"reuse"}
    with pytest.raises(RefreshRevoked):
        rotate(store, db, live.refresh_token, now=T0 + 140)
    with pytest.raises(RefreshRevoked):  # and the replayed one now reads "revoked", not "reuse" again
        rotate(store, db, first.refresh_token, now=T0 + 150)


def test_replay_inside_grace_gets_a_sibling_and_revokes_nothing(db, store):
    first = issue(store, db)
    one = rotate(store, db, first.refresh_token, now=T0 + 100)
    two = rotate(store, db, first.refresh_token, now=T0 + 119.9)  # boundary: 19.9 s after the claim
    assert one.refresh_token != two.refresh_token
    stored = rows(db, first.family_id)
    assert len(stored) == 3 and all(r.revoked_at is None for r in stored)
    assert [r.parent_id for r in stored[1:]] == [stored[0].id, stored[0].id]
    with pytest.raises(ReuseDetected):  # exactly at the grace length it is reuse
        rotate(store, db, first.refresh_token, now=T0 + 120)


def test_grace_zero_is_strict(db):
    strict = SessionStore(AuthSession, settings_with(refresh_reuse_grace_seconds=0))
    first = issue(strict, db)
    rotate(strict, db, first.refresh_token, now=T0 + 100)
    with pytest.raises(ReuseDetected):
        rotate(strict, db, first.refresh_token, now=T0 + 100)  # even at the same instant


def test_sliding_expiry_extends_but_never_passes_the_family_cap(db, store):
    first = issue(store, db)  # auth_time T0: cap at T0 + 180 d
    child = rotate(store, db, first.refresh_token, now=T0 + 50 * DAY)
    assert rows(db)[1].expires_at == at(T0 + 110 * DAY).replace(tzinfo=None)
    token = child.refresh_token
    for day in (100, 150):
        token = rotate(store, db, token, now=T0 + day * DAY).refresh_token
    last = rows(db)[-1]
    assert last.expires_at == last.family_expires_at == at(T0 + 180 * DAY).replace(tzinfo=None)
    with pytest.raises(RefreshExpired) as err:
        rotate(store, db, token, now=T0 + 180 * DAY)
    assert err.value.code == "refresh_expired"


def test_expired_rotate_does_not_burn_the_token(db, store):
    first = issue(store, db)
    with pytest.raises(RefreshExpired):
        rotate(store, db, first.refresh_token, now=T0 + 61 * DAY, commit=False)
    only = rows(db)
    assert len(only) == 1 and only[0].rotated_at is None and only[0].last_used_at is None


def test_revocation_mark_compares_the_family_auth_time(db, store):
    first = issue(store, db)  # auth_time T0
    mark = Revocation(at(T0 + 100))
    with pytest.raises(RefreshRevoked):  # `now` is after the mark: comparing `now` would let it through
        rotate(store, db, first.refresh_token, now=T0 + 200, revocation=mark)
    assert {r.revoke_reason for r in rows(db)} == {"signout_all"}
    fresh = issue(store, db, now=T0 + 101)  # a new sign-in after the mark works
    assert rotate(store, db, fresh.refresh_token, now=T0 + 200, revocation=mark).user_id == "u1"


def test_revocation_mark_keeps_the_five_second_skew(db, store):
    first = issue(store, db)
    ok = rotate(store, db, first.refresh_token, now=T0 + 10, revocation=Revocation(at(T0 + 4.9)))
    with pytest.raises(RefreshRevoked):
        rotate(store, db, ok.refresh_token, now=T0 + 20, revocation=Revocation(at(T0 + 5.1)))


def test_a_new_child_does_not_refresh_the_auth_time(db, store):
    first = issue(store, db)
    child = rotate(store, db, first.refresh_token, now=T0 + 3000)  # JWT iat and child created_at are late
    assert rows(db)[1].auth_time == rows(db)[0].auth_time
    with pytest.raises(RefreshRevoked):
        rotate(store, db, child.refresh_token, now=T0 + 3100, revocation=Revocation(at(T0 + 2000)))


def test_naive_and_aware_marks_and_columns(db, store):
    first = issue(store, db)
    naive = at(T0 - 100).replace(tzinfo=None)
    token = rotate(store, db, first.refresh_token, now=T0 + 1, revocation=Revocation(naive)).refresh_token
    assert all(r.auth_time.tzinfo is None and r.expires_at.tzinfo is None for r in rows(db))
    with pytest.raises(RefreshRevoked):
        rotate(store, db, token, now=T0 + 2, revocation=Revocation(at(T0 + 100).replace(tzinfo=None)))


def test_loader_none_ends_the_family(db, store):
    first = issue(store, db)
    with pytest.raises(RefreshRevoked):
        rotate(store, db, first.refresh_token, now=T0 + 10, loader=lambda uid: None)
    assert all(r.revoked_at is not None for r in rows(db))


def test_a_failing_loader_does_not_burn_the_token(db, store):
    first = issue(store, db)

    def boom(uid):
        raise OSError("db down")

    with pytest.raises(OSError):
        rotate(store, db, first.refresh_token, now=T0 + 10, loader=boom, commit=False)
    assert rows(db)[0].rotated_at is None
    assert rotate(store, db, first.refresh_token, now=T0 + 11).user_id == "u1"


@pytest.mark.parametrize("token", ["", "   ", "x" * 257, "unknown-token", None, 123])
def test_malformed_and_unknown_tokens_are_revoked_and_create_no_rows(db, store, token):
    issue(store, db)
    with pytest.raises(RefreshRevoked) as err:
        store.rotate(db, refresh_token=token, rotation_id=None, loader=loader, revocation=Revocation(), now=T0)
    assert err.value.code == "refresh_revoked"
    assert len(rows(db)) == 1


def test_revoke_token_is_idempotent_and_isolates_families(db, store):
    one, two = issue(store, db), issue(store, db)
    rotate(store, db, one.refresh_token, now=T0 + 5)
    assert store.revoke_token(db, refresh_token=one.refresh_token) is True  # a stale token still ends the family
    assert store.revoke_token(db, refresh_token=one.refresh_token) is False
    assert store.revoke_token(db, refresh_token="nope") is False and store.revoke_token(db, refresh_token="") is False
    assert {r.revoke_reason for r in rows(db, one.family_id)} == {"logout"}
    assert all(r.revoked_at is None for r in rows(db, two.family_id))
    assert rotate(store, db, two.refresh_token, now=T0 + 6).user_id == "u1"


def test_revoke_user_ends_every_family_and_marks_in_the_same_transaction(factory, db, store):
    issue(store, db), issue(store, db), issue(store, db, user="u2")
    marks = []
    with scope(factory) as session:
        count = store.revoke_user(session, user_id="u1", reason="signout_all",
                                  mark_valid_after=lambda uid, when: marks.append((uid, when)))
    assert count == 2 and marks[0][0] == "u1" and marks[0][1].tzinfo is not None
    stored = rows(db)
    assert {(r.user_id, r.revoke_reason) for r in stored if r.revoked_at} == {("u1", "signout_all")}
    assert [r.revoked_at for r in stored if r.user_id == "u2"] == [None]


def test_the_eleventh_session_revokes_the_least_recently_used_family(db, store):
    families = [issue(store, db, now=T0 + i) for i in range(10)]
    rotate(store, db, families[0].refresh_token, now=T0 + 50)  # family 0 is now the most recent
    newest = issue(store, db, now=T0 + 60)
    revoked = {r.family_id for r in rows(db) if r.revoked_at}
    assert revoked == {families[1].family_id}
    assert {r.revoke_reason for r in rows(db) if r.revoked_at} == {"limit"}
    live = {r.family_id for r in rows(db) if r.revoked_at is None and r.rotated_at is None}
    assert len(live) == 10 and newest.family_id in live
    with pytest.raises(RefreshRevoked):
        rotate(store, db, families[1].refresh_token, now=T0 + 70)


def test_prune_drops_old_expired_revoked_and_rotated_rows_and_keeps_recent_ones(db, store):
    old = issue(store, db)  # expires T0 + 60 d
    kept = issue(store, db)
    revoked_recent = issue(store, db)
    rotate(store, db, old.refresh_token, now=T0 + 10)
    store.revoke_token(db, refresh_token=revoked_recent.refresh_token)
    db.commit()
    assert store.prune(db, now=T0 + 3 * DAY) == 0
    removed = store.prune(db, now=T0 + 8 * DAY)  # revoked > 7 d, and the rotated parent
    db.commit()
    assert removed == 2
    assert {r.family_id for r in rows(db)} == {old.family_id, kept.family_id}
    assert len(rows(db, old.family_id)) == 1  # the live child stays
    assert store.prune(db, now=T0 + 66 * DAY) == 0  # expired 6 d ago: kept
    assert store.prune(db, now=T0 + 68 * DAY) == 2  # expired 8 d ago
    db.commit()
    assert rows(db) == []
