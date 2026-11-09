from datetime import UTC, datetime, timedelta

import pytest

from bond_auth_py import AuthUnavailable, Identity, MockIdentities, MockIdentityAdmin, janitor_after_refusal

NOW = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)
NAIVE = NOW.replace(tzinfo=None)


class Rig:
    def __init__(self, provider="google.com", providers=None, age=10, exists=False):
        self.store = MockIdentities()
        self.admin = MockIdentityAdmin(self.store)
        self.store.add_identity("uid-1", "stray@example.com", providers=[provider] if providers is None else providers,
                                created_at=NAIVE - timedelta(seconds=age))
        self.identity = Identity("uid-1", "stray@example.com", sign_in_provider=provider)
        self.exists = exists
        self.asked, self.audited = [], []

    def user_exists(self, uid, email):
        self.asked.append((uid, email))
        return self.exists

    def run(self, **kw):
        return janitor_after_refusal(identity=self.identity, admin=self.admin, user_exists=self.user_exists,
                                     now=kw.pop("now", NOW), audit=lambda uid, p: self.audited.append((uid, p)),
                                     **kw)


def gone(rig):
    return rig.store.by_uid("uid-1") is None


@pytest.mark.parametrize("provider", ["google.com", "apple.com"])
def test_deletes_a_fresh_stray_and_audits(provider):
    rig = Rig(provider=provider)
    assert rig.run() is True
    assert gone(rig) and rig.audited == [("uid-1", provider)]
    assert rig.asked == [("uid-1", "stray@example.com")] * 2  # before the lookup and again before the delete


@pytest.mark.parametrize("provider", ["password", "facebook.com", "microsoft.com"])
def test_other_providers_are_never_touched(provider):
    rig = Rig(provider=provider)
    assert rig.run() is False and not gone(rig) and rig.asked == [] and rig.audited == []


def test_age_window_and_skew_boundaries():
    assert Rig(age=59).run() is True
    assert Rig(age=60).run() is False  # the window is exclusive
    assert Rig(age=3600).run() is False
    assert Rig(age=-5).run() is True  # the provider's clock up to 5 s ahead
    assert Rig(age=-6).run() is False
    assert Rig(age=-20).run(skew=30) is True
    assert Rig(age=100).run(window_seconds=120) is True


def test_naive_now_is_taken_as_utc():
    assert Rig(age=10).run(now=NAIVE) is True


def test_provider_data_must_be_exactly_that_provider():
    for providers in (["google.com", "password"], ["password", "google.com"], [], ["apple.com"]):
        rig = Rig(provider="google.com", providers=providers)
        assert rig.run() is False and not gone(rig)


def test_existing_user_row_means_it_is_not_a_stray():
    rig = Rig(exists=True)
    assert rig.run() is False and not gone(rig) and rig.audited == []


def test_row_that_lands_between_the_checks_saves_the_identity():
    rig = Rig()
    answers = iter([False, True])
    rig.user_exists = lambda uid, email: next(answers)
    assert rig.run() is False and not gone(rig)


def test_missing_identity_or_creation_time():
    rig = Rig()
    rig.store.by_email.clear()
    assert rig.run() is False
    rig = Rig()
    rig.admin.get_user = lambda **kw: {"uid": "uid-1", "providers": ["google.com"], "created_at": None}
    assert rig.run() is False


def test_never_raises():
    rig = Rig()
    rig.store.unavailable = True  # provider down
    assert rig.run() is False
    rig = Rig()
    rig.user_exists = lambda uid, email: (_ for _ in ()).throw(RuntimeError("db down"))
    assert rig.run() is False

    rig = Rig()

    def boom(uid):
        raise AuthUnavailable("delete failed")

    rig.admin.delete_user = boom
    assert rig.run() is False and rig.audited == []
    rig = Rig()
    assert janitor_after_refusal(identity=rig.identity, admin=rig.admin, user_exists=rig.user_exists, now=NOW,
                                 audit=lambda uid, p: 1 / 0) is True  # deleted; a failing audit changes nothing
    assert gone(rig)


def test_no_audit_hook_is_fine():
    rig = Rig()
    assert janitor_after_refusal(identity=rig.identity, admin=rig.admin, user_exists=rig.user_exists, now=NOW)
    assert gone(rig)


def test_empty_uid_is_skipped():
    rig = Rig()
    rig.identity = Identity("", "stray@example.com", sign_in_provider="google.com")
    assert rig.run() is False
