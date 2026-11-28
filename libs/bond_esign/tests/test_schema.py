"""Pins the three tables: apps migrate them by hand, so a silent change here is a breaking change."""

from conftest import Event, Request, Signer
from sqlalchemy import JSON, Boolean, DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase

from bond_esign import EsignEventMixin, EsignRequestMixin, EsignSignerMixin

# name -> (type class, nullable, unique, scalar default or None)
REQUEST = {
    "id": (String, False, False, None),
    "status": (String, False, False, None),
    "title": (String, False, False, None),
    "subject_type": (String, True, False, None),
    "subject_id": (String, True, False, None),
    "document_sha256": (String, False, False, None),
    "document_bytes": (Integer, False, False, None),
    "page_count": (Integer, False, False, None),
    "consent_version": (String, False, False, None),
    "consent_language": (String, False, False, None),
    "consent_sha256": (String, False, False, None),
    "consent_text": (Text, False, False, None),
    "policy": (JSON, False, False, None),
    "expires_at": (DateTime, True, False, None),
    "signed_sha256": (String, True, False, None),
    "sealed": (Boolean, False, False, False),
    "timestamped": (Boolean, False, False, False),
    "completed_at": (DateTime, True, False, None),
    "voided_at": (DateTime, True, False, None),
    "declined_at": (DateTime, True, False, None),
    "void_reason": (Text, True, False, None),
    "meta": (JSON, False, False, None),  # default: empty dict (callable)
    "created_at": (DateTime, True, False, None),
    "updated_at": (DateTime, True, False, None),
    "company_id": (String, True, False, None),  # TenantEsignRequestMixin only
}
SIGNER = {
    "id": (String, False, False, None),
    "request_id": (String, False, False, None),
    "position": (Integer, False, False, None),
    "name": (String, False, False, None),
    "email": (String, True, False, None),
    "role": (String, False, False, None),
    "key": (String, True, False, None),
    "status": (String, False, False, None),
    "placement": (JSON, True, False, None),
    "date_placement": (JSON, True, False, None),
    "token_sha256": (String, True, True, None),
    "token_expires_at": (DateTime, True, False, None),
    "code_sha256": (String, True, False, None),
    "code_expires_at": (DateTime, True, False, None),
    "code_sent_at": (DateTime, True, False, None),
    "code_verified_at": (DateTime, True, False, None),
    "code_attempts": (Integer, False, False, 0),
    "method": (String, True, False, None),
    "witness": (String, True, False, None),
    "signature_kind": (String, True, False, None),
    "typed_name": (String, True, False, None),
    "signature_png": (LargeBinary, True, False, None),
    "signature_sha256": (String, True, False, None),
    "signed_at": (DateTime, True, False, None),
    "ip": (String, True, False, None),
    "user_agent": (Text, True, False, None),
    "decline_reason": (Text, True, False, None),
    "created_at": (DateTime, True, False, None),
    "updated_at": (DateTime, True, False, None),
}
EVENT = {
    "id": (String, False, False, None),
    "request_id": (String, False, False, None),
    "seq": (Integer, False, False, None),
    "signer_id": (String, True, False, None),
    "kind": (String, False, False, None),
    "at": (DateTime, False, False, None),
    "ip": (String, True, False, None),
    "user_agent": (Text, True, False, None),
    "actor": (String, True, False, None),
    "data": (JSON, False, False, None),  # default: empty dict (callable)
    "prev_hash": (String, False, False, None),
    "row_hash": (String, False, False, None),
}


def check_columns(table, expected):
    assert set(table.c.keys()) == set(expected)
    for name, (type_class, nullable, unique, default) in expected.items():
        column = table.c[name]
        assert type(column.type) is type_class, name
        assert column.nullable is nullable, name
        assert bool(column.unique) is unique, name
        if default is not None:
            assert column.default.arg == default, name


def unique_sets(table):
    from sqlalchemy import UniqueConstraint

    return {
        (c.name, tuple(col.name for col in c.columns))
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
    }


def test_request_table():
    table = Request.__table__
    assert table.name == "esign_requests"
    check_columns(table, REQUEST)
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert table.c.id.default.is_callable and table.c.meta.default.is_callable
    for name in ("document_sha256", "consent_sha256"):
        assert table.c[name].type.length == 64
    indexes = {i.name: [c.name for c in i.columns] for i in table.indexes}
    assert indexes["ix_esign_requests_subject"] == ["subject_type", "subject_id"]
    assert indexes["ix_esign_requests_company_id"] == ["company_id"]
    assert not table.c.company_id.foreign_keys


def test_signer_table():
    table = Signer.__table__
    assert table.name == "esign_signers"
    check_columns(table, SIGNER)
    assert table.c.token_sha256.type.length == 64 and table.c.code_sha256.type.length == 64
    fk = next(iter(table.c.request_id.foreign_keys))
    assert fk.target_fullname == "esign_requests.id" and fk.ondelete == "CASCADE"
    assert ("uq_esign_signers_request_position", ("request_id", "position")) in unique_sets(table)
    assert any(i.columns.keys() == ["request_id"] for i in table.indexes)


def test_event_table():
    table = Event.__table__
    assert table.name == "esign_events"
    check_columns(table, EVENT)
    assert table.c.prev_hash.type.length == 64 and table.c.row_hash.type.length == 64
    fk = next(iter(table.c.request_id.foreign_keys))
    assert fk.target_fullname == "esign_requests.id" and fk.ondelete == "CASCADE"
    assert ("uq_esign_events_request_seq", ("request_id", "seq")) in unique_sets(table)


def test_plain_request_mixin_has_no_company_id_and_a_second_base_works():
    class Other(DeclarativeBase):
        pass

    class R(EsignRequestMixin, Other):
        pass

    class S(EsignSignerMixin, Other):
        pass

    class E(EsignEventMixin, Other):
        pass

    assert "company_id" not in R.__table__.c
    assert set(R.__table__.c.keys()) == set(REQUEST) - {"company_id"}
    assert set(S.__table__.c.keys()) == set(SIGNER) and set(E.__table__.c.keys()) == set(EVENT)
    assert next(iter(S.__table__.c.request_id.foreign_keys)).column is R.__table__.c.id
    assert next(iter(E.__table__.c.request_id.foreign_keys)).column is R.__table__.c.id
    # the first base is untouched by the second declaration
    assert next(iter(Signer.__table__.c.request_id.foreign_keys)).column is Request.__table__.c.id
