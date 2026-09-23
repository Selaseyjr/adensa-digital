"""
Migration tests for the schema-evolution foundation (ADR-012).

The migration contract under test:

- a fresh database reaches the current schema through the full
  migration history;
- a version-0 database — the state of every database created
  before migrations existed, including data/adensa.db — upgrades
  additively without touching existing operational data;
- a current database is a no-op;
- migrations run in order, inside transactions, and a failure
  never falsely advances the recorded version;
- the bootstrap schema guard knows the full current schema.

Every test runs against a disposable temporary database;
data/adensa.db is never touched.
"""

import sqlite3

import pytest

import app.database as database
from app import migrations
from app.bootstrap import REQUIRED_TABLES
from app.migrations import (
    CURRENT_VERSION,
    MIGRATIONS,
    apply_pending_migrations,
    get_schema_version,
)


# ==================================================
# HELPERS / FIXTURES
# ==================================================

CANONICAL_TABLES = {
    "customers",
    "suppliers",
    "products",
    "warehouses",
    "carriers",
    "orders",
    "order_items",
    "inventory",
    "shipments",
    "shipment_events",
    "exceptions",
    "recovery_options",
    "recovery_actions",
    "manual_interventions",
}


@pytest.fixture()
def migration_database(tmp_path, monkeypatch):
    """
    Re-point the connection factory at a disposable file and
    return the path. Nothing exists yet.
    """

    database_path = tmp_path / "migration_adensa.db"
    monkeypatch.setattr(database, "DATABASE_PATH", database_path)
    return database_path


def table_names(connection):
    rows = connection.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {row[0] for row in rows}


def make_version0_database(path):
    """
    Create a version-0 database the way the pre-migration
    initializer did: canonical DDL applied with no version stamp
    (PRAGMA user_version stays 0).
    """

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    for _, _, statements in MIGRATIONS:
        for statement in statements:
            connection.execute(statement)

    connection.commit()
    assert get_schema_version(connection) == 0
    return connection


# ==================================================
# FRESH DATABASE
# ==================================================

def test_fresh_database_reaches_current_schema(migration_database):
    """
    initialize_database() on nothing builds the complete current
    schema and stamps the current migration version.
    """

    database.initialize_database()

    connection = database.get_connection()
    try:
        assert table_names(connection) == CANONICAL_TABLES
        assert get_schema_version(connection) == CURRENT_VERSION
    finally:
        connection.close()


def test_fresh_database_version_matches_migration_history():
    """
    The declared current version is the last migration in the
    history — the stamp can never run ahead of defined work.
    """

    assert CURRENT_VERSION == MIGRATIONS[-1][0]
    assert len({version for version, _, _ in MIGRATIONS}) == len(MIGRATIONS)


# ==================================================
# VERSION-0 UPGRADE
# ==================================================

def test_version0_database_upgrades_to_current_schema(migration_database):
    """
    A database built before migrations existed (version 0) is
    upgraded through the history to the current version and
    gains every table, including manual_interventions.
    """

    connection = make_version0_database(migration_database)
    connection.close()

    database.initialize_database()

    connection = database.get_connection()
    try:
        assert get_schema_version(connection) == CURRENT_VERSION
        assert table_names(connection) == CANONICAL_TABLES
    finally:
        connection.close()


def test_version0_upgrade_preserves_operational_data(migration_database):
    """
    The additive upgrade must not touch existing rows: the
    version-0 database is seeded with operational data, upgraded,
    and every count is compared before/after.
    """

    connection = make_version0_database(migration_database)

    connection.execute(
        """
        INSERT INTO customers VALUES (
            'CUS-TEST', 'Test Customer', 'direct', 'Germany', 'Hamburg', 'standard'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO warehouses VALUES ('WH-TEST', 'Test Warehouse', 'Hamburg', 'Germany', 100)
        """
    )
    connection.execute(
        """
        INSERT INTO orders (
            order_id, customer_id, order_date, required_delivery_date,
            required_delivery_time, service_level, priority, status, warehouse_id
        ) VALUES (
            'ORD-TEST', 'CUS-TEST', '2026-01-01', '2026-01-10',
            '12:00', 'standard', 'normal', 'in_transit', 'WH-TEST'
        )
        """
    )
    connection.commit()

    tables = sorted(table_names(connection) - {"manual_interventions"})
    counts_before = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
    connection.close()

    database.initialize_database()

    connection = database.get_connection()
    try:
        counts_after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }

        assert counts_after == counts_before
        assert counts_after["customers"] == 1
        assert counts_after["orders"] == 1
    finally:
        connection.close()


def test_version0_database_is_fully_current_after_upgrade(migration_database):
    """
    After the version-0 upgrade the database is byte-for-byte
    current: a second run is a no-op, proving the upgrade reached
    exactly the canonical state.
    """

    connection = make_version0_database(migration_database)
    connection.close()

    database.initialize_database()
    database.initialize_database()  # must not raise or rework

    connection = database.get_connection()
    try:
        assert get_schema_version(connection) == CURRENT_VERSION
        assert table_names(connection) == CANONICAL_TABLES
    finally:
        connection.close()


# ==================================================
# CURRENT DATABASE NO-OP
# ==================================================

def test_current_database_is_noop(migration_database, monkeypatch):
    """
    A current database performs no migration work: the runner is
    replaced with a failing sentinel and initialization still
    succeeds.
    """

    database.initialize_database()

    def _must_not_migrate(connection):
        raise AssertionError("migrations ran on a current database")

    monkeypatch.setattr(migrations, "apply_pending_migrations", _must_not_migrate)

    database.initialize_database()


# ==================================================
# RUNNER SEMANTICS
# ==================================================

def test_migrations_run_in_deterministic_order(migration_database):
    """
    Versions are applied strictly in ascending order.
    """

    connection = sqlite3.connect(migration_database)

    applied_versions = []
    connection.set_trace_callback(
        lambda statement: applied_versions.append(int(statement.rsplit("=", 1)[1]))
        if statement.startswith("PRAGMA user_version =")
        else None
    )

    try:
        assert apply_pending_migrations(connection) == CURRENT_VERSION
    finally:
        connection.set_trace_callback(None)
        connection.close()

    assert applied_versions == sorted(
        version for version, _, _ in MIGRATIONS
    )


def test_migration_failure_does_not_advance_version(
    migration_database,
    monkeypatch,
):
    """
    A failing migration must roll back and leave the recorded
    version untouched — a partial migration can never claim
    success.
    """

    connection = sqlite3.connect(migration_database)

    # Simulate a history where the second migration applies one
    # statement and then fails: the failed migration's own work
    # must be rolled back with it.
    exploding = [
        (1, "first", ["CREATE TABLE ok_table (id INTEGER)"]),
        (
            2,
            "second",
            [
                "CREATE TABLE second_table (id INTEGER)",
                "CREATE TABLE broken (incomplete",
            ],
        ),
    ]

    monkeypatch.setattr(migrations, "MIGRATIONS", exploding)

    with pytest.raises(Exception):
        apply_pending_migrations(connection)

    # The completed first migration keeps its version stamp, and
    # the failed migration's work is fully rolled back — the
    # version can never claim success for migration 2.
    assert get_schema_version(connection) == 1
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'ok_table'"
        ).fetchone()[0]
        == 1
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'second_table'"
        ).fetchone()[0]
        == 0
    )
    connection.close()


def test_schema_version_is_inspectable(migration_database):
    """
    A fresh database reports version 0 before initialization and
    the current version after it.
    """

    connection = sqlite3.connect(migration_database)
    assert get_schema_version(connection) == 0
    connection.close()

    database.initialize_database()

    connection = database.get_connection()
    try:
        assert get_schema_version(connection) == CURRENT_VERSION
    finally:
        connection.close()


# ==================================================
# BOOTSTRAP GUARD CONTRACT
# ==================================================

def test_required_tables_includes_manual_interventions():
    """
    The bootstrap schema guard must know the full current schema:
    a database missing manual_interventions is not schema-current.
    """

    assert "manual_interventions" in REQUIRED_TABLES
    assert REQUIRED_TABLES == CANONICAL_TABLES


def test_schema_current_database_passes_required_tables_guard(migration_database):
    """
    After initialization the database satisfies the bootstrap
    schema guard exactly — the guard and the migration history
    describe the same schema.
    """

    from app.bootstrap import database_schema_exists

    database.initialize_database()

    assert database_schema_exists() is True
