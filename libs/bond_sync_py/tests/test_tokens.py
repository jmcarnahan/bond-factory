from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import load_fixture
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from bond_sync_py import SyncKeyError, SyncTokenSettings, is_configured, jwks, key_reason, mint_sync_token
from bond_sync_py.tokens import clear_cache, previous_reason

NOW = datetime(2026, 11, 8, 12, 0, 0, 500000, tzinfo=UTC)


def pem(key=None) -> str:
    key = key or ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def public_of(jwk):
    return jwt.algorithms.ECAlgorithm.from_jwk({k: jwk[k] for k in ("kty", "crv", "x", "y")})


@pytest.fixture
def settings():
    return SyncTokenSettings(url="http://sync.example.test", private_key=pem())


def test_mint_and_verify_with_jwks(settings):
    token, expires = mint_sync_token(settings, "user-1", now=NOW)
    header = jwt.get_unverified_header(token)
    assert (header["alg"], header["kid"]) == ("ES256", "bond-sync-1")
    jwk = jwks(settings)["keys"][0]
    claims = jwt.decode(token, public_of(jwk), algorithms=["ES256"], audience="powersync",
                        options={"verify_exp": False})
    assert claims == {"sub": "user-1", "aud": "powersync", "iat": int(NOW.timestamp()),
                      "exp": int(NOW.timestamp()) + 900}
    assert expires == datetime(2026, 11, 8, 12, 15, 0)
    assert expires.tzinfo is None


def test_claims_are_ints_and_whole_seconds(settings):
    token, _ = mint_sync_token(settings, "u", now=NOW)
    claims = jwt.decode(token, options={"verify_signature": False})
    assert isinstance(claims["iat"], int) and isinstance(claims["exp"], int)


@pytest.mark.parametrize("minutes,expected", [(0, 1), (-5, 1), (1, 1), (15, 15), (60, 60), (500, 60)])
def test_minutes_are_clamped(settings, minutes, expected):
    s = SyncTokenSettings(url=settings.url, private_key=settings.private_key, minutes=minutes)
    _, expires = mint_sync_token(s, "u", now=NOW)
    assert expires - NOW.replace(microsecond=0, tzinfo=None) == timedelta(minutes=expected)


def test_custom_kid_and_audience():
    s = SyncTokenSettings(url="u", private_key=pem(), kid="demo-sync-7", audience="other")
    token, _ = mint_sync_token(s, "u", now=NOW)
    assert jwt.get_unverified_header(token)["kid"] == "demo-sync-7"
    assert jwt.decode(token, options={"verify_signature": False})["aud"] == "other"
    assert jwks(s)["keys"][0]["kid"] == "demo-sync-7"


def test_jwks_shape_is_public_only(settings):
    key = jwks(settings)["keys"][0]
    assert set(key) == {"kty", "crv", "x", "y", "kid", "alg", "use"}
    assert (key["kty"], key["crv"], key["alg"], key["use"]) == ("EC", "P-256", "ES256", "sig")
    assert "d" not in key
    assert set(key) == set(load_fixture("jwks_example.json")["keys"][0])


def test_rotation_publishes_previous_key_and_old_tokens_verify():
    old, new = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    before = SyncTokenSettings(url="u", private_key=pem(old), kid="k1")
    old_token, _ = mint_sync_token(before, "u", now=NOW)
    during = SyncTokenSettings(url="u", private_key=pem(new), kid="k2", previous_key=pem(old), previous_kid="k1")
    keys = {k["kid"]: k for k in jwks(during)["keys"]}
    assert list(keys) == ["k2", "k1"]
    claims = jwt.decode(old_token, public_of(keys["k1"]), algorithms=["ES256"], audience="powersync",
                        options={"verify_exp": False})
    assert claims["sub"] == "u"
    new_token, _ = mint_sync_token(during, "u", now=NOW)
    assert jwt.get_unverified_header(new_token)["kid"] == "k2"
    jwt.decode(new_token, public_of(keys["k2"]), algorithms=["ES256"], audience="powersync",
               options={"verify_exp": False})


def test_previous_key_needs_its_own_kid():
    s = SyncTokenSettings(url="u", private_key=pem(), previous_key=pem())
    assert "not set" in previous_reason(s)
    assert len(jwks(s)["keys"]) == 1
    same = SyncTokenSettings(url="u", private_key=pem(), kid="k", previous_key=pem(), previous_kid="k")
    assert "equals" in previous_reason(same)
    assert len(jwks(same)["keys"]) == 1


def test_bad_previous_key_is_ignored_not_fatal():
    s = SyncTokenSettings(url="u", private_key=pem(), previous_key="garbage", previous_kid="old")
    assert previous_reason(s)
    assert len(jwks(s)["keys"]) == 1


def test_key_from_file_and_replacement_is_picked_up(tmp_path):
    path = tmp_path / "k.pem"
    path.write_text(pem())
    s = SyncTokenSettings(url="u", private_key_file=str(path))
    first = jwks(s)["keys"][0]["x"]
    path.write_text(pem())
    import os
    os.utime(path, (NOW.timestamp() + 100, NOW.timestamp() + 100))
    assert jwks(s)["keys"][0]["x"] != first


def test_unusable_keys_are_reported_without_material(tmp_path):
    clear_cache()
    rsa_pem = pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    p384 = pem(ec.generate_private_key(ec.SECP384R1()))
    cases = {
        "": "no signing key",
        "not a pem": "readable",
        rsa_pem: "EC P-256",
        p384: "EC P-256",
    }
    for value, fragment in cases.items():
        s = SyncTokenSettings(url="u", private_key=value)
        reason = key_reason(s)
        assert fragment in reason
        assert "BEGIN" not in reason
        assert not is_configured(s)
        with pytest.raises(SyncKeyError):
            mint_sync_token(s, "u", now=NOW)
        with pytest.raises(SyncKeyError):
            jwks(s)
    missing = SyncTokenSettings(url="u", private_key_file=str(tmp_path / "nope.pem"))
    assert "cannot be read" in key_reason(missing)


def test_is_configured_needs_url_and_key(settings):
    assert is_configured(settings)
    assert not is_configured(SyncTokenSettings(private_key=settings.private_key))
    assert not is_configured(SyncTokenSettings(url="u"))


def test_from_env_uses_bond_sync_names_and_defaults():
    env = {"BOND_SYNC_URL": "http://x", "BOND_SYNC_PRIVATE_KEY_FILE": "/k.pem", "BOND_SYNC_MINUTES": "30",
           "BOND_SYNC_PREVIOUS_KID": "old", "BOND_SYNC_KID": "mine"}
    s = SyncTokenSettings.from_env(env=env)
    assert (s.url, s.private_key_file, s.minutes, s.previous_kid, s.kid) == ("http://x", "/k.pem", 30, "old", "mine")
    assert (s.audience, s.private_key) == ("powersync", "")
    empty = SyncTokenSettings.from_env(env={})
    assert (empty.kid, empty.minutes, empty.url) == ("bond-sync-1", 15, "")
    assert SyncTokenSettings.from_env(env={"BOND_SYNC_MINUTES": "soon"}).minutes == 15
    custom = SyncTokenSettings.from_env("APP_SYNC_", env={"APP_SYNC_URL": "http://y", "BOND_SYNC_URL": "no"})
    assert custom.url == "http://y"


def test_settings_repr_hides_keys(settings):
    assert "BEGIN" not in repr(settings)
