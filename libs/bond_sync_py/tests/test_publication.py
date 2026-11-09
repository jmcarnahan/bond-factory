from unittest.mock import MagicMock

import pytest

from bond_sync_py import add_table, render_source_sql


class FakeOp:
    def __init__(self, dialect="postgresql", publication=True, listed=False, role=True):
        self.executed = []
        self.dialect, self.publication, self.listed, self.role = dialect, publication, listed, role

    def get_bind(self):
        bind = MagicMock()
        bind.dialect.name = self.dialect

        def execute(stmt, params=None):
            text = str(stmt)
            result = MagicMock()
            if "pg_publication_tables" in text:
                result.first.return_value = (1,) if self.listed else None
            elif "pg_publication" in text:
                result.first.return_value = (1,) if self.publication else None
            else:
                result.first.return_value = (1,) if self.role else None
            return result

        bind.execute.side_effect = execute
        return bind

    def execute(self, sql):
        self.executed.append(sql)


def test_add_table_runs_alter_and_grant():
    op = FakeOp()
    assert add_table(op, "notes") is True
    assert op.executed == ['ALTER PUBLICATION powersync ADD TABLE "notes"', 'GRANT SELECT ON "notes" TO powersync']


def test_add_table_uses_given_publication_and_role():
    op = FakeOp()
    add_table(op, "notes", publication="demo_pub", role="demo_role")
    assert op.executed[0] == 'ALTER PUBLICATION demo_pub ADD TABLE "notes"'
    assert op.executed[1].endswith("TO demo_role")


def test_add_table_skips_when_not_postgres_missing_publication_or_listed():
    assert add_table(FakeOp(dialect="sqlite"), "notes") is False
    assert add_table(FakeOp(publication=False), "notes") is False
    assert add_table(FakeOp(listed=True), "notes") is False


def test_add_table_without_role_skips_grant():
    op = FakeOp(role=False)
    add_table(op, "notes")
    assert len(op.executed) == 1


def test_add_table_rejects_bad_names():
    for name in ("notes; drop", 'a"b', "Notes", ""):
        with pytest.raises(ValueError):
            add_table(FakeOp(), name)
    with pytest.raises(ValueError):
        add_table(FakeOp(), "notes", publication="x y")


def test_source_sql_text():
    sql = render_source_sql(["notes", "tags"], publication="demo_pub", role="demo_role", app_name="demo")
    assert "CREATE PUBLICATION demo_pub FOR TABLE :synced_tables;" in sql
    assert "\\set synced_tables 'notes, tags'" in sql
    assert "GRANT SELECT ON :synced_tables TO demo_role;" in sql
    assert "Sync source setup for demo." in sql
    assert "ps_password" in sql and "max_slot_wal_keep_size = '2GB'" in sql
    assert render_source_sql(["notes"], generated_by="make sql") .startswith("-- GENERATED FILE. Do not edit by hand. Regenerate")


def test_source_sql_is_deterministic_and_generic():
    assert render_source_sql(["notes"]) == render_source_sql(["notes"])
    assert "app" in render_source_sql(["notes"]).splitlines()[3]


def test_source_sql_validates_names():
    for tables in ([], ["a", "a"], ["bad name"], ["x;drop"]):
        with pytest.raises(ValueError):
            render_source_sql(tables)
    with pytest.raises(ValueError):
        render_source_sql(["a"], publication="p'q")
    with pytest.raises(ValueError):
        render_source_sql(["a"], wal_keep="2GB'; --")
