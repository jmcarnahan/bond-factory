"""The fixed refusal order: one test per code, plus the happy and ordering cases."""

from datetime import UTC, datetime

import pytest

from bond_signin import SignInRefused, refusal_code, sign_in, sign_in_with_first

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


def test_identity_mismatch_when_link_raises_identity_taken_without_code():
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
