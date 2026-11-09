import threading
from datetime import datetime
from urllib.parse import unquote

import pytest
from conftest import Base, Connection
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import bond_oauth.service as svc
from bond_oauth import FakeOAuth, OAuthError, TokenSet, access_token, complete, start, start_flow


def flow(session, cipher, fake, user="u1", **kw):
    return start_flow(session, user_id=user, provider_name="fake", provider=fake, scopes=["a"], redirect_to="http://app",
                      cipher=cipher, redirect_uri="r", **kw)


def finish(session, cipher, providers, started, **kw):
    kw.setdefault("expected_nonce", started.nonce)
    kw.setdefault("expected_user_id", None)
    return complete(session, state=started.state, code="mock", providers=providers, cipher=cipher,
                    connection_model=Connection, redirect_uri="r", **kw)


def test_start_flow_returns_state_url_and_nonce(session, cipher, fake):
    started = flow(session, cipher, fake)
    assert started.authorize_url.startswith("/consent?state=")
    assert started.state in unquote(started.authorize_url)
    assert started.nonce and started.nonce not in started.state


def test_start_is_a_thin_wrapper(session, cipher, fake):
    url = start(session, user_id="u1", provider_name="fake", provider=fake, scopes=["a"], redirect_to="",
                cipher=cipher, redirect_uri="r")
    assert url.startswith("/consent?state=")


def test_matching_nonce_completes(session, cipher, fake, providers):
    started = flow(session, cipher, fake)
    assert finish(session, cipher, providers, started, expected_nonce=started.nonce).user_id == "u1"


def test_other_flows_nonce_is_refused_and_stores_nothing(session, cipher, fake, providers):
    a, b = flow(session, cipher, fake), flow(session, cipher, fake)
    with pytest.raises(OAuthError) as err:
        finish(session, cipher, providers, a, expected_nonce=b.nonce)
    assert err.value.code == "invalid_state"
    assert session.execute(select(Connection)).first() is None


def test_empty_nonce_is_refused(session, cipher, fake, providers):
    with pytest.raises(OAuthError):
        finish(session, cipher, providers, flow(session, cipher, fake), expected_nonce="")


def test_live_row_unique_index_blocks_a_second_live_row(session):
    def row():
        return Connection(user_id=None, provider="p", connection_name="p", account_email="a@example.com",
                          refresh_token_enc="x", connected_at=datetime(2026, 1, 1))

    session.add(row())
    session.commit()
    session.add(row())
    with pytest.raises(IntegrityError):
        session.commit()


def test_unique_index_allows_revoked_history_and_other_owners(session):
    def row(user, revoked=None):
        return Connection(user_id=user, provider="p", connection_name="p", account_email="a@example.com",
                          refresh_token_enc="x", connected_at=datetime(2026, 1, 1), revoked_at=revoked)

    session.add_all([row("u1", datetime(2026, 1, 2)), row("u1", datetime(2026, 1, 3)), row("u1"), row("u2"), row(None)])
    session.commit()


def test_race_retry_revokes_the_winner_and_succeeds(session, cipher, fake, providers, monkeypatch):
    winner = finish(session, cipher, providers, flow(session, cipher, fake))
    real, calls = svc._live, []

    def blind_first(*a, **kw):  # the concurrent request did not see the winner's row yet
        calls.append(1)
        return [] if len(calls) == 1 else real(*a, **kw)

    monkeypatch.setattr(svc, "_live", blind_first)
    row = finish(session, cipher, providers, flow(session, cipher, fake))
    live = session.execute(select(Connection).where(Connection.revoked_at.is_(None))).scalars().all()
    assert [r.id for r in live] == [row.id] and winner.id != row.id and len(calls) == 2


def test_race_that_keeps_losing_raises_conflict(session, cipher, fake, providers, monkeypatch):
    finish(session, cipher, providers, flow(session, cipher, fake))
    monkeypatch.setattr(svc, "_live", lambda *a, **kw: [])
    with pytest.raises(OAuthError) as err:
        finish(session, cipher, providers, flow(session, cipher, fake))
    assert err.value.code == "conflict"
    assert len(session.execute(select(Connection)).scalars().all()) == 1


class BarrierFake(FakeOAuth):
    """Both callbacks finish the provider exchange before either one touches the database."""

    def __init__(self, barrier):
        super().__init__("/consent")
        self.barrier = barrier

    def userinfo(self, access_token):
        self.barrier.wait(timeout=10)
        return super().userinfo(access_token)


@pytest.mark.parametrize("round_", range(5))
def test_concurrent_callbacks_leave_exactly_one_live_row(tmp_path, cipher, round_):
    engine = create_engine(f"sqlite:///{tmp_path}/race.db", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    fake = BarrierFake(threading.Barrier(2))
    providers = {"fake": fake}
    with factory() as setup:
        states = [flow(setup, cipher, fake) for _ in range(2)]
    errors: list[BaseException] = []

    def run(started):
        try:
            with factory() as session:
                finish(session, cipher, providers, started)
        except BaseException as exc:  # noqa: BLE001 - the test asserts nothing escapes
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(s,)) for s in states]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    with factory() as check:
        rows = check.execute(select(Connection)).scalars().all()
    assert errors == []
    assert len(rows) == 2 and len([r for r in rows if r.revoked_at is None]) == 1


class ShortLived:
    """Refreshes to a token that lives ``expires_in`` seconds."""

    def __init__(self, expires_in):
        self.expires_in, self.calls = expires_in, 0

    def refresh(self, refresh_token, *, scopes):
        self.calls += 1
        return TokenSet(access_token=f"t{self.calls}", expires_in=self.expires_in)


def stored_row(session, cipher):
    row = Connection(user_id="u1", provider="p", connection_name="p", account_email="a@example.com",
                     refresh_token_enc=cipher.encrypt("rt"), connected_at=datetime(2026, 1, 1))
    session.add(row)
    session.commit()
    return row


def test_cache_ttl_follows_expires_in(session, cipher, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(svc, "_monotonic", lambda: clock[0])
    provider, row = ShortLived(300), stored_row(session, cipher)
    access_token(session, row, provider=provider, cipher=cipher)
    clock[0] += 170  # inside 300 - 120
    access_token(session, row, provider=provider, cipher=cipher)
    assert provider.calls == 1
    clock[0] += 6 * 60
    access_token(session, row, provider=provider, cipher=cipher)
    assert provider.calls == 2


def test_very_short_token_is_not_cached(session, cipher):
    provider, row = ShortLived(100), stored_row(session, cipher)
    access_token(session, row, provider=provider, cipher=cipher)
    access_token(session, row, provider=provider, cipher=cipher)
    assert provider.calls == 2


def test_long_token_still_capped_at_fifty_minutes(session, cipher, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(svc, "_monotonic", lambda: clock[0])
    provider, row = ShortLived(86400), stored_row(session, cipher)
    access_token(session, row, provider=provider, cipher=cipher)
    clock[0] += 51 * 60
    access_token(session, row, provider=provider, cipher=cipher)
    assert provider.calls == 2
