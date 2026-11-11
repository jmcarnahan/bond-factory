"""The reference app's own `Directory.apply_profile`, through the REAL app in fake mode (the fake provider names every
identity by the local part of its e-mail): an empty or blank name is filled, a set name is kept."""

import pytest
from bond_auth_py import decode_claims
from signin_util import ACCESS, browser, sign_in

from sdk_example.db import session_scope
from sdk_example.models.auth import User


def seed(app, email: str, name: str) -> None:
    with session_scope(app.state.session_factory) as session:
        session.add(User(id=f"u-{email.split('@')[0]}", email=email, name=name, capabilities=[]))


def signed_in_name(app, email: str) -> tuple[str, str]:
    """(access token name claim, `GET /auth/me` name) after a web sign-in as `email`."""
    client = browser(app)
    assert sign_in(client, email).status_code == 302
    claim = decode_claims(client.cookies.get(ACCESS), app.state.auth_settings).name
    return claim, client.get("/auth/me").json()["user"]["name"]


@pytest.mark.parametrize("stored", ["", "   "])
def test_an_empty_or_blank_name_is_filled_before_the_first_token(app, stored):
    seed(app, "dora.example@example.com", stored)
    assert signed_in_name(app, "dora.example@example.com") == ("dora.example", "dora.example")


def test_an_existing_name_is_kept(app):
    seed(app, "kept.example@example.com", "Kept Name")
    assert signed_in_name(app, "kept.example@example.com") == ("Kept Name", "Kept Name")
