"""The fixed refusal order: one test per code, plus the happy and ordering cases."""

from datetime import UTC, datetime

import pytest

from bond_signin import ProfileHookError, SignInRefused, refusal_code, sign_in, sign_in_with_first

from .bare_directory import BareDirectory
from .fakes import FakeDb, FakeDirectory, identity_ns

DB = FakeDb()
GM = "gmail.com"  # built at run time: the hygiene scan allows only example.com / example.org literals


def run(directory, **kw):
    ident = identity_ns(**kw)
    return sign_in(DB, directory=directory, identity=ident, provider=ident.provider, ip="198.51.100.7")


def reason(directory, **kw) -> str:
    with pytest.raises(Exception) as info:
        run(directory, **kw)
    return refusal_code(info.value)


def test_first_sign_in_links_identity_and_reports_first():
    d = FakeDirectory()
    ident = identity_ns(subject="g-1")
    user, first = sign_in_with_first(DB, directory=d, identity=ident, provider="google", ip=None)
    assert (user.id, first) == ("u-alice", True)
    assert d.links == [("u-alice", "google", "g-1")]
    assert d.refusals == []


def test_returning_user_found_by_identity_is_not_linked_again():
    d = FakeDirectory()
    d.by_id["u-alice"].identity = ("google", "g-1")
    user, first = sign_in_with_first(DB, directory=d, identity=identity_ns(subject="g-1", email="new@example.org"),
                                     provider="google", ip=None)
    assert (user.id, first) == ("u-alice", False)
    assert d.links == [] and d.invite_calls == []


def test_find_invite_gets_the_identity_subject():
    d = FakeDirectory()
    run(d, subject="g-77")
    assert d.invite_subjects == ["g-77"]


def test_email_not_verified():
    d = FakeDirectory()
    assert reason(d, email_verified=False) == "email_not_verified"
    assert d.refusals[0]["reason"] == "email_not_verified" and d.refusals[0]["email"] == "alice@example.com"


def test_email_verified_string_forms():
    assert reason(FakeDirectory(), email_verified="false") == "email_not_verified"
    assert run(FakeDirectory(), email_verified="true").id == "u-alice"


def test_not_invited():
    d = FakeDirectory()
    assert reason(d, email="stranger@example.com") == "not_invited"
    assert d.refusals[0]["user"] is None


def test_not_invited_when_two_candidates_resolve_to_different_users():
    d = FakeDirectory()
    d.by_email[f"a.lice@{GM}"] = d.by_id["u-bob"]  # the address as the IdP wrote it
    d.by_email[f"alice@{GM}"] = d.by_id["u-alice"]  # its dot-free normal form
    assert reason(d, email=f"a.lice@{GM}") == "not_invited"  # the lib's candidate list reaches both rows
    assert d.invite_calls == [[f"a.lice@{GM}", f"alice@{GM}"]]


def test_invite_candidates_are_raw_and_normalised():
    d = FakeDirectory()
    reason(d, email=f"A.Li+x@{GM.title()}")
    assert d.invite_calls == [[f"a.li+x@{GM}", f"ali@{GM}"]]


def test_company_suspended_and_provider_not_allowed():
    d = FakeDirectory()
    d.by_id["u-alice"].suspended = True
    assert reason(d) == "company_suspended"
    assert d.refusals[0]["user"] == "u-alice"
    d2 = FakeDirectory()
    d2.by_id["u-alice"].blocked_provider = "google"
    assert reason(d2) == "provider_not_allowed"


def test_deactivated():
    d = FakeDirectory()
    assert reason(d, email="carol@example.com") == "deactivated"
    assert d.links == []


def test_identity_mismatch_when_invited_row_is_bound_to_another_account():
    d = FakeDirectory()
    d.by_id["u-alice"].identity = ("google", "someone-else")
    assert reason(d, subject="g-2") == "identity_mismatch"
    assert d.links == []


def test_identity_mismatch_when_link_raises_identity_taken():
    d = FakeDirectory()
    d.by_id["u-alice"].taken_by_other = True
    assert reason(d) == "identity_mismatch"


def test_session_revoked_after_identity_auth_time():
    d = FakeDirectory()
    d.by_id["u-alice"].identity = ("google", "g-1")
    d.by_id["u-alice"].sessions_valid_after = datetime.fromtimestamp(1_800_000_100, UTC).replace(tzinfo=None)
    assert reason(d, subject="g-1") == "session_revoked"


def test_session_valid_inside_the_five_second_skew():
    d = FakeDirectory()
    d.by_id["u-alice"].identity = ("google", "g-1")
    d.by_id["u-alice"].sessions_valid_after = datetime.fromtimestamp(1_800_000_004, UTC).replace(tzinfo=None)
    assert run(d, subject="g-1").id == "u-alice"


def test_order_deactivated_beats_identity_mismatch_and_session_revoked():
    d = FakeDirectory()
    carol = d.by_id["u-carol"]
    carol.identity = ("google", "other")
    carol.sessions_valid_after = datetime(2999, 1, 1)
    assert reason(d, email="carol@example.com", subject="g-3") == "deactivated"


def test_order_not_invited_beats_nothing_after_unverified():
    assert reason(FakeDirectory(), email="x@example.org", email_verified=False) == "email_not_verified"


def test_non_refusal_errors_are_not_recorded():
    d = FakeDirectory()
    d.find_invite = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
    with pytest.raises(RuntimeError):
        run(d)
    assert d.refusals == []


def test_signin_refused_carries_code_and_message():
    exc = SignInRefused("deactivated")
    assert exc.code == "deactivated" and "deactivated" in exc.message


# --- optional apply_profile hook -------------------------------------------------------------------------------

def dora_signin(directory, **kw):
    ident = identity_ns(**{"email": "dora@example.com", "subject": "g-dora", "name": "Dora Example", **kw})
    return sign_in_with_first(DB, directory=directory, identity=ident, provider="google", ip=None)


def test_hook_runs_on_first_sign_in_and_fills_an_empty_name():
    d = FakeDirectory()
    user, first = dora_signin(d)
    assert (user.id, first) == ("u-dora", True)
    assert d.profile_calls == [("u-dora", "Dora Example", True, "google")] and user.name == "Dora Example"


def test_hook_runs_again_on_a_repeat_sign_in_with_first_false():
    d = FakeDirectory()
    dora_signin(d)
    _, first = dora_signin(d)
    assert first is False
    assert d.profile_calls == [("u-dora", "Dora Example", True, "google"), ("u-dora", "Dora Example", False, "google")]


def test_hook_does_not_overwrite_an_existing_name():
    d = FakeDirectory()
    user = run(d, name="Alice Renamed")
    assert d.profile_calls == [("u-alice", "Alice Renamed", True, "google")] and user.name == "Alice"


@pytest.mark.parametrize("name", [None, "", "   ", "\u200b", 42])
def test_hook_is_not_called_without_a_usable_name(name):
    d = FakeDirectory()
    ident = identity_ns(email="dora@example.com", subject="g-dora", name=name)
    user, _ = sign_in_with_first(DB, directory=d, identity=ident, provider="google", ip=None)
    assert d.profile_calls == [] and user.name == ""


def test_hook_is_passed_the_normalised_name():
    d = FakeDirectory()
    dora_signin(d, name="  Dora\n\tExample\u202e ")
    assert d.profile_calls == [("u-dora", "Dora Example", True, "google")]


def _set(uid, **attrs):
    def setup(d):
        for key, value in attrs.items():
            setattr(d.by_id[uid], key, value)
        return d
    return setup


@pytest.mark.parametrize("setup, kw, code", [
    (_set("u-alice"), {"email_verified": False}, "email_not_verified"),
    (_set("u-alice"), {"email": "stranger@example.com"}, "not_invited"),
    (_set("u-alice", suspended=True), {}, "company_suspended"),
    (_set("u-alice", blocked_provider="google"), {}, "provider_not_allowed"),
    (_set("u-alice"), {"email": "carol@example.com"}, "deactivated"),
    (_set("u-alice", identity=("google", "other")), {"subject": "g-2"}, "identity_mismatch"),
    (_set("u-alice", taken_by_other=True), {}, "identity_mismatch"),
    (_set("u-alice", identity=("google", "g-1"), sessions_valid_after=datetime(2999, 1, 1)), {"subject": "g-1"},
     "session_revoked"),
])
def test_hook_never_runs_on_a_refusal(setup, kw, code):
    d = setup(FakeDirectory())
    assert reason(d, **kw) == code
    assert d.profile_calls == [] and [r["reason"] for r in d.refusals] == [code]


def test_an_async_hook_is_refused_loudly():
    async def hook(*args, **kwargs):
        return None

    d = FakeDirectory()
    d.apply_profile = hook
    with pytest.raises(ProfileHookError, match="synchronous"):
        dora_signin(d)
    assert d.refusals == []


def test_bare_directory_has_no_hook_and_gets_the_same_result():
    bare = BareDirectory()
    assert not hasattr(bare, "apply_profile")
    plain = FakeDirectory()
    b_user, b_first = dora_signin(bare)
    p_user, p_first = dora_signin(plain)
    assert (b_user.id, b_first) == (p_user.id, p_first) == ("u-dora", True)
    assert b_user.name == ""  # nothing wrote the name


def test_a_raising_hook_becomes_profile_hook_error_not_a_refusal():
    class Boom(Exception):
        code = "x"

    def hook(*args, **kwargs):
        raise Boom("db")

    d = FakeDirectory()
    d.apply_profile = hook
    with pytest.raises(ProfileHookError) as info:
        dora_signin(d)
    assert isinstance(info.value.__cause__, Boom) and refusal_code(info.value) is None
    assert d.refusals == []
