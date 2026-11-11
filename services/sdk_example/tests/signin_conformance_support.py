"""Test-local pieces of the sign-in conformance test: models on a private Base, a small UserDirectory and a builder
that wires the REAL bond_oauth / bond_auth_py classes into ``bond_signin.make_signin_router``."""

from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from bond_auth_py import (
    AuthSettings,
    SessionsMixin,
    SessionSpec,
    SessionStore,
    cookie_name,
    decode_claims,
    refresh_cookie_name,
    refresh_cookie_params,
    session_cookie_params,
)
from bond_oauth import (
    MICROSOFT_SIGNIN_FULL,
    ConnectionsMixin,
    FakeOAuth,
    HandoffsMixin,
    HandoffStore,
    SignInFlow,
    TokenCipher,
)
from bond_oauth.fake import FAKE_TENANT, mock_code
from bond_signin import CookiePolicy, IdentityTaken, ScopePolicy, SignInSettings, make_signin_router
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Boolean, Column, DateTime, String, create_engine, func, select
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

GOOGLE, MICROSOFT = "fake-google", "fake-microsoft"
WEB_ORIGIN = "http://localhost:8078"
API_BASE = "http://testserver"
APP = "conf"
SECRET = "conformance-secret-conformance-secret-xx"
CLIENT_ID = "fake-client"
GOOGLE_SIGNIN_SCOPES = ("openid", "email", "profile")


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False, default="")
    capabilities = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    idp_provider = Column(String, nullable=True)
    idp_subject = Column(String, nullable=True)
    sessions_valid_after = Column(DateTime, nullable=True)
    last_sign_in_at = Column(DateTime, nullable=True)

    @property
    def identity(self) -> tuple[str, str] | None:
        return (self.idp_provider, self.idp_subject) if self.idp_provider else None


class Connection(ConnectionsMixin, Base):
    pass


class Handoff(HandoffsMixin, Base):
    pass


class AuthSession(SessionsMixin, Base):
    pass


class Directory:
    """The ~20 lines an app writes (structurally a ``bond_signin.UserDirectory``)."""

    def __init__(self) -> None:
        self.refusals: list[tuple[str, str | None, str]] = []  # (reason, email, provider)
        self.sign_ins: list[tuple[str, str, bool]] = []  # (user id, provider, first)

    def find_by_identity(self, s, provider, subject):
        return s.scalar(select(User).where(User.idp_provider == provider, User.idp_subject == subject))

    def find_by_id(self, s, user_id):
        return s.get(User, user_id)

    def find_invite(self, s, emails, provider, *, subject=None):
        rows = {u.id: u for u in s.scalars(select(User).where(func.lower(User.email).in_(list(emails))))}
        return next(iter(rows.values())) if len(rows) == 1 else None

    def link_identity(self, s, user, provider, subject):
        if s.scalar(select(User).where(User.idp_provider == provider, User.idp_subject == subject,
                                       User.id != user.id)):
            raise IdentityTaken()
        user.idp_provider, user.idp_subject = provider, subject

    def check_allowed(self, s, user, provider):
        return None

    def capabilities(self, s, user):
        return list(user.capabilities or [])

    def session_spec(self, s, user):
        return SessionSpec(sub=user.id, name=user.name, capabilities=self.capabilities(s, user))

    def public(self, s, user):
        return {"id": user.id, "email": user.email, "name": user.name, "capabilities": self.capabilities(s, user)}

    def apply_profile(self, s, user, profile, *, provider, first):  # optional hook: fill only when empty
        if not (user.name or "").strip():
            user.name = profile.name

    def record_sign_in(self, s, user, *, provider, ip, first):
        user.last_sign_in_at = datetime.now().replace(tzinfo=None)
        self.sign_ins.append((user.id, provider, first))

    def record_refusal(self, s, reason, *, email, user, provider, ip):
        self.refusals.append((reason, email, provider))

    def mark_sessions_invalid(self, s, user, at):
        user.sessions_valid_after = at.replace(tzinfo=None)

    def provider_alive(self, s, user, provider):
        return None


class ClockedSessions:
    """The real ``SessionStore`` with a movable clock. The router passes no ``now``, so this proxy supplies it."""

    def __init__(self, store: SessionStore) -> None:
        self._store, self.offset = store, 0.0

    def now(self) -> float:
        return time.time() + self.offset

    def issue(self, session, **kw):
        return self._store.issue(session, now=kw.pop("now", None) or self.now(), **kw)

    def rotate(self, session, **kw):
        return self._store.rotate(session, now=kw.pop("now", None) or self.now(), **kw)

    def revoke_token(self, session, **kw):
        return self._store.revoke_token(session, **kw)

    def revoke_user(self, session, **kw):
        return self._store.revoke_user(session, **kw)


@dataclass
class Stack:
    app: FastAPI
    factory: sessionmaker
    directory: Directory
    flow: SignInFlow
    handoffs: HandoffStore
    store: SessionStore
    sessions: ClockedSessions
    cipher: TokenCipher
    auth: AuthSettings
    settings: SignInSettings
    google: FakeOAuth
    microsoft: FakeOAuth
    cookies: CookiePolicy
    rate_calls: list[str] = field(default_factory=list)

    @contextmanager
    def db(self):
        session = self.factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    def add_user(self, user_id: str, email: str, *, active: bool = True, caps: tuple[str, ...] = (),
                 name: str | None = None) -> None:
        """``name=None`` seeds the e-mail local part; an explicit ``""`` seeds an empty name."""
        with self.db() as s:
            s.add(User(id=user_id, email=email, name=email.split("@")[0] if name is None else name,
                       is_active=active,
                       capabilities=list(caps)))


def device_pair(secret: str = "device-secret-0123456789") -> tuple[str, str]:
    """``(device_secret, device_challenge)``: the challenge is sha256 hex of the secret."""
    return secret, hashlib.sha256(secret.encode()).hexdigest()


def build_stack(db_path: str, prefix: str = "/auth") -> Stack:
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    cipher = TokenCipher("conformance-oauth-key")
    google = FakeOAuth("http://testserver/fake-consent", kind="google", client_id=CLIENT_ID)
    microsoft = FakeOAuth("http://testserver/fake-consent", kind="microsoft", client_id=CLIENT_ID,
                          pinned_tenant=FAKE_TENANT)
    flow = SignInFlow(providers={GOOGLE: google, MICROSOFT: microsoft}, cipher=cipher,
                      client_ids={GOOGLE: CLIENT_ID, MICROSOFT: CLIENT_ID}, public_base=API_BASE,
                      pinned_tenants={MICROSOFT: FAKE_TENANT}, prefix=prefix)
    handoffs = HandoffStore(Handoff, cipher)
    auth = AuthSettings(jwt_secret=SECRET, app_name=APP)
    store = SessionStore(AuthSession, auth)
    sessions = ClockedSessions(store)
    cookies = CookiePolicy(
        cookie_name(APP), refresh_cookie_name(APP),
        lambda secure: session_cookie_params(auth, secure=secure, ttl_minutes=auth.session_access_ttl_minutes),
        lambda secure: refresh_cookie_params(auth, secure))
    settings = SignInSettings(providers=(GOOGLE, MICROSOFT), public_base=API_BASE, redirect_allowlist=(WEB_ORIGIN,),
                              cookie_secure=False, allow_http=True)
    policy = ScopePolicy(signin={GOOGLE: GOOGLE_SIGNIN_SCOPES, MICROSOFT: MICROSOFT_SIGNIN_FULL})
    directory = Directory()
    stack = Stack(FastAPI(), factory, directory, flow, handoffs, store, sessions, cipher, auth, settings, google,
                  microsoft, cookies)

    def session_dep(request: Request):
        token = request.cookies.get(cookies.access_name) or ""
        scheme, _, bearer = request.headers.get("authorization", "").partition(" ")
        token = bearer.strip() if scheme.lower() == "bearer" and bearer.strip() else token
        if not token:
            return None
        try:
            claims = decode_claims(token, auth)
        except Exception:  # noqa: BLE001
            return None
        with stack.db() as s:
            return s.get(User, claims.user_id)

    def client_ip(request: Request) -> str | None:
        return request.client.host if request.client else None

    router = make_signin_router(
        directory=directory, flow=flow, handoffs=handoffs, sessions=sessions, policy=policy, settings=settings,
        cookies=cookies, session_dep=session_dep, client_ip=client_ip, session_scope=stack.db,
        connection_model=Connection, rate_limit=lambda request, key: stack.rate_calls.append(key),
        prefix=prefix, include_providers=True, legacy_refresh=lambda request, body: {"legacy": True},
        labels={GOOGLE: "Fake Google", MICROSOFT: "Fake Microsoft"})
    stack.app.include_router(router)

    @stack.app.get(f"{prefix}/me")
    def me(request: Request):
        user = session_dep(request)
        if user is None:
            return {"detail": {"code": "invalid_token"}}
        with stack.db() as s:
            return directory.public(s, s.get(User, user.id))

    return stack


# shared test helpers and fixtures ----------------------------------------------------------------------
ACCESS, REFRESH = "conf_access_token", "conf_refresh_token"
ORIGIN = {"Origin": WEB_ORIGIN}
REDIRECT = f"{WEB_ORIGIN}/after"
NATIVE_RETURN = "http://testserver/app/return"


@pytest.fixture
def stack(tmp_path) -> Stack:
    st = build_stack(str(tmp_path / "conf.db"))
    st.add_user("u-google", "demo.google@example.com", caps=("connections.manage",))
    st.add_user("u-ms", "demo.microsoft@example.com", caps=("connections.manage",))
    st.add_user("u-off", "off@example.com", active=False)
    return st


@pytest.fixture
def client(stack) -> TestClient:
    return TestClient(stack.app, follow_redirects=False)


def count(stack: Stack, model) -> int:
    with stack.db() as s:
        return s.scalar(select(func.count()).select_from(model))


def code_of(response) -> str | None:
    body = response.json()
    detail = body.get("detail", body)
    return detail.get("code") if isinstance(detail, dict) else None


def web_start(client, provider=GOOGLE, **extra):
    r = client.post(f"/auth/signin/{provider}/start", json={"redirect_to": REDIRECT, "mode": "web"},
                    headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r, parse_qs(urlsplit(r.json()["url"]).query)["state"][0]


def callback(client, provider, state, email):
    """What the fake consent page does: the browser lands on the callback with the state and a mock code."""
    return client.get(f"/auth/signin/{provider}/callback", params={"state": state, "code": mock_code(email)})


def web_sign_in(client, provider=GOOGLE, email="demo.google@example.com"):
    _, state = web_start(client, provider)
    return callback(client, provider, state, email)


def reason_of(response) -> str | None:
    return parse_qs(urlsplit(response.headers["location"]).query).get("reason", [None])[0]


def native_start(client, challenge, attempt="att-1", provider=GOOGLE):
    r = client.post(f"/auth/signin/{provider}/start", json={
        "redirect_to": f"{NATIVE_RETURN}/{provider}", "mode": "native", "device_challenge": challenge,
        "attempt": attempt})
    assert r.status_code == 200, r.text
    return parse_qs(urlsplit(r.json()["url"]).query)["state"][0]


def native_sign_in(client, secret_pair=None, email="demo.google@example.com", provider=GOOGLE):
    secret, challenge = secret_pair or device_pair()
    state = native_start(client, challenge, provider=provider)
    return secret, callback(client, provider, state, email)


def redeem_pair(client, email="demo.google@example.com", provider=GOOGLE) -> dict:
    secret, cb = native_sign_in(client, email=email, provider=provider)
    code = parse_qs(urlsplit(cb.headers["location"]).query)["code"][0]
    r = client.post("/auth/signin/redeem", json={"code": code, "device_secret": secret})
    assert r.status_code == 200, r.text
    return r.json()

