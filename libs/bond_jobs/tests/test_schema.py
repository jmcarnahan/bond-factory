"""Pins the ``background_jobs`` table: apps migrate it by hand, so a silent change here is a breaking change."""

from conftest import JobRecord
from sqlalchemy import JSON, DateTime, Integer, String, Text

# name -> (type class, nullable, unique, scalar default or None)
EXPECTED = {
    "id": (String, False, False, None),  # primary key, uuid string default (callable)
    "job_type": (String, False, False, None),
    "payload": (JSON, False, False, None),  # default: empty dict (callable)
    "run_at": (DateTime, False, False, None),  # default: now (server function)
    "status": (String, False, False, "pending"),
    "attempts": (Integer, False, False, 0),
    "max_attempts": (Integer, False, False, 5),
    "locked_at": (DateTime, True, False, None),
    "locked_by": (String, True, False, None),
    "last_error": (Text, True, False, None),
    "idempotency_key": (String, True, True, None),
    "created_at": (DateTime, True, False, None),
    "updated_at": (DateTime, True, False, None),
    "company_id": (String, True, False, None),  # TenantJobsMixin only
}


def test_table_name_and_columns():
    table = JobRecord.__table__
    assert table.name == "background_jobs"
    assert set(table.c.keys()) == set(EXPECTED)
    for name, (type_class, nullable, unique, default) in EXPECTED.items():
        column = table.c[name]
        assert type(column.type) is type_class, name
        assert column.nullable is nullable, name
        assert bool(column.unique) is unique, name
        if default is not None:
            assert column.default.arg == default, name


def test_primary_key_and_defaults_that_are_functions():
    table = JobRecord.__table__
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert table.c.id.default.is_callable and table.c.payload.default.is_callable
    assert table.c.run_at.default is not None and table.c.created_at.default is not None
    assert table.c.updated_at.onupdate is not None


def test_claim_index_is_status_then_run_at():
    indexes = {i.name: [c.name for c in i.columns] for i in JobRecord.__table__.indexes}
    assert indexes["ix_background_jobs_claim"] == ["status", "run_at"]


def test_plain_mixin_has_no_company_id():
    from sqlalchemy.orm import DeclarativeBase

    from bond_jobs import JobsMixin

    class Other(DeclarativeBase):
        pass

    class Plain(JobsMixin, Other):
        pass

    assert "company_id" not in Plain.__table__.c
    assert set(Plain.__table__.c.keys()) == set(EXPECTED) - {"company_id"}
