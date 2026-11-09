from dataclasses import replace
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from bond_auth_py import (
    TokenError,
    cookie_name,
    create_access_token,
    decode_claims,
    read_bearer_or_cookie,
    session_cookie_params,
)


def mint(settings, **kw):
    return create_access_token(sub="u1", name="Una", capabilities=["a", "b"], settings=settings, **kw)


def test_mint_and_decode_round_trip(settings):
    token = mint(settings, extra_claims={"company_id": "c1", "sub": "attacker", "exp": 1})
    raw = jwt.decode(token, options={"verify_signature": False})
    assert set(raw) == {"sub", "user_id", "name", "capabilities", "iat", "exp", "aud", "iss", "company_id"}
    assert raw["sub"] == raw["user_id"] == "u1"  # extra claims cannot override standard ones
    assert raw["aud"] == ["bond-api"] and raw["iss"] == "bond"
    assert isinstance(raw["iat"], float) and raw["exp"] - int(raw["iat"]) in (10080 * 60, 10080 * 60 - 1)
    claims = decode_claims(token, settings)
    assert (claims.sub, claims.user_id, claims.name, claims.capabilities) == ("u1", "u1", "Una", ["a", "b"])
    assert claims.extra == {"company_id": "c1"}


def test_iat_is_sub_second_real_time(settings):
    at = datetime(2030, 1, 1, 12, 0, 0, 250_000, tzinfo=UTC)
    token = mint(settings, now=at)
    assert jwt.decode(token, options={"verify_signature": False, "verify_exp": False})["iat"] == at.timestamp()


def test_ttl_overrides_the_settings_minutes(settings):
    at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)
    raw = jwt.decode(mint(settings, now=at, ttl=timedelta(minutes=5)),
                     options={"verify_signature": False, "verify_exp": False})
    assert raw["exp"] - raw["iat"] == 300
    default = jwt.decode(mint(settings, now=at), options={"verify_signature": False, "verify_exp": False})
    assert default["exp"] - default["iat"] == 10080 * 60


def test_leeway_tolerates_clock_skew_between_nodes(settings):
    now = datetime.now(UTC)
    assert decode_claims(mint(settings, now=now + timedelta(seconds=5)), settings).sub == "u1"
    with pytest.raises(TokenError):  # 30 s ahead is beyond the leeway
        decode_claims(mint(settings, now=now + timedelta(seconds=30)), settings)


def test_expired(settings):
    token = mint(settings, now=datetime.now(UTC) - timedelta(minutes=settings.access_ttl_minutes + 1))
    with pytest.raises(TokenError) as err:
        decode_claims(token, settings)
    assert err.value.reason == "expired"


def test_wrong_secret_audience_issuer_and_garbage(settings):
    token = mint(settings)
    for other in (replace(settings, jwt_secret="another-secret-also-long-enough-for-hs256"),
                  replace(settings, audience="other"), replace(settings, issuer="other")):
        with pytest.raises(TokenError) as err:
            decode_claims(token, other)
        assert err.value.reason == "invalid"
    with pytest.raises(TokenError):
        decode_claims("not.a.jwt", settings)


def test_missing_claims(settings):
    def forge(**claims):
        base = {"aud": ["bond-api"], "iss": "bond", "exp": datetime.now(UTC) + timedelta(hours=1),
                "iat": datetime.now(UTC).timestamp()}
        return jwt.encode({**base, **claims}, settings.jwt_secret, algorithm="HS256")

    with pytest.raises(TokenError) as err:
        decode_claims(forge(sub="u1"), settings)  # no user_id
    assert err.value.reason == "incomplete"
    with pytest.raises(TokenError):
        decode_claims(forge(user_id="u1"), settings)  # no sub
    no_iat = jwt.encode({"sub": "u", "user_id": "u", "aud": ["bond-api"], "iss": "bond",
                         "exp": datetime.now(UTC) + timedelta(hours=1)}, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_claims(no_iat, settings)
    no_exp = jwt.encode({"sub": "u", "user_id": "u", "aud": ["bond-api"], "iss": "bond", "iat": 1.0},
                        settings.jwt_secret, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_claims(no_exp, settings)


def test_empty_secret_never_mints_or_verifies(settings):
    from bond_auth_py import AuthSettings

    good = mint(settings)
    for secret in ("", "  "):
        empty = AuthSettings(jwt_secret=secret)
        with pytest.raises(TokenError) as err:
            create_access_token(sub="u", name=None, capabilities=[], settings=empty)
        assert err.value.reason == "misconfigured"
        with pytest.raises(TokenError) as err:
            decode_claims(good, empty)
        assert err.value.reason == "misconfigured"
    # the guard sits before PyJWT, so a token forged with an empty key is refused whatever the library version does
    forged = jwt.api_jws.PyJWS().encode(b'{"sub":"u","user_id":"u"}', "x" * 32, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_claims(forged, AuthSettings(jwt_secret=""))


def test_cookie_name_and_params(settings):
    assert cookie_name("shop") == "shop_access_token"
    params = session_cookie_params(settings, secure=True)
    assert params == {"httponly": True, "secure": True, "samesite": "lax", "path": "/", "max_age": 10080 * 60}


def test_bearer_wins_over_cookie():
    headers = {"Authorization": "Bearer abc"}
    assert read_bearer_or_cookie(headers, {"c": "cookie-token"}, "c") == "abc"
    assert read_bearer_or_cookie({"authorization": "bearer  abc "}, {}, "c") == "abc"
    assert read_bearer_or_cookie({}, {"c": "cookie-token"}, "c") == "cookie-token"
    assert read_bearer_or_cookie({"Authorization": "Basic zzz"}, {"c": "ck"}, "c") == "ck"
    assert read_bearer_or_cookie({"Authorization": "Bearer "}, {"c": "ck"}, "c") == "ck"
    assert read_bearer_or_cookie({}, None, "c") is None
    assert read_bearer_or_cookie({}, {"c": ""}, "c") is None
