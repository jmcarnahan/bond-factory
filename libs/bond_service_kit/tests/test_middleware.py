import logging

import pytest
import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bond_service_kit import (
    LoggingCORSMiddleware,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
    UploadLimit,
    db_session_middleware,
    make_session_factory,
)


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String)


def test_security_headers_and_stricter_referrer_kept():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/a")
    def a():
        return {}

    from fastapi.responses import JSONResponse

    @app.get("/b")
    def b():
        return JSONResponse({}, headers={"Referrer-Policy": "no-referrer"})

    c = TestClient(app)
    h = c.get("/a").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert h["strict-transport-security"].startswith("max-age=31536000")
    assert "camera=(self)" in h["permissions-policy"]
    assert c.get("/b").headers["referrer-policy"] == "no-referrer"


def session_app(url="sqlite://"):
    engine, factory = make_session_factory(url)
    app = FastAPI()
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(db_session_middleware(factory))
    return app, engine, factory


def test_session_on_request_state_is_rolled_back_and_closed():
    app, engine, factory = session_app()
    Base.metadata.create_all(engine)
    seen = []

    @app.post("/pending")
    def pending(request: Request):
        db = request.state.db
        seen.append(db)
        db.add(Item(name="uncommitted"))
        db.flush()
        return {}

    @app.post("/boom")
    def boom(request: Request):
        request.state.db.add(Item(name="lost"))
        request.state.db.flush()
        raise RuntimeError("x")

    @app.post("/commit")
    def commit(request: Request):
        request.state.db.add(Item(name="kept"))
        request.state.db.commit()
        return {}

    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/pending").status_code == 200
    assert c.post("/boom").status_code == 500
    assert c.post("/commit").status_code == 200
    with factory() as s:
        assert [i.name for i in s.query(Item)] == ["kept"]
    assert not seen[0].in_transaction()


def test_db_unreachable_is_503_with_retry_after_without_the_catch_all():
    _, factory = make_session_factory("sqlite:////nonexistent-dir-for-bond-tests/x.db")
    app = FastAPI()
    app.add_middleware(db_session_middleware(factory))

    @app.get("/q")
    def q(request: Request):
        request.state.db.execute(sa.text("select 1"))
        return {}

    r = TestClient(app, raise_server_exceptions=False).get("/q")
    assert r.status_code == 503 and r.headers["retry-after"] == "5"


def test_db_unreachable_is_503_with_retry_after():
    app, _, _ = session_app("sqlite:////nonexistent-dir-for-bond-tests/x.db")

    @app.get("/q")
    def q(request: Request):
        request.state.db.execute(sa.text("select 1"))
        return {}

    r = TestClient(app, raise_server_exceptions=False).get("/q")
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert r.json()["detail"]["code"] == "db_unavailable"


class _Orig(Exception):
    def __init__(self, text="x", pgcode=None):
        super().__init__(text)
        self.pgcode = pgcode


def _db_error(text="x", *, pgcode=None, invalidated=False):
    return OperationalError("select 1", {}, _Orig(text, pgcode), connection_invalidated=invalidated)


def test_only_connection_class_errors_are_unavailable():
    from bond_service_kit.errors import is_db_unavailable

    for yes in (_db_error(invalidated=True), _db_error(pgcode="08006"), _db_error(pgcode="57P01"),
                _db_error(pgcode="53300"), _db_error("unable to open database file"),
                _db_error("database is locked"), PoolTimeoutError("pool")):
        assert is_db_unavailable(yes), yes
    for no in (_db_error("no such table: items"), _db_error(pgcode="42P01"), _db_error(pgcode="23505"),
               RuntimeError("x")):
        assert not is_db_unavailable(no), no


def _raising_app(exc, *, with_catch_all):
    _, factory = make_session_factory("sqlite://")
    app = FastAPI()
    if with_catch_all:
        app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(db_session_middleware(factory))

    @app.get("/x")
    def x():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_programming_errors_stay_500_and_connection_errors_are_503():
    for with_catch_all in (True, False):
        missing = _raising_app(_db_error("no such table: items"), with_catch_all=with_catch_all).get("/x")
        assert missing.status_code == 500 and "retry-after" not in missing.headers
        if with_catch_all:
            assert missing.json()["detail"]["code"] == "internal_error"
        lost = _raising_app(_db_error(invalidated=True), with_catch_all=with_catch_all).get("/x")
        assert lost.status_code == 503 and lost.headers["retry-after"] == "5"
        assert lost.json()["detail"]["code"] == "db_unavailable"


def test_real_sqlite_missing_table_is_a_500():
    app, _, _ = session_app()

    @app.get("/t")
    def t(request: Request):
        request.state.db.execute(sa.text("select * from no_such_table"))

    assert TestClient(app, raise_server_exceptions=False).get("/t").status_code == 500


def test_cors_refuses_wildcard_with_credentials():
    with pytest.raises(ValueError, match="allow_credentials"):
        LoggingCORSMiddleware(FastAPI(), allow_origins=["*"])
    with pytest.raises(ValueError):
        LoggingCORSMiddleware(FastAPI(), allow_origins="*", allow_credentials=True)
    LoggingCORSMiddleware(FastAPI(), allow_origins=["*"], allow_credentials=False)  # public API: fine
    LoggingCORSMiddleware(FastAPI(), allow_origins=["https://a.test"])


def test_upload_limit_by_content_length_and_chunked():
    app = FastAPI()
    app.add_middleware(UploadLimit, max_bytes=10, paths=("/up",))

    @app.post("/up")
    async def up(request: Request):
        return {"n": len(await request.body())}

    @app.post("/other")
    async def other(request: Request):
        return {"n": len(await request.body())}

    c = TestClient(app)
    assert c.post("/up", content=b"x" * 10).json() == {"n": 10}
    r = c.post("/up", content=b"x" * 11)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    assert c.post("/other", content=b"x" * 500).json() == {"n": 500}

    def chunks(total):
        for _ in range(total):
            yield b"x"

    assert c.post("/up", content=chunks(10)).json() == {"n": 10}  # chunked, within the cap, replayed
    assert c.post("/up", content=chunks(11)).status_code == 413


def test_cors_logs_a_rejected_origin_once(caplog):
    app = FastAPI()
    app.add_middleware(LoggingCORSMiddleware, allow_origins=["http://ok.test"])

    @app.get("/")
    def root():
        return {}

    c = TestClient(app)
    headers = {"Access-Control-Request-Method": "GET"}
    with caplog.at_level(logging.WARNING, logger="bond_service_kit.middleware"):
        for _ in range(2):
            r = c.options("/", headers={**headers, "Origin": "http://evil.test"})
            assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
    lines = [x.getMessage() for x in caplog.records if "http://evil.test" in x.getMessage()]
    assert len(lines) == 1
    ok = c.options("/", headers={**headers, "Origin": "http://ok.test"})
    assert ok.headers["access-control-allow-origin"] == "http://ok.test"
