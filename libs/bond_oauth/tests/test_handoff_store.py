"""``HandoffStore``: device-bound single-use codes in a table."""

import hashlib
import threading
from datetime import timedelta

import pytest
from conftest import Base, Handoff
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bond_oauth import HandoffStore, OAuthError

SECRET = "device-secret-1"
DEVICE = hashlib.sha256(SECRET.encode()).hexdigest()
T0 = 1_800_000_000.0


@pytest.fixture
def store(cipher):
    return HandoffStore(Handoff, cipher)


def issue(store, session, **kw):
    kw.setdefault("purpose", "signin")
    kw.setdefault("payload", {"user_id": "user-marker-7f3c", "provider": "google", "auth_time": 5.0, "attempt": "a1"})
    return store.issue(session, provider="google", device_hash=DEVICE, attempt_id="a1", now=T0, **kw)


def redeem(store, session, code, **kw):
    kw.setdefault("device_secret", SECRET)
    kw.setdefault("purpose", "signin")
    return store.redeem(session, code=code, now=T0 + 10, **kw)


def refusal(store, session, code, **kw):
    with pytest.raises(OAuthError) as caught:
        redeem(store, session, code, **kw)
    assert caught.value.code == "invalid_handoff"


def test_round_trip_returns_the_payload(store, session):
    code = issue(store, session)
    assert redeem(store, session, code) == {"user_id": "user-marker-7f3c", "provider": "google", "auth_time": 5.0, "attempt": "a1"}


def test_the_row_holds_hashes_and_sealed_text_never_the_code_or_payload(store, session):
    code = issue(store, session)
    row = session.query(Handoff).one()
    assert row.code_hash == hashlib.sha256(code.encode()).hexdigest() and code not in row.payload_enc
    assert "user-marker-7f3c" not in row.payload_enc and row.device_hash == DEVICE and row.purpose == "signin"
    assert (row.attempt_id, row.used_at) == ("a1", None)
    assert row.expires_at - row.created_at == timedelta(seconds=120)


def test_second_redeem_is_refused(store, session):
    code = issue(store, session)
    redeem(store, session, code)
    refusal(store, session, code)


def test_wrong_device_secret_refuses_and_burns_the_code(store, session):
    code = issue(store, session)
    refusal(store, session, code, device_secret="not-the-secret")
    refusal(store, session, code)  # the right secret is too late now
    assert session.query(Handoff).one().used_at is not None


def test_wrong_purpose_refuses_and_burns_the_code(store, session):
    code = issue(store, session, purpose="connect")
    refusal(store, session, code, purpose="signin")
    refusal(store, session, code, purpose="connect")


def test_expired_code_is_refused(store, session):
    code = issue(store, session)
    with pytest.raises(OAuthError) as caught:
        store.redeem(session, code=code, device_secret=SECRET, purpose="signin", now=T0 + 120)
    assert caught.value.code == "invalid_handoff"


def test_still_valid_one_second_before_expiry_and_ttl_is_adjustable(store, session):
    code = issue(store, session, ttl=30)
    assert store.redeem(session, code=code, device_secret=SECRET, purpose="signin", now=T0 + 29)["user_id"] == "user-marker-7f3c"


@pytest.mark.parametrize("code", ["", "nope", "A" * 43])
def test_unknown_codes_are_refused(store, session, code):
    issue(store, session)
    refusal(store, session, code)


@pytest.mark.parametrize("bad", ["", "AB" * 32, "ab" * 31, "zz" * 32, "ab" * 32 + "0"])
def test_device_hash_must_be_64_lowercase_hex(store, session, bad):
    with pytest.raises(OAuthError) as caught:
        store.issue(session, purpose="signin", provider="google", payload={}, device_hash=bad, attempt_id=None)
    assert caught.value.code == "invalid_request" and session.query(Handoff).count() == 0


def test_attempt_id_is_validated(store, session):
    with pytest.raises(OAuthError):
        store.issue(session, purpose="signin", provider="g", payload={}, device_hash=DEVICE, attempt_id="a b")


def test_a_tampered_payload_is_refused(store, session, cipher):
    code = issue(store, session)
    session.query(Handoff).update({"payload_enc": cipher.encrypt("{}")})  # sealed with the other purpose's key
    session.commit()
    refusal(store, session, code)


def test_prune_removes_only_rows_expired_long_ago(store, session):
    old, fresh = issue(store, session), store.issue(session, purpose="signin", provider="g", payload={},
                                                    device_hash=DEVICE, attempt_id=None, now=T0 + 5000)
    assert store.prune(session, now=T0 + 120 + 3600 + 1) == 1  # only the first expired over an hour ago
    assert session.query(Handoff).count() == 1 and redeem_at(store, session, fresh, T0 + 5010) == {}
    assert old


def redeem_at(store, session, code, now):
    return store.redeem(session, code=code, device_secret=SECRET, purpose="signin", now=now)


def test_prune_keeps_a_row_inside_the_window_and_returns_zero(store, session):
    issue(store, session)
    assert store.prune(session, now=T0 + 3000) == 0 and session.query(Handoff).count() == 1


def test_two_threads_on_a_sqlite_file_exactly_one_wins(cipher, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'h.db'}", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    store = HandoffStore(Handoff, cipher)
    with maker() as s:
        code = issue(store, s)
    barrier, outcomes = threading.Barrier(6), []

    def worker():
        with maker() as s:
            barrier.wait()
            try:
                outcomes.append(("won", store.redeem(s, code=code, device_secret=SECRET, purpose="signin", now=T0 + 1)))
            except OAuthError as exc:
                outcomes.append((exc.code, None))
            except Exception as exc:  # noqa: BLE001 - a locking bug must show up as an outcome, not a hang
                outcomes.append((type(exc).__name__, None))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert sorted(o[0] for o in outcomes) == ["invalid_handoff"] * 5 + ["won"]
    engine.dispose()
