"""The example's schema matches what every lib expects, and the migration chain matches the models."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from bond_jobs import JobsMixin
from bond_oauth.models import ConnectionsMixin
from bond_service_kit import SchemaContract, schema_contract
from bond_storage import GrantsMixin
from bond_tasks_py import TasksMixin
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base

from alembic import command
from sdk_example.db import Base
from sdk_example.wiring import bootstrap_schema

SERVICE = Path(__file__).resolve().parents[1]


def lib_contract(mixin, table: str) -> SchemaContract:
    """The columns a lib's mixin defines, read from a private Base so the example's own models are not involved."""
    private = declarative_base()
    type("Probe", (mixin, private), {"user_fk_target": None})  # no users table in the private metadata
    return schema_contract(private.metadata, tables=[table])


@pytest.fixture
def engine(app):
    return app.state.engine


def test_jobs_table_matches_the_jobs_lib(engine):
    lib_contract(JobsMixin, "background_jobs").assert_matches(engine)


def test_grants_table_matches_the_storage_lib(engine):
    lib_contract(GrantsMixin, "download_grants").assert_matches(engine)


def test_connections_table_matches_the_oauth_lib(engine):
    lib_contract(ConnectionsMixin, "oauth_connections").assert_matches(engine)


def test_tasks_table_matches_the_tasks_lib(engine):
    lib_contract(TasksMixin, "tasks").assert_matches(engine)


def test_users_table_has_what_the_auth_lib_reads(engine):
    SchemaContract({"users": {
        "id": False, "email": False, "capabilities": False, "is_active": False,
        "sessions_valid_after": True, "firebase_uid": True,
    }}).assert_matches(engine)


def test_every_model_table_exists_with_its_columns(engine):
    schema_contract(Base.metadata).assert_matches(engine, strict=True)


def test_the_contract_notices_a_missing_column(engine):
    contract = SchemaContract({"users": {"no_such_column": True}})
    with pytest.raises(AssertionError, match="users.no_such_column is missing"):
        contract.assert_matches(engine)


def index_names(engine, table: str) -> set[str]:
    """Index names in the database. SQLite reflection skips expression indexes, so ask its catalog directly."""
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?", (table,)
            )
            return {row[0] for row in rows}
    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def missing_indexes(engine) -> list[str]:
    """Index names the models declare and the database lacks (expression indexes included, by name)."""
    found = []
    for table in Base.metadata.sorted_tables:
        have = index_names(engine, table.name)
        found += [f"{table.name}.{ix.name}" for ix in table.indexes if ix.name not in have]
    return found


def test_every_model_index_exists_by_name(engine):
    assert missing_indexes(engine) == []
    assert "uq_oauth_connections_live" in index_names(engine, "oauth_connections")


def test_a_missing_index_is_noticed(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX uq_oauth_connections_live")
    assert missing_indexes(engine) == ["oauth_connections.uq_oauth_connections_live"]


def test_the_example_tables_are_the_expected_set(engine):
    names = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert {"users", "background_jobs", "download_grants", "documents", "notes", "oauth_connections", "tasks"} <= names


def test_upgrade_head_on_a_fresh_database_matches_the_models(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/fresh.db"
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", url)
    config = Config()
    config.set_main_option("script_location", str(SERVICE / "alembic"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == []
    schema_contract(Base.metadata).assert_matches(engine, strict=True)
    assert missing_indexes(engine) == []


def test_a_database_the_fake_app_created_is_already_at_head(app, tmp_path, monkeypatch):
    """Fake-mode startup stamps the head it created, so `make migrate` afterwards changes nothing."""
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", str(app.state.engine.url))
    config = Config()
    config.set_main_option("script_location", str(SERVICE / "alembic"))
    command.upgrade(config, "head")  # would raise "table already exists" if the stamp were missing
    with app.state.engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0003"


def test_bootstrap_creates_and_stamps_an_empty_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/empty.db")
    bootstrap_schema(engine)
    assert "users" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0003"


def test_bootstrap_leaves_a_stale_database_alone_and_says_so(tmp_path, caplog):
    engine = create_engine(f"sqlite:///{tmp_path}/stale.db")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id VARCHAR PRIMARY KEY)")
    with caplog.at_level("WARNING", logger="sdk_example"):
        bootstrap_schema(engine)
    names = set(inspect(engine).get_table_names())
    assert names == {"users"}  # no create_all, no alembic_version
    assert "make migrate" in caplog.text


def test_a_fake_app_on_a_stale_database_still_starts(tmp_path, monkeypatch):
    from sdk_example.main import create_app

    path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE something_old (id VARCHAR PRIMARY KEY)")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{path}")
    app = create_app()
    assert "users" not in inspect(app.state.engine).get_table_names()
