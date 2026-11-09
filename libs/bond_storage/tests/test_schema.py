"""The ``download_grants`` shape, written out literally (PLAN section 3.3.8). Change it only with the contract."""

import sqlalchemy as sa
from conftest import Grant

# name -> (type class, nullable, unique)
EXPECTED = {
    "id": (sa.String, False, None),
    "token_hash": (sa.String, False, True),
    "document_id": (sa.String, False, None),
    "purpose": (sa.String, False, None),
    "owner_type": (sa.String, True, None),
    "owner_id": (sa.String, True, None),
    "expires_at": (sa.DateTime, False, None),
    "max_downloads": (sa.Integer, True, None),
    "download_count": (sa.Integer, False, None),
    "revoked_at": (sa.DateTime, True, None),
    "last_downloaded_at": (sa.DateTime, True, None),
    "last_ip": (sa.String, True, None),
    "created_by": (sa.String, True, None),
    "created_at": (sa.DateTime, False, None),
    "updated_at": (sa.DateTime, False, None),
}


def test_table_name_and_columns_match_the_contract():
    table = Grant.__table__
    assert table.name == "download_grants"
    assert set(table.columns.keys()) == set(EXPECTED)
    for name, (type_class, nullable, unique) in EXPECTED.items():
        column = table.columns[name]
        assert type(column.type) is type_class, name
        assert column.nullable is nullable, name
        assert bool(column.unique) is bool(unique), name
    assert [c.name for c in table.primary_key.columns] == ["id"]


def test_defaults_and_indexes():
    table = Grant.__table__
    assert table.columns["purpose"].default.arg == "share"
    assert table.columns["download_count"].default.arg == 0
    assert table.columns["max_downloads"].default is None
    indexed = {tuple(c.name for c in index.columns) for index in table.indexes}
    assert indexed == {("document_id",), ("owner_id",)}


def test_the_app_can_constrain_document_id():
    foreign = list(Grant.__table__.foreign_key_constraints)
    assert [(fk.column_keys, fk.elements[0].target_fullname, fk.ondelete) for fk in foreign] == [
        (["document_id"], "documents.id", "CASCADE")]
