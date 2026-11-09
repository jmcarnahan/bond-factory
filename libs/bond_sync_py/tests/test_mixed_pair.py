"""The lib proves the mixed request/response fixture pair itself, with a minimal host and a notes table."""

import sqlalchemy as sa
from conftest import Base, load_fixture
from sqlalchemy.orm import Mapped, mapped_column

from bond_sync_py import Ctx, Host, Rejected, Route, Skipped, UploadRequest, upload, written_by


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(sa.String)
    title: Mapped[str] = mapped_column(sa.String(255))
    body: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    deleted: Mapped[bool] = mapped_column(sa.Boolean, default=False)


def _notes(session, ctx, op, data):
    if op.op == "put":
        if not str(data.get("title", "")).strip():
            raise Rejected("title_required")
        session.add(Note(id=op.id, owner_user_id=ctx.user, title=data["title"], body=data.get("body")))
        session.flush()
        return
    note = session.get(Note, op.id)
    if note is None or note.owner_user_id != ctx.user or note.deleted:
        if op.op == "delete":
            raise Skipped()
        raise Rejected("Not found", code="not_found")
    if op.op == "delete":
        note.deleted = True
    else:
        note.title = data.get("title", note.title)


def notes_host() -> Host:
    return Host(
        routes={("notes", None): Route(frozenset({"put", "patch", "delete"}), _notes, ("title", "body"))},
        tables={"notes": Note.__table__},
        single_action=frozenset({"notes"}),
        already_written=lambda session, user, op: written_by(session, Note, "owner_user_id", user, op.id),
    )


def test_mixed_request_yields_the_mixed_response(factory):
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        session.add(Note(id="note-taken", owner_user_id="someone-else", title="theirs"))
        session.commit()
    body = UploadRequest.model_validate(load_fixture("upload_request_mixed.json"))
    out = upload(factory, notes_host(), Ctx(user="user-1"), body).wire()
    expected = load_fixture("upload_response_mixed.json")
    assert out["results"] == expected["results"]
    assert out["server_now"].endswith("Z") and len(out["server_now"]) == len(expected["server_now"])


def test_ok_request_is_all_ok(factory):
    body = UploadRequest.model_validate(load_fixture("upload_request_ok.json"))
    out = upload(factory, notes_host(), Ctx(user="user-1"), body).wire()
    assert [r["status"] for r in out["results"]] == ["ok"] * 4
