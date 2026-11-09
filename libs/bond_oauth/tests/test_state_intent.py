"""State 0.2.0: intent, sign-in fields, compactness, and old states."""

import json

import pytest

from bond_oauth import OAuthError, decode_state, encode_state


def old_state(cipher, **over):
    """A state exactly as 0.1.0 minted it: no intent, no new fields."""
    data = {"sub": "u1", "provider": "google", "connection_name": "google", "nonce": "n", "exp": 9e12,
            "verifier": "v", "redirect_to": "http://app/x", "shared": False, "native": False}
    data.update(over)
    return cipher.encrypt_state(json.dumps(data))


def test_old_state_decodes_as_connect(cipher):
    payload = decode_state(cipher, old_state(cipher))
    assert payload.intent == "connect" and payload.sub == "u1"
    assert payload.device_hash is None and payload.oidc_nonce is None and payload.expected_subject is None


def test_old_callers_keep_working_and_default_to_connect(cipher):
    state = encode_state(cipher, sub="u1", provider="g", connection_name="g", verifier="v", redirect_to="x")
    assert decode_state(cipher, state).intent == "connect"


def test_signin_state_round_trips_sub_none_not_the_string_none(cipher):
    state = encode_state(cipher, sub=None, provider="google", connection_name="google", verifier="v",
                         redirect_to="http://app/x", intent="signin")
    payload = decode_state(cipher, state)
    assert payload.sub is None and payload.intent == "signin"


def test_all_new_fields_round_trip(cipher):
    state = encode_state(cipher, sub="u1", provider="g", connection_name="g", verifier="v", redirect_to="x",
                         intent="signin", device_hash="d" * 64, attempt_id="a-1", oidc_nonce="o", set_id="mail",
                         login_hint="a@example.com", expected_subject="s-1", nonce="fixed")
    p = decode_state(cipher, state)
    assert (p.device_hash, p.attempt_id, p.oidc_nonce, p.set_id, p.login_hint, p.expected_subject, p.nonce) == (
        "d" * 64, "a-1", "o", "mail", "a@example.com", "s-1", "fixed")


def test_connect_state_without_a_subject_is_invalid(cipher):
    with pytest.raises(OAuthError) as caught:
        decode_state(cipher, old_state(cipher, sub=None))
    assert caught.value.code == "invalid_state"


def test_unknown_intent_is_invalid(cipher):
    with pytest.raises(OAuthError) as caught:
        decode_state(cipher, old_state(cipher, intent="admin"))
    assert caught.value.code == "invalid_state"


def test_a_fully_loaded_signin_state_stays_under_1200_chars(cipher):
    state = encode_state(cipher, sub=None, provider="microsoft", connection_name="microsoft",
                         verifier="v" * 86, redirect_to="https://app.example.com/some/long/return/path?x=1",
                         intent="signin", device_hash="d" * 64, attempt_id="a" * 64, oidc_nonce="o" * 64,
                         set_id="office", login_hint="someone.long@example.com", native=True)
    assert len(state) < 1200


def test_the_payload_json_is_compact_and_omits_unset_fields(cipher):
    state = encode_state(cipher, sub=None, provider="g", connection_name="g", verifier="v", redirect_to="x",
                         intent="signin")
    raw = cipher.decrypt_state(state)
    assert " " not in raw and "\n" not in raw and "device_hash" not in raw and "login_hint" not in raw
