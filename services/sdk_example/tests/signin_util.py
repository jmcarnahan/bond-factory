"""What a person does in a browser, as plain requests against the real example app (fake mode)."""

from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from sdk_example.db import session_scope

ORIGIN = {"Origin": "http://localhost:8078"}  # the web app's origin: on the redirect allowlist
AUTH_PAGE = "http://localhost:8078/auth"
CONNECTIONS_PAGE = "http://localhost:8078/connections"
ACCESS, REFRESH = "sdk_example_access_token", "sdk_example_refresh_token"
GOOGLE, MICROSOFT = "fake-google", "fake-microsoft"
RETURN = "http://testserver/app/return"  # the phone's return address (universal link)


def browser(app) -> TestClient:
    """A client that keeps cookies and does NOT follow redirects, so each hop can be asserted."""
    return TestClient(app, follow_redirects=False)


def state_in(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]


def query_of(response) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}


def start_web(client, provider: str = GOOGLE, origin: dict | None = ORIGIN) -> str:
    """The same-origin POST that sets the nonce cookie; returns the state inside the consent URL."""
    reply = client.post(f"/auth/signin/{provider}/start", json={"redirect_to": AUTH_PAGE, "mode": "web"},
                        headers=origin or {})
    assert reply.status_code == 200, reply.text
    return state_in(reply.json()["url"])


def consent(client, state: str, identity: str, *, action: str = "allow", shown: tuple[str, ...] = (),
            ticked: tuple[str, ...] = ()):
    """Open the fake consent page, pick an identity, press a button. Returns the app's callback response."""
    page = client.get("/connections/fake/consent", params={"state": state})
    assert page.status_code == 200 and "id=sdk-consent-allow" in page.text and "id=sdk-consent-deny" in page.text
    params = {"state": state, "identity": identity, "action": action, "shown": ",".join(shown), "set": list(ticked)}
    pick = client.get("/connections/fake/consent/submit", params=params)
    assert pick.status_code == 302
    return client.get(pick.headers["location"])


def sign_in(client, email: str = "demo@example.com", provider: str = GOOGLE):
    return consent(client, start_web(client, provider), email)


def rows(app, model, **where):
    with session_scope(app.state.session_factory) as session:
        return session.query(model).filter_by(**where).all()


def connect(client, set_id: str, identity: str, *, action: str = "allow", ticked: tuple[str, ...] | None = None,
            provider: str = GOOGLE):
    """The role ask: start (XHR, session cookie) -> /go (sets the nonce) -> consent -> callback."""
    started = client.get(f"/connections/{provider}/start", params={"set": set_id, "redirect_to": CONNECTIONS_PAGE})
    assert started.status_code == 200, started.text
    go = client.get(started.json()["url"])
    assert go.status_code == 302
    state = state_in(go.headers["location"])
    return go, consent(client, state, identity, action=action, shown=(set_id,),
                       ticked=(set_id,) if ticked is None else ticked)
