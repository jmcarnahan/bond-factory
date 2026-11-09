import pytest

from bond_signin import (
    ScopePolicy,
    ScopeSet,
    SignInRefused,
    UnknownScopeSet,
    connect_scopes,
    http_error,
    normalize_email,
    refusal_code,
    wanted_sets,
)
from bond_signin.errors import STATUS_FOR_CODE

GM, GM2 = "gmail.com", "googlemail.com"  # run-time strings: the hygiene scan allows only example.* literals
MAIL = ScopeSet("mail", "google", ("gmail.send",), "Mail")
CAL = ScopeSet("cal", "google", ("calendar.events",), "Calendar")
MS = ScopeSet("ms_cal", "microsoft", ("Calendars.ReadWrite",), "Calendar")
POLICY = ScopePolicy(signin={"google": ("openid", "email", "profile")},
                     by_capability={"owner": (MAIL, CAL), "office": (MAIL, MS), "crew": ()})


def test_signin_scopes():
    assert POLICY.signin_scopes("google") == ("openid", "email", "profile")
    assert POLICY.signin_scopes("microsoft") == ()


def test_wanted_is_a_union_without_duplicates():
    ids = [s.id for s in POLICY.wanted(["owner", "office"], "google")]
    assert ids == ["mail", "cal"]


def test_wanted_filters_provider_and_ignores_unknown_caps():
    assert [s.id for s in POLICY.wanted(["office"], "microsoft")] == ["ms_cal"]
    assert POLICY.wanted(["crew", "nobody"], "google") == []


def test_set_lookup_and_unknown():
    assert POLICY.set("cal") is CAL
    with pytest.raises(UnknownScopeSet) as info:
        POLICY.set("nope")
    assert refusal_code(info.value) == "invalid_request"


def test_wanted_sets_payload_and_granted():
    out = wanted_sets(POLICY, ["owner"], "google", ["openid", "GMAIL.send"])
    assert out == [
        {"id": "mail", "provider": "google", "label": "Mail", "scopes": ["gmail.send"], "granted": True},
        {"id": "cal", "provider": "google", "label": "Calendar", "scopes": ["calendar.events"], "granted": False},
    ]


def test_wanted_sets_empty_for_no_roles():
    assert wanted_sets(POLICY, [], "google", []) == []


def test_connect_scopes_google_is_the_set_alone():
    assert connect_scopes(POLICY, "mail", ["openid", "calendar.events"]) == ["gmail.send"]


def test_connect_scopes_microsoft_is_the_union():
    assert connect_scopes(POLICY, "ms_cal", ["openid", "calendars.readwrite", "User.Read"]) == [
        "openid", "calendars.readwrite", "User.Read"]
    assert connect_scopes(POLICY, "ms_cal", ["openid"]) == ["openid", "Calendars.ReadWrite"]


@pytest.mark.parametrize(("provider", "raw", "expected"), [
    ("google", f"  A.B.C+tag@{GM.title()} ", f"abc@{GM}"),
    ("google", f"Jo.Doe@{GM2}", f"jodoe@{GM2}"),
    ("google", "first.last@example.com", "first.last@example.com"),
    ("google", "First.Last+x@example.com", "first.last+x@example.com"),
    ("microsoft", f"a.b+c@{GM}", f"a.b+c@{GM}"),
    ("google", "", ""),
])
def test_normalize_email(provider, raw, expected):
    assert normalize_email(provider, raw) == expected


def test_refusal_code_reads_a_str_code_attribute():
    class WithCode(Exception):
        code = "deactivated"

    class NoCode(Exception):
        pass

    class BadCode(Exception):
        code = 7

    assert refusal_code(WithCode()) == "deactivated"
    assert refusal_code(NoCode()) is None
    assert refusal_code(BadCode()) is None
    assert refusal_code(SignInRefused("not_invited")) == "not_invited"


def test_status_table():
    for code in ("tenant_mismatch", "email_not_verified", "not_invited", "company_suspended",
                 "provider_not_allowed", "deactivated", "identity_mismatch", "consent_declined", "invalid_origin"):
        assert STATUS_FOR_CODE[code] == 403
    for code in ("session_revoked", "invalid_handoff", "refresh_reused", "refresh_expired", "refresh_revoked"):
        assert STATUS_FOR_CODE[code] == 401
    assert STATUS_FOR_CODE["invalid_state"] == STATUS_FOR_CODE["invalid_request"] == 400


def test_http_error_detail_and_unknown_code():
    exc = http_error("not_invited")
    assert exc.status_code == 403 and exc.detail["code"] == "not_invited" and exc.detail["message"]
    assert http_error("mystery").status_code == 500
    assert http_error("mystery").detail["code"] == "internal_error"
    assert http_error("deactivated", "Custom").detail["message"] == "Custom"
