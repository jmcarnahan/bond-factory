import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_sync_py import Ctx, Host, Rejected, Resolved, Route, Skipped, UploadOp, written_by

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "sync"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(sa.String)
    title: Mapped[str] = mapped_column(sa.String(255))
    count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    flag: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    meta: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


def _put(session, ctx, op, data):
    if not data.get("title"):
        raise Rejected("title_required")
    if isinstance(data.get("meta"), (dict, list)):
        data = {**data, "meta": json.dumps(data["meta"])}
    session.add(Item(id=op.id, owner=ctx.user, **data))
    session.flush()
    if data.get("title") == "resolve":
        return Resolved("server-1")


def _patch(session, ctx, op, data):
    row = session.get(Item, op.id)
    if row is None:
        raise Rejected("Not found", code="not_found")
    for key, value in data.items():
        setattr(row, key, value)


def _delete(session, ctx, op, data):
    row = session.get(Item, op.id)
    if row is None:
        raise Skipped()
    session.delete(row)


def _boom(session, ctx, op, data):
    raise RuntimeError("unmapped bug")


def make_host(**overrides) -> Host:
    routes = {
        ("items", None): Route(frozenset({"put"}), _put, ("title", "count", "flag", "meta")),
        ("items", "edit"): Route(frozenset({"patch"}), _patch, ("title", "count", "flag", "meta")),
        ("items", "remove"): Route(frozenset({"delete"}), _delete),
        ("bugs", None): Route(frozenset({"put"}), _boom),
        ("single", None): Route(frozenset({"put"}), _put, ("title",)),
    }
    base = {
        "routes": routes,
        "tables": {"items": Item.__table__},
        "single_action": frozenset({"single"}),
        "rest_only": frozenset({"rest"}),
        "already_written": lambda session, user, op: written_by(session, Item, "owner", user, op.id),
        "client_bools": {"items": frozenset({"flag"})},
        "client_json": {"items": frozenset({"meta"})},
    }
    base.update(overrides)
    return Host(**base)


@pytest.fixture
def factory():
    engine = sa.create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def host():
    return make_host()


@pytest.fixture
def ctx():
    return Ctx(user="user-1")


def op(seq=0, kind="put", table="items", id_="i-1", action=None, **data) -> UploadOp:
    return UploadOp(seq=seq, op=kind, table=table, id=id_, action=action, data=data)
