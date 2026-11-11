"""A directory WITHOUT ``apply_profile`` (attribute absent)."""

from .fakes import FakeDirectory


class BareDirectory:
    """A directory WITHOUT ``apply_profile`` (attribute absent): forwards the 12 ``UserDirectory`` methods."""

    def __init__(self, inner: FakeDirectory | None = None) -> None:
        self.inner = inner or FakeDirectory()

    def find_by_identity(self, session, provider, subject):
        return self.inner.find_by_identity(session, provider, subject)

    def find_by_id(self, session, user_id):
        return self.inner.find_by_id(session, user_id)

    def find_invite(self, session, emails, provider, *, subject=None):
        return self.inner.find_invite(session, emails, provider, subject=subject)

    def link_identity(self, session, user, provider, subject):
        return self.inner.link_identity(session, user, provider, subject)

    def check_allowed(self, session, user, provider):
        return self.inner.check_allowed(session, user, provider)

    def capabilities(self, session, user):
        return self.inner.capabilities(session, user)

    def session_spec(self, session, user):
        return self.inner.session_spec(session, user)

    def public(self, session, user):
        return self.inner.public(session, user)

    def record_sign_in(self, session, user, *, provider, ip, first):
        return self.inner.record_sign_in(session, user, provider=provider, ip=ip, first=first)

    def record_refusal(self, session, reason, *, email, user, provider, ip):
        return self.inner.record_refusal(session, reason, email=email, user=user, provider=provider, ip=ip)

    def mark_sessions_invalid(self, session, user, at):
        return self.inner.mark_sessions_invalid(session, user, at)

    def provider_alive(self, session, user, provider):
        return self.inner.provider_alive(session, user, provider)
