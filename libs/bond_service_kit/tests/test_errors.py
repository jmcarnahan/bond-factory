import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from bond_service_kit import ApiError, RateLimited, error_body, install_error_handlers


@pytest.mark.parametrize("status,code", [
    (400, "bad_request"), (401, "unauthorized"), (403, "forbidden"), (404, "not_found"), (405, "method_not_allowed"),
    (409, "conflict"), (413, "too_large"), (415, "unsupported_media_type"), (422, "invalid"), (429, "rate_limited"),
    (501, "not_implemented"), (502, "bad_gateway"), (503, "unavailable"), (418, "error"),
])
def test_status_fallback_codes(status, code):
    assert error_body(status, "Not found!") == {"code": code, "message": "Not found!"}


def test_api_error_options_are_keyword_only():
    with pytest.raises(TypeError):
        ApiError("c", "m", "h")  # type: ignore[misc]
    assert ApiError("c", "m", hint="h").status == 400


def test_capitalised_string_is_a_message_not_a_code():
    assert error_body(403, "Forbidden") == {"code": "forbidden", "message": "Forbidden"}
    assert error_body(404, "NotFound") == {"code": "not_found", "message": "NotFound"}


def test_snake_string_becomes_code():
    assert error_body(401, "invalid_token") == {"code": "invalid_token", "message": "invalid token"}


def test_dict_keeps_fields_and_gains_missing():
    assert error_body(409, {"hint": "retry", "x": 1}) == {
        "hint": "retry", "x": 1, "code": "conflict", "message": "conflict"}
    assert error_body(409, {"code": "stale_copy", "message": "Old"}) == {"code": "stale_copy", "message": "Old"}
    assert error_body(400, {"code": "a_b"})["message"] == "a b"


class Body(BaseModel):
    qty: int


def make_app(legacy=False):
    app = FastAPI()
    install_error_handlers(app, legacy_detail_string=legacy)

    @app.get("/plain")
    def plain():
        raise HTTPException(404, "Thing not here")

    @app.get("/code")
    def code():
        raise HTTPException(401, "invalid_token", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/dict")
    def as_dict():
        raise HTTPException(409, {"code": "stale", "extra": 1})

    @app.get("/api")
    def api():
        raise ApiError("too_hot", "It is hot", status=422, hint="Cool it", extra={"temp": 99})

    @app.get("/limited")
    def limited():
        raise RateLimited("5/minute")

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals")

    @app.post("/body")
    def body(b: Body):
        return b

    return app


def client(legacy=False):
    return TestClient(make_app(legacy), raise_server_exceptions=False)


def test_string_detail():
    r = client().get("/plain")
    assert r.status_code == 404
    assert r.json() == {"detail": {"code": "not_found", "message": "Thing not here"}}


def test_code_string_detail_keeps_headers():
    r = client().get("/code")
    assert r.json()["detail"] == {"code": "invalid_token", "message": "invalid token"}
    assert r.headers["www-authenticate"] == "Bearer"


def test_dict_detail():
    assert client().get("/dict").json()["detail"] == {"code": "stale", "extra": 1, "message": "stale"}


def test_unknown_path_and_bad_method():
    c = client()
    assert c.get("/nope").json()["detail"]["code"] == "not_found"
    assert c.post("/plain").json()["detail"]["code"] == "method_not_allowed"


def test_api_error():
    r = client().get("/api")
    assert r.status_code == 422
    assert r.json()["detail"] == {"temp": 99, "code": "too_hot", "message": "It is hot", "hint": "Cool it"}


def test_validation_never_echoes_input():
    r = client().post("/body", json={"qty": "SECRET-VALUE"})
    detail = r.json()["detail"]
    assert r.status_code == 422 and detail["code"] == "validation_error"
    assert detail["message"].startswith("qty: ")
    assert detail["errors"][0]["loc"] == ["body", "qty"]
    assert set(detail["errors"][0]) == {"loc", "msg", "type"}
    assert "SECRET-VALUE" not in r.text


def test_rate_limited():
    r = client().get("/limited")
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    assert r.json()["detail"]["code"] == "rate_limited"
    assert "5/minute" in r.json()["detail"]["message"]


def test_unhandled_is_internal_error_without_leaking():
    r = client().get("/boom")
    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "internal_error"
    assert "secret" not in r.text


def test_legacy_flag_keeps_string_details():
    c = client(legacy=True)
    assert c.get("/plain").json() == {"detail": "Thing not here"}
    assert c.get("/code").json() == {"detail": "invalid_token"}
    assert c.get("/boom").json() == {"detail": "Internal server error"}
    # dict details and ApiError stay in the object form
    assert c.get("/dict").json()["detail"]["code"] == "stale"
    assert c.get("/api").json()["detail"]["code"] == "too_hot"
