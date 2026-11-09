"""``identity_from_token_response``: claim checks, subjects, tenants."""

import pytest
from jwt_util import (
    CLIENT,
    NOW,
    OID,
    TID,
    google,
    google_claims,
    make_jwt,
    microsoft,
    microsoft_claims,
    token_set,
)

from bond_oauth import FakeOAuth, MicrosoftOAuth, OAuthError, identity_from_token_response


def read(provider, name, tokens, **kw):
    kw.setdefault("expected_nonce", "n1")
    kw.setdefault("client_id", CLIENT)
    kw.setdefault("now", NOW)
    return identity_from_token_response(name, provider, tokens, **kw)


def refused(provider, name, tokens, code="invalid_id_token", **kw):
    with pytest.raises(OAuthError) as caught:
        read(provider, name, tokens, **kw)
    assert caught.value.code == code


def test_google_identity_fields():
    who = read(google(), "google", token_set(google_claims()))
    assert (who.provider, who.subject, who.tenant, who.hd) == ("google", "g-123", None, "example.com")
    assert who.email == "ann@example.com" and who.email_verified is True and who.name == "Ann"
    assert who.auth_time == NOW and who.raw_claims["sub"] == "g-123"


def test_auth_time_claim_wins_over_now():
    assert read(google(), "google", token_set(google_claims(auth_time=1_700_000_000))).auth_time == 1_700_000_000.0


def test_both_google_issuer_forms_are_accepted():
    read(google(), "google", token_set(google_claims(iss="accounts.google.com")))


def test_forged_issuer_is_refused():
    refused(google(), "google", token_set(google_claims(iss="https://accounts.google.com.evil.example")))
    refused(google(), "google", token_set(google_claims(iss=None)))


def test_microsoft_issuer_must_embed_the_tokens_own_tid():
    refused(microsoft(), "microsoft", token_set(microsoft_claims(iss="https://login.microsoftonline.com/other/v2.0")))
    refused(microsoft(), "microsoft", token_set(microsoft_claims(tid=None)))


def test_wrong_audience_is_refused_and_a_list_with_the_client_is_accepted():
    refused(google(), "google", token_set(google_claims(aud="someone-else")))
    refused(google(), "google", token_set(google_claims(aud=["a", "b"])))
    read(google(), "google", token_set(google_claims(aud=["a", CLIENT])))


def test_expired_and_missing_exp_are_refused():
    refused(google(), "google", token_set(google_claims(exp=NOW - 1)))
    refused(google(), "google", token_set(google_claims(exp=NOW)))
    refused(google(), "google", token_set(google_claims(exp=None)))


def test_wrong_or_missing_nonce_is_refused_and_skipped_when_not_expected():
    refused(google(), "google", token_set(google_claims(nonce="other")))
    refused(google(), "google", token_set(google_claims(nonce=None)))
    read(google(), "google", token_set(google_claims(nonce=None)), expected_nonce=None)


def test_alg_none_is_refused_on_a_real_provider_and_accepted_on_the_fake():
    unsigned = {"alg": "none", "typ": "JWT"}
    refused(google(), "google", token_set(google_claims(), header=unsigned))
    refused(microsoft(), "microsoft", token_set(microsoft_claims(), header={"alg": "NONE"}))
    fake_claims = google_claims(iss="https://fake.invalid")
    assert read(FakeOAuth("/c"), "fake-google", token_set(fake_claims, header=unsigned)).subject == "g-123"


def test_the_fake_issuer_is_not_accepted_by_a_real_provider():
    refused(google(), "google", token_set(google_claims(iss="https://fake.invalid")))


@pytest.mark.parametrize("raw", ["", "only.two", "a.b.c.d", "!!!.???.sig", make_jwt(["not", "a", "dict"])])
def test_malformed_tokens_are_refused(raw):
    refused(google(), "google", token_set(raw_token=raw))


def test_missing_id_token_is_refused():
    from bond_oauth import TokenSet
    refused(google(), "google", TokenSet(access_token="a", raw={}))


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), ("true", True), ("True", True),
                                            ("false", False), (None, False), ("yes", False), (1, False)])
def test_email_verified_accepts_bool_or_string_forms(value, expected):
    claims = google_claims(email_verified=value)
    assert read(google(), "google", token_set(claims)).email_verified is expected


def test_microsoft_subject_is_tid_colon_oid_and_email_comes_from_mail_first():
    who = read(microsoft(), "microsoft", token_set(microsoft_claims()), userinfo={"mail": " Ann.Mail@example.org "})
    assert who.subject == f"{TID}:{OID}" and who.tenant == TID and who.email == "ann.mail@example.org"
    assert who.email_verified is True and who.hd is None


def test_microsoft_email_falls_back_to_id_token_email_then_preferred_username():
    assert read(microsoft(), "microsoft", token_set(microsoft_claims(email="x@example.org"))).email == "x@example.org"
    assert read(microsoft(), "microsoft", token_set(microsoft_claims())).email == "ann@example.org"


def test_microsoft_without_a_pin_is_never_verified():
    who = read(microsoft(None), "microsoft", token_set(microsoft_claims()))
    assert who.email_verified is False and who.tenant == TID


def test_tenant_mismatch_is_refused():
    other = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    claims = microsoft_claims(tid=other, iss=f"https://login.microsoftonline.com/{other}/v2.0")
    refused(microsoft(), "microsoft", token_set(claims), code="tenant_mismatch")
    read(microsoft(), "microsoft", token_set(claims), pinned_tenant=other)  # the argument overrides the provider's pin


@pytest.mark.parametrize("over", [{"idtyp": "guest"}, {"preferred_username": "ann_corp.example#EXT#@x.onmicrosoft.com"}])
def test_guests_are_refused(over):
    refused(microsoft(), "microsoft", token_set(microsoft_claims(**over)), code="tenant_mismatch")


def me(**over):
    """A realistic /me answer, as MicrosoftOAuth.userinfo shapes it."""
    return {"email": "ann@example.org", "mail": "ann@example.org", "upn": "ann@example.org", "user_type": "Member",
            "name": "Ann", "id": OID, **over}


def test_a_member_me_answer_is_accepted():
    assert read(microsoft(), "microsoft", token_set(microsoft_claims()), userinfo=me()).email == "ann@example.org"


@pytest.mark.parametrize("info", [
    me(upn="ann_partner.example.org#EXT#@example.org", mail="ann@example.com", user_type="Guest"),
    me(upn="ann_partner.example.org#ext#@example.org"),
    me(user_type="guest"),
])
def test_a_guest_me_answer_is_refused(info):
    refused(microsoft(), "microsoft", token_set(microsoft_claims()), code="tenant_mismatch", userinfo=info)


def test_idp_claim_naming_another_provider_is_refused_and_the_tenants_own_forms_pass():
    refused(microsoft(), "microsoft", token_set(microsoft_claims(idp="https://sts.windows.net/other-tenant/")),
            code="tenant_mismatch")
    refused(microsoft(), "microsoft", token_set(microsoft_claims(idp="live.com")), code="tenant_mismatch")
    read(microsoft(), "microsoft", token_set(microsoft_claims(idp=f"https://sts.windows.net/{TID}/")))
    read(microsoft(), "microsoft", token_set(microsoft_claims(idp=f"https://login.microsoftonline.com/{TID}/v2.0")))


def test_microsoft_userinfo_exposes_mail_upn_and_user_type():
    import httpx
    body = {"mail": "m@example.org", "userPrincipalName": "u@example.org", "userType": "Member", "displayName": "M",
            "id": "oid-1"}
    ms = MicrosoftOAuth("c", "s", http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))))
    info = ms.userinfo("tok")
    assert (info["mail"], info["upn"], info["user_type"], info["id"]) == ("m@example.org", "u@example.org", "Member", "oid-1")


@pytest.mark.parametrize("exp", ["nan", "inf", "-inf", float("nan"), float("inf"), "soon", [1], {"a": 1}])
def test_exp_must_be_a_finite_number_in_the_future(exp):
    import json as _json
    token = make_jwt(google_claims()).split(".")
    claims = _json.loads(__import__("base64").urlsafe_b64decode(token[1] + "=="))
    claims["exp"] = exp
    from jwt_util import b64
    # json.dumps writes NaN/Infinity for float values; strings and lists go through unchanged
    raw = f"{token[0]}.{b64(claims)}.sig"
    refused(google(), "google", token_set(raw_token=raw))


@pytest.mark.parametrize("value", [["ann@example.com"], 5, {"a": "b"}, True])
def test_a_non_string_email_claim_is_missing_not_coerced(value):
    assert read(google(), "google", token_set(google_claims(email=value))).email == ""
    claims = microsoft_claims(email=value, preferred_username="p@example.org")
    assert read(microsoft(), "microsoft", token_set(claims), userinfo={"mail": ["x@example.org"]}).email == "p@example.org"


def test_me_url_selects_user_type_so_guest_detection_sees_it():
    from bond_oauth.microsoft import ME_URL

    assert "$select=" in ME_URL and "userType" in ME_URL and "userPrincipalName" in ME_URL
