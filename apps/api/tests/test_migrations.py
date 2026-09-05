from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "players",
    "teams",
    "player_team_history",
    "agents",
    "events",
    "matches",
    "match_maps",
    "player_map_stats",
    "team_rating_snapshots",
    "metric_versions",
    "player_metric_snapshots",
    "player_metric_scoped_snapshots",
    "data_sync_runs",
}

MIGRATION_DATABASE_URL = os.environ.get(
    "MIGRATION_DATABASE_URL",
    "postgresql://valorant:valorant@127.0.0.1:5432/valorant_scout_alembic_test",
)


def _recreate_database(database_url: str) -> None:
    url = make_url(database_url)
    db_name = url.database
    owner = url.username or "valorant"
    assert db_name is not None
    admin_url = url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(
            text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name"),
            {"name": db_name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        connection.execute(text(f'CREATE DATABASE "{db_name}" OWNER "{owner}"'))
    admin_engine.dispose()


@pytest.fixture
def migration_engine() -> Iterator[Engine]:
    _recreate_database(MIGRATION_DATABASE_URL)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = MIGRATION_DATABASE_URL
    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_upgrade_from_empty_database(migration_engine: Engine) -> None:
    assert _table_names(migration_engine) == set()
    command.upgrade(alembic_config(MIGRATION_DATABASE_URL), "head")
    tables = _table_names(migration_engine)
    assert EXPECTED_TABLES.issubset(tables)
    assert "alembic_version" in tables


def test_downgrade_removes_application_tables(migration_engine: Engine) -> None:
    command.upgrade(alembic_config(MIGRATION_DATABASE_URL), "head")
    command.downgrade(alembic_config(MIGRATION_DATABASE_URL), "base")
    tables = _table_names(migration_engine)
    assert tables.isdisjoint(EXPECTED_TABLES)


def test_upgrade_after_downgrade(migration_engine: Engine) -> None:
    config = alembic_config(MIGRATION_DATABASE_URL)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert EXPECTED_TABLES.issubset(_table_names(migration_engine))
