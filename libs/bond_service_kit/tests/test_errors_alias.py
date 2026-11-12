from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from bond_service_kit import error_body, install_error_handlers


def test_default_unchanged_without_aliases():
    assert error_body(409, {"error_code": "stale", "x": 1}) == {"error_code": "stale", "x": 1, "code": "conflict", "message": "conflict"}


def test_alias_fills_code_and_is_kept():
    body = error_body(409, {"error_code": "stale_copy", "x": 1}, code_aliases=("error_code",))
    assert body == {"error_code": "stale_copy", "x": 1, "code": "stale_copy", "message": "stale copy"}


def test_code_wins_over_alias_and_first_alias_wins():
    assert error_body(409, {"code": "a", "error_code": "b"}, code_aliases=("error_code",))["code"] == "a"
    assert error_body(409, {"err": "x", "error_code": "y"}, code_aliases=("missing", "error_code", "err"))["code"] == "y"
    assert error_body(409, {"error_code": ""}, code_aliases=("error_code",))["code"] == "conflict"


def test_installed_handler_uses_aliases():
    def app(**kw):
        a = FastAPI()
        install_error_handlers(a, **kw)

        @a.get("/x")
        def x():
            raise HTTPException(409, {"error_code": "stale_copy", "message": "Old"})

        return TestClient(a)

    assert app(code_aliases=("error_code",)).get("/x").json()["detail"] == {
        "error_code": "stale_copy", "message": "Old", "code": "stale_copy"}
    assert app().get("/x").json()["detail"]["code"] == "conflict"
