from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from bond_signin import CookiePolicy, ScopePolicy, ScopeSet, SignInSettings, make_signin_router

from .fakes import FakeDb, FakeDirectory, FakeFlow, FakeHandoffs, FakeSessions

APP_ORIGIN = "https://app.example.org"
OWN_ORIGIN = "http://testserver"
GMAIL = ("https://www.googleapis.com/auth/gmail.send",)
POLICY = ScopePolicy(
    signin={"google": ("openid", "email", "profile"),
            "microsoft": ("openid", "profile", "email", "offline_access", "User.Read", "Mail.Send")},
    by_capability={"connections.manage": (ScopeSet("mail", "google", GMAIL, "Send e-mail"),)},
)
COOKIES = CookiePolicy(
    access_name="app_access_token", refresh_name="app_refresh_token",
    access_cookie=lambda secure: {"httponly": True, "secure": secure, "samesite": "lax", "path": "/", "max_age": 3600},
    refresh_cookie=lambda secure: {"httponly": True, "secure": secure, "samesite": "lax", "path": "/auth",
                                   "max_age": 5_184_000},
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Harness(SimpleNamespace):
    pass


def make_settings(**kw) -> SignInSettings:
    base = {"providers": ("google", "microsoft"), "public_base": OWN_ORIGIN, "allow_http": True,
            "cookie_secure": False, "redirect_allowlist": (APP_ORIGIN,), "native_schemes": ("com.example.app",)}
    return SignInSettings(**{**base, **kw})


def build(directory=None, **kw) -> Harness:
    h = Harness(db=FakeDb(), directory=directory or FakeDirectory(), flow=FakeFlow(), handoffs=FakeHandoffs(),
                sessions=FakeSessions(), limits=[], current=None, legacy_calls=[])
    h.settings = kw.pop("settings", None) or make_settings()

    def rate_limit(request, key):
        h.limits.append(key)

    def session_dep(request):
        return h.current

    def legacy(request, body):
        h.legacy_calls.append(body)
        return {"legacy": True}

    app = FastAPI()
    app.include_router(make_signin_router(
        directory=h.directory, flow=h.flow, handoffs=h.handoffs, sessions=h.sessions, policy=POLICY,
        settings=h.settings, cookies=COOKIES, session_dep=session_dep, client_ip=lambda r: "203.0.113.9",
        session_scope=h.db.scope, connection_model="CONN", rate_limit=rate_limit, legacy_refresh=legacy,
        include_providers=True, providers_payload=lambda: {"firebase": False}, **kw))

    @app.exception_handler(HTTPException)
    async def _http(request, exc):  # same shape the service kit gives: {"detail": {...}}
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    h.app = app
    h.client = TestClient(app, base_url=OWN_ORIGIN, follow_redirects=False)
    return h


@pytest.fixture
def h() -> Harness:
    return build()


def start_web(h: Harness, provider="google", client=None, origin=APP_ORIGIN, redirect_to=None):
    client = client or h.client
    return client.post(f"/auth/signin/{provider}/start", headers={"Origin": origin},
                       json={"redirect_to": redirect_to or f"{APP_ORIGIN}/done", "mode": "web"})


def state_of(resp) -> str:
    return resp.json()["url"].split("state=")[1]


def native_start(h: Harness, secret="s" * 32, attempt="att_1", provider="google", redirect_to=None):
    body = {"mode": "native", "device_challenge": sha(secret), "attempt": attempt,
            "redirect_to": redirect_to or f"{OWN_ORIGIN}/app/return/{provider}"}
    return h.client.post(f"/auth/signin/{provider}/start", json=body)
