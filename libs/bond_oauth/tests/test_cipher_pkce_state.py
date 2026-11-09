import base64
import hashlib
import time

import pytest

from bond_oauth import OAuthError, TokenCipher, decode_state, encode_state, pkce


def test_cipher_round_trip(cipher):
    assert cipher.decrypt(cipher.encrypt("refresh-abc")) == "refresh-abc"


def test_cipher_text_differs_each_time(cipher):
    assert cipher.encrypt("x") != cipher.encrypt("x")


def test_cipher_wrong_key_is_value_error(cipher):
    with pytest.raises(ValueError):
        TokenCipher("another-key").decrypt(cipher.encrypt("secret"))


def test_cipher_garbage_is_value_error(cipher):
    with pytest.raises(ValueError):
        cipher.decrypt("not-a-token")


def test_cipher_accepts_a_real_fernet_key():
    key = TokenCipher.generate_key()
    assert TokenCipher(key).decrypt(TokenCipher(key).encrypt("a")) == "a"


def test_state_blob_never_decrypts_as_a_token_and_back(cipher):
    state = cipher.encrypt_state("payload")
    token = cipher.encrypt("payload")
    with pytest.raises(ValueError):
        cipher.decrypt(state)
    with pytest.raises(ValueError):
        cipher.decrypt_state(token)


def test_a_token_ciphertext_is_not_a_valid_state(cipher):
    with pytest.raises(OAuthError) as err:
        decode_state(cipher, cipher.encrypt('{"sub":"u1"}'))
    assert err.value.code == "invalid_state"


@pytest.mark.parametrize("key", ["plain secret string", TokenCipher.generate_key()])
def test_both_key_forms_round_trip_both_purposes(key):
    c = TokenCipher(key)
    assert c.decrypt(c.encrypt("t")) == "t" and c.decrypt_state(c.encrypt_state("s")) == "s"
    assert TokenCipher(key).decrypt(c.encrypt("t")) == "t"


def test_fernet_key_form_is_hkdf_input_not_used_directly():
    from cryptography.fernet import Fernet

    key = TokenCipher.generate_key()
    with pytest.raises(ValueError):
        TokenCipher(key).decrypt(Fernet(key.encode()).encrypt(b"x").decode())


def test_cipher_empty_key_refused():
    with pytest.raises(ValueError):
        TokenCipher("  ")


def test_cipher_from_env(monkeypatch):
    monkeypatch.setenv("BOND_OAUTH_KEY", "k")
    assert TokenCipher.from_env().decrypt(TokenCipher("k").encrypt("v")) == "v"
    monkeypatch.delenv("BOND_OAUTH_KEY")
    with pytest.raises(ValueError):
        TokenCipher.from_env()


def test_pkce_verifier_is_long_and_random():
    a, b = pkce.new_verifier(), pkce.new_verifier()
    assert a != b and len(a) >= 86


def test_pkce_challenge_is_s256_unpadded():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert pkce.challenge(verifier) == expected == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _state(cipher, **kw):
    args = {"sub": "u1", "provider": "google", "connection_name": "google", "verifier": "v",
            "redirect_to": "http://x/y"}
    return encode_state(cipher, **{**args, **kw})


def test_state_round_trip(cipher):
    payload = decode_state(cipher, _state(cipher, shared=True))
    assert (payload.sub, payload.provider, payload.verifier, payload.redirect_to, payload.shared) == (
        "u1", "google", "v", "http://x/y", True)
    assert payload.exp - time.time() == pytest.approx(600, abs=5)


def test_state_is_opaque(cipher):
    sub, verifier = "sub-marker-9f3c2e71", "verifier-marker-5b1d84a6"
    state = _state(cipher, sub=sub, verifier=verifier)
    raw = base64.urlsafe_b64decode(state)
    for marker in (sub, verifier, "google"):
        assert marker not in state and marker.encode() not in raw
    payload = decode_state(cipher, state)
    assert (payload.sub, payload.verifier) == (sub, verifier)


def test_state_tampered(cipher):
    state = _state(cipher)
    flipped = state[:-3] + ("AAA" if not state.endswith("AAA") else "BBB")
    with pytest.raises(OAuthError) as err:
        decode_state(cipher, flipped)
    assert err.value.code == "invalid_state"


def test_state_other_key(cipher):
    with pytest.raises(OAuthError) as err:
        decode_state(TokenCipher("zzz"), _state(cipher))
    assert err.value.code == "invalid_state"


def test_state_empty_or_not_json(cipher):
    for bad in ("", cipher.encrypt_state("plain text"), cipher.encrypt_state('{"sub": "u"}')):
        with pytest.raises(OAuthError) as err:
            decode_state(cipher, bad)
        assert err.value.code == "invalid_state"


def test_state_expired(cipher):
    old = _state(cipher, now=time.time() - 601)
    with pytest.raises(OAuthError) as err:
        decode_state(cipher, old)
    assert err.value.code == "expired_state"


def test_state_is_expired_exactly_at_exp_and_valid_just_before(cipher):
    state = _state(cipher, now=1000.0)  # exp = 1600.0
    assert decode_state(cipher, state, now=1599.999).sub == "u1"
    for at in (1600.0, 1600.001):
        with pytest.raises(OAuthError) as err:
            decode_state(cipher, state, now=at)
        assert err.value.code == "expired_state"


def test_state_still_valid_at_nine_minutes(cipher):
    assert decode_state(cipher, _state(cipher, now=time.time() - 540)).sub == "u1"


def test_state_nonce_differs(cipher):
    assert decode_state(cipher, _state(cipher)).nonce != decode_state(cipher, _state(cipher)).nonce
