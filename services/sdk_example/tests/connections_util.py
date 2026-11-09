"""Helpers shared by the connection route tests."""

from urllib.parse import parse_qs, urlsplit

from sdk_example.models.auth import DEMO_USER_ID
from sdk_example.models.connections import OAuthConnection

APP = "http://localhost:8078/connections"
NONCE = "sdk_example_oauth_nonce"


def headers(client, user_id=DEMO_USER_ID):
    """Sign in as a demo user (also leaves the session cookie in the client's jar) and return bearer headers."""
    web = {"Origin": "http://localhost:8078"}  # the web app: on the allowlist and in CORS
    token = client.post("/auth/demo", json={"user_id": user_id}, headers=web).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def start(client, h, provider="fake-google", redirect_to=APP):
    """The authenticated XHR step: returns the /go URL the browser is sent to."""
    return client.get(f"/connections/{provider}/start", params={"redirect_to": redirect_to}, headers=h).json()["url"]


def state_of(url):
    return parse_qs(urlsplit(url).query)["state"][0]


def begin(client, h, provider="fake-google", redirect_to=APP):
    """start -> /go (sets the nonce cookie, 302 to the consent page). Returns the state."""
    go = client.get(start(client, h, provider, redirect_to), headers=h, follow_redirects=False)
    assert go.status_code == 302
    return state_of(go.headers["location"])


def connect(client, h, provider="fake-google", redirect_to=APP):
    """start -> go -> consent page (it has an Allow button) -> callback with the plain `mock` code. Returns the final (redirect) response."""
    state = begin(client, h, provider, redirect_to)
    page = client.get("/connections/fake/consent", params={"state": state})
    assert page.status_code == 200 and "id=sdk-consent-allow" in page.text
    return client.get(f"/connections/{provider}/callback", params={"state": state, "code": "mock"}, headers=h,
                      follow_redirects=False)


def statuses(client, h):
    return {row["provider"]: row for row in client.get("/connections", headers=h).json()["connections"]}


def live_rows(app):
    with app.state.session_factory() as session:
        return session.query(OAuthConnection).filter_by(revoked_at=None).count()
