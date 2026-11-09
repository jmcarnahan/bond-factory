from datetime import UTC, datetime, timedelta

import pytest

from bond_auth_py import (
    AuthRefused,
    Claims,
    Identity,
    SessionRevoked,
    TokenError,
    check_exchange,
    check_session,
)

MARK = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)


class Revocation:
    def __init__(self, value):
        self.value = value

    def sessions_valid_after(self, user_id):
        return self.value


def claims(iat):
    return Claims("u1", "u1", "U", [], iat=iat, exp=iat + 1000)


def test_no_mark_means_valid():
    check_session(claims(1.0), Revocation(None))


def test_boundary_issued_before_after_and_equal():
    revocation = Revocation(MARK)
    with pytest.raises(SessionRevoked) as err:
        check_session(claims(MARK.timestamp() - 0.000001), revocation)
    assert err.value.code == "session_revoked" and err.value.status == 401
    check_session(claims(MARK.timestamp()), revocation)  # equal: still valid
    check_session(claims(MARK.timestamp() + 0.000001), revocation)


def test_naive_datetime_is_utc():
    revocation = Revocation(MARK.replace(tzinfo=None))
    with pytest.raises(SessionRevoked):
        check_session(claims(MARK.timestamp() - 1), revocation)
    check_session(claims(MARK.timestamp() + 1), revocation)


def test_session_revoked_is_an_auth_refused():
    assert issubclass(SessionRevoked, AuthRefused)
    assert SessionRevoked().detail() == {"code": "session_revoked", "message": "This session was ended. Sign in again."}


def test_unusable_iat_is_invalid_not_valid():
    bad = Claims("u1", "u1", None, [], iat="x", exp=1.0)  # type: ignore[arg-type]
    with pytest.raises(TokenError):
        check_session(bad, Revocation(MARK))


def test_exchange_skew(settings):
    revocation = Revocation(MARK)
    mark = MARK.timestamp()

    def exchange(auth_time):
        check_exchange(Identity("f1", "a@example.com", auth_time=auth_time), revocation, settings, user_id="u1")

    exchange(mark)
    exchange(mark - 5)  # exactly the skew: accepted
    exchange(mark - 4.9)
    with pytest.raises(SessionRevoked):
        exchange(mark - 5.1)
    with pytest.raises(SessionRevoked):
        exchange(None)  # cannot be proven newer
    check_exchange(Identity("f1", "a@example.com"), Revocation(None), settings, user_id="u1")


def test_exchange_uses_the_settings_skew(settings):
    from dataclasses import replace

    ident = Identity("f1", "a@example.com", auth_time=MARK.timestamp() - 30)
    with pytest.raises(SessionRevoked):
        check_exchange(ident, Revocation(MARK), settings, user_id="u1")
    check_exchange(ident, Revocation(MARK), replace(settings, auth_time_skew_seconds=60), user_id="u1")
    check_exchange(ident, Revocation(MARK - timedelta(minutes=1)), settings, user_id="u1")
