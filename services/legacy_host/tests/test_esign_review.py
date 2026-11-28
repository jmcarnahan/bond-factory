"""E-signing review fixes on the host: the form guards, the page, the adapter's status words, the adopted schema."""

import bond_esign as be
import pytest
from esign_util import PDF, esign_app, estimate, providers, signer_of
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.dialects import sqlite

from legacy_host.db import Base
from legacy_host.esign_models import TABLES, EsignEnvelope
from legacy_host.esign_seam import EsignError, send_for_signature, void_envelope

FORM = {"content-type": "application/x-www-form-urlencoded"}


def link_for(app, session, est="est-7"):
    both = providers(app, session)
    now = app.state.clock.utcnow_naive()
    row = send_for_signature(session, both, "native", estimate(session, est), pdf=PDF, file_name="Estimate",
                             signer_name="Pat Customer", signer_email="pat@example.com", client_user_id="cu",
                             now=now, envelope_class=EsignEnvelope)
    return both, row, f"/estimates/{est}/sign?sign=1&t=" + _token(both["native"], row)


def _token(native, row):
    from urllib.parse import parse_qs, urlparse

    url = native.recipient_view_url(envelope_id=row.envelope_id, signer_name="Pat Customer",
                                    signer_email="pat@example.com", client_user_id="cu", return_url="/x")
    native.session.commit()
    return parse_qs(urlparse(url).query)["t"][0]


def test_the_post_guards(tmp_path):
    app = esign_app(tmp_path)
    client = TestClient(app)
    with app.state.session_factory() as session:
        _, _, link = link_for(app, session)
    assert client.post(link, json={"typed_name": "x"}).status_code == 415
    assert client.post(link, content=b"x=" + b"a" * 500_000, headers=FORM).status_code == 413
    assert client.post(link, content=b"x=1", headers={**FORM, "content-length": "900000"}).status_code in (400, 413)
    assert client.post(link, content=b"consent_version=\xff\xfe&mode=typed", headers=FORM).status_code == 200
    bad = client.post(link, content=b"consent_version=x&consent_accepted=1&mode=drawn&drawn_png=data:image/png;base64,@@",
                      headers=FORM)
    assert bad.status_code == 200 and "<form" in bad.text  # re-rendered, not a 500
    many = b"&".join(b"k%d=1" % n for n in range(40))
    assert client.post(link, content=many, headers=FORM).status_code == 400


def test_the_error_query_is_never_echoed_and_the_form_posts_to_a_clean_url(tmp_path):
    app = esign_app(tmp_path)
    client = TestClient(app)
    with app.state.session_factory() as session:
        _, _, link = link_for(app, session)
    page = client.get(link + "&error=%3Cb%3Eowned%3C/b%3E&evil=1")
    assert page.status_code == 200 and "owned" not in page.text and "evil" not in page.text
    assert page.headers["cache-control"] == "no-store"
    assert f'action="{link.replace("&", "&amp;")}"' in page.text or f'action="{link}"' in page.text
    known = client.get(link + "&error=consent_required")
    assert "agree" in known.text.lower()


def test_fetch_is_retryable_only_while_open(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        native = both["native"]
        rows = {}
        for est in ("est-1", "est-2", "est-3", "est-4"):
            rows[est] = send_for_signature(session, both, "native", estimate(session, est), pdf=PDF, file_name=est,
                                           signer_name="Pat Customer", signer_email="pat@example.com",
                                           client_user_id="cu", now=now, envelope_class=EsignEnvelope)
        with pytest.raises(EsignError) as still_open:
            native.fetch_signed_pdf(rows["est-1"].envelope_id)
        assert still_open.value.retryable is True
        be.decline(session, TABLES, signer_of(session, rows["est-2"].envelope_id), reason=None, ctx=None, now=now)
        void_envelope(session, both, rows["est-3"], "changed mind")
        session.get(TABLES.request, rows["est-4"].envelope_id).status = "expired"
        for est, word in (("est-2", "declined"), ("est-3", "voided"), ("est-4", "expired")):
            with pytest.raises(EsignError) as never:
                native.fetch_signed_pdf(rows[est].envelope_id)
            assert never.value.retryable is False and never.value.code == word and not isinstance(never.value, be.EsignError)


def test_an_unknown_provider_name_is_the_hosts_error(tmp_path):
    app = esign_app(tmp_path)
    with app.state.session_factory() as session:
        both = providers(app, session)
        with pytest.raises(EsignError) as caught:
            send_for_signature(session, both, "nope", estimate(session), pdf=PDF, file_name="x", signer_name="P",
                               signer_email="p@example.com", client_user_id="c",
                               now=app.state.clock.utcnow_naive(), envelope_class=EsignEnvelope)
        assert caught.value.code == "UNKNOWN_PROVIDER"


def affinity(type_sql: str) -> str:
    """SQLite's column affinity rules (section 3.1 of its datatype notes)."""
    t = type_sql.upper()
    if "INT" in t:
        return "INTEGER"
    if any(w in t for w in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in t or not t:
        return "BLOB"
    if any(w in t for w in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def shape_of_database(engine, table):
    insp = inspect(engine)
    cols = {c["name"]: (affinity(str(c["type"])), bool(c["nullable"])) for c in insp.get_columns(table)}
    pk = tuple(insp.get_pk_constraint(table)["constrained_columns"])
    # PRAGMAs, not reflection: inspect() misses an inline UNIQUE and an inline ON DELETE on this SQLite
    with engine.connect() as c:
        uniques, indexes = set(), set()
        for _, name, unique, origin, _ in c.execute(text(f"PRAGMA index_list({table})")).all():
            members = tuple(r[2] for r in c.execute(text(f"PRAGMA index_info({name})")).all())
            if origin == "u":
                uniques.add(members)
            elif origin == "c":
                (uniques if unique else indexes).add(members if unique else (name, members))
        fks = {}
        for row in c.execute(text(f"PRAGMA foreign_key_list({table})")).all():
            fks.setdefault(row[0], []).append(row)
    fks = {(tuple(r[3] for r in rows), rows[0][2], tuple(r[4] for r in rows), rows[0][6].replace("NO ACTION", ""))
           for rows in fks.values()}
    return cols, pk, uniques, indexes, fks


def shape_of_metadata(table):
    dialect = sqlite.dialect()
    cols = {c.name: (affinity(c.type.compile(dialect=dialect)), bool(c.nullable) and not c.primary_key)
            for c in table.columns}
    pk = tuple(c.name for c in table.primary_key.columns)
    from sqlalchemy import UniqueConstraint

    uniques = {tuple(c.name for c in k.columns) for k in table.constraints if isinstance(k, UniqueConstraint)}
    uniques |= {(c.name,) for c in table.columns if c.unique}
    uniques |= {tuple(c.name for c in i.columns) for i in table.indexes if i.unique}
    indexes = {(i.name, tuple(c.name for c in i.columns)) for i in table.indexes if not i.unique}
    fks = {((f.parent.name,), f.column.table.name, (f.column.name,), (f.ondelete or "").upper())
           for f in table.foreign_keys}
    return cols, pk, uniques, indexes, fks


@pytest.mark.parametrize("table", ["esign_requests", "esign_signers", "esign_events"])
def test_the_adopt_ddl_has_the_mixin_schema_not_just_its_column_names(tmp_path, table):
    app = esign_app(tmp_path)
    made = shape_of_database(app.state.engine, table)
    wanted = shape_of_metadata(Base.metadata.tables[table])
    for label, got, want in zip(("columns", "primary key", "unique", "indexes", "foreign keys"), made, wanted):
        assert got == want, f"{table} {label}"
    if table == "esign_signers":
        assert ("token_sha256",) in made[2] and ("request_id", "position") in made[2]
        assert any(cols == ("request_id",) for _, cols in made[3])
        assert (("request_id",), "esign_requests", ("id",), "CASCADE") in made[4]
    if table == "esign_events":
        assert ("request_id", "seq") in made[2]
        assert (("request_id",), "esign_requests", ("id",), "CASCADE") in made[4]
    if table == "esign_requests":
        assert any(name == "ix_esign_requests_subject" for name, _ in made[3])
