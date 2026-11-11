"""Web sign-in with the optional ``apply_profile`` hook."""

import pytest

from bond_signin import ProfileHookError

from .bare_directory import BareDirectory
from .conftest import APP_ORIGIN, build, start_web, state_of

DONE = f"{APP_ORIGIN}/done"


def cookies_of(resp) -> dict[str, str]:
    return {c.split("=", 1)[0]: c for c in resp.headers.get_list("set-cookie")}


def signin_web(h, code):
    resp = h.client.get(f"/auth/signin/google/callback?state={state_of(start_web(h))}&code={code}")
    assert resp.status_code == 302 and resp.headers["location"] == f"{DONE}?signin=ok"
    assert "app_access_token" in cookies_of(resp)
    return resp


def test_web_first_token_carries_the_provider_name_for_an_empty_invitee(h):
    signin_web(h, "dora")
    assert h.sessions.issued[-1]["spec"].name == "Dora Example"
    assert h.directory.profile_calls == [("u-dora", "Dora Example", True, "google")]
    assert h.db.rollbacks == 0


def test_web_existing_name_is_unchanged(h):
    h.flow.identities["alice"] = {"name": "Alice Renamed"}
    signin_web(h, "alice")
    assert h.sessions.issued[-1]["spec"].name == "Alice"


def test_web_directory_without_the_hook_still_signs_in():
    h = build(directory=BareDirectory())
    signin_web(h, "dora")
    assert h.sessions.issued[-1]["spec"].name == ""  # the stored name: nothing wrote it
    signin_web(h, "alice")
    assert h.sessions.issued[-1]["spec"].name == "Alice"


def test_web_a_raising_hook_rolls_back_and_is_not_a_refusal(h):
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    h.directory.apply_profile = boom
    with pytest.raises(ProfileHookError):  # unhandled: the server answers 500 (the test client re-raises)
        h.client.get(f"/auth/signin/google/callback?state={state_of(start_web(h))}&code=dora")
    assert h.db.rollbacks == 1
    assert h.sessions.issued == [] and h.directory.refusals == []
