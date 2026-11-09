import threading
import time

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bond_service_kit import (
    HealthSlot,
    health_router,
    make_session_factory,
    mount_uploads,
    mount_web,
    schema_contract,
    session_scope,
)


class Base(DeclarativeBase):
    pass


class Widget(Base):
    __tablename__ = "widgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(20))
    note: Mapped[str | None] = mapped_column(sa.String, nullable=True)


def test_session_factory_and_scope_commit_and_rollback():
    engine, factory = make_session_factory("sqlite://")
    Base.metadata.create_all(engine)
    with session_scope(factory) as s:
        s.add(Widget(name="a"))
    with pytest.raises(RuntimeError), session_scope(factory) as s:
        s.add(Widget(name="b"))
        s.flush()
        raise RuntimeError
    with session_scope(factory) as s:
        assert [w.name for w in s.query(Widget)] == ["a"]
    with engine.connect() as c:
        assert c.execute(sa.text("PRAGMA foreign_keys")).scalar() == 1


def test_schema_contract_output_shape():
    contract = schema_contract(Base.metadata)
    assert contract.tables == {"widgets": {"id": False, "name": False, "note": True}}
    assert schema_contract(Base.metadata, tables=["nope"]).tables == {}


def test_schema_contract_passes_and_extra_columns_ok():
    engine, _ = make_session_factory("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(sa.text("ALTER TABLE widgets ADD COLUMN extra TEXT"))
    contract = schema_contract(Base.metadata)
    contract.assert_matches(engine)
    with pytest.raises(AssertionError, match="extra is not in the contract"):
        contract.assert_matches(engine, strict=True)


def test_schema_contract_fails_listing_every_difference():
    engine, _ = make_session_factory("sqlite://")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE widgets (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(20))"))
    contract = schema_contract(Base.metadata)
    with pytest.raises(AssertionError) as info:
        contract.assert_matches(engine)
    text = str(info.value)
    assert "widgets.name should be NOT NULL" in text and "widgets.note is missing" in text
    missing = schema_contract(Base.metadata, tables=["widgets"])
    assert missing.tables["widgets"]["note"] is True
    other = sa.MetaData()
    sa.Table("gadgets", other, sa.Column("id", sa.Integer, primary_key=True))
    with pytest.raises(AssertionError, match="gadgets' is missing"):
        schema_contract(other).assert_matches(engine)


def health_client(checks, **kw):
    app = FastAPI()
    app.include_router(health_router(checks, **kw))
    return TestClient(app)


def test_health_ok():
    r = health_client({"db": lambda: True, "cfg": lambda: "ok"}).get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "checks": {"db": "ok", "cfg": "ok"}}


def test_health_degraded_for_false_message_and_raise():
    def boom():
        raise RuntimeError("secret")

    r = health_client({"a": lambda: False, "b": lambda: "behind", "c": boom, "d": lambda: True}).get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "checks": {"a": "fail", "b": "behind", "c": "error", "d": "ok"}}
    assert "secret" not in r.text
    assert health_client({"a": lambda: False}, degraded_status=200).get("/health").status_code == 200


def test_health_timeout_then_busy_and_slot_freed_by_thread():
    release = threading.Event()

    def slow():
        release.wait(5)
        return True

    slot = HealthSlot(1)
    c = health_client({"db": slow}, slot=slot, timeout=0.2)
    assert c.get("/health").json()["checks"] == {"db": "timeout"}
    assert c.get("/health").json()["checks"] == {"db": "busy"}  # the hung thread still holds the slot
    release.set()
    for _ in range(50):
        if c.get("/health").json()["status"] == "ok":
            break
        time.sleep(0.05)
    else:
        pytest.fail("slot was never freed")


def test_mount_web_spa_fallback_and_reserved(tmp_path):
    (tmp_path / "index.html").write_text("<h1>app</h1>")
    (tmp_path / "main.js").write_text("js()")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "secret.txt").write_text("s")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": 1}

    assert mount_web(app, tmp_path) is True
    c = TestClient(app)
    assert c.get("/").text == "<h1>app</h1>"
    assert c.get("/main.js").text == "js()"
    assert c.get("/customers/123").text == "<h1>app</h1>"
    assert c.get("/sub/").text == "<h1>app</h1>"  # no directory listing: the index, not a file list
    assert "secret.txt" not in c.get("/sub/").text
    assert c.get("/api/ping").json() == {"ok": 1}
    assert c.get("/api/missing").status_code == 404
    assert c.get("/uploads/x").status_code == 404
    assert c.post("/customers/1").status_code == 405


def test_mount_web_without_index_is_not_mounted(tmp_path):
    assert mount_web(FastAPI(), tmp_path) is False


def test_mount_uploads_refuses_private_and_downgrades_html(tmp_path):
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "doc.pdf").write_bytes(b"%PDF")
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "evil.html").write_text("<script>x</script>")
    app = FastAPI()
    assert mount_uploads(app, tmp_path) is True
    c = TestClient(app)
    assert c.get("/uploads/a.png").status_code == 200
    assert c.get("/uploads/private/doc.pdf").status_code == 404
    assert c.get("/uploads/Private/doc.pdf").status_code == 404
    assert c.get("/uploads/private/missing.pdf").status_code == 404  # same answer as a missing key
    r = c.get("/uploads/evil.html")
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment; filename=\"evil.html\"")
    custom = FastAPI()
    mount_uploads(custom, tmp_path / "private", private_prefix="nothing/")
    assert TestClient(custom).get("/uploads/doc.pdf").status_code == 200
