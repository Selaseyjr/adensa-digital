"""
Regression tests for the bootstrap pipeline
(app.bootstrap.initialize_adensa and its guards).

The bootstrap contract under test:

- database_schema_exists() / database_contains_operational_data()
  form a two-tier guard: schema presence, then non-empty
  operational tables.
- initialize_adensa() on a fresh environment builds the full
  dataset (master data, 5000 orders, 5000 shipments, events,
  exceptions, recovery options, workflow actions) — the exact
  path the CI workflow relies on for its fresh checkout.
- initialize_adensa() on an initialized database exits without
  regenerating anything (Streamlit-rerun safety).

These tests run the REAL pipeline against an isolated temporary
database file. Both app.database.DATABASE_PATH (connections,
schema) and app.bootstrap.DATABASE_PATH (guard functions) are
re-pointed for the duration of each test, so data/adensa.db is
never read or written.
"""

import pytest

import app.bootstrap as bootstrap
import app.database as database
from app.bootstrap import (
    database_contains_operational_data,
    database_schema_exists,
    initialize_adensa,
)


COUNTED_TABLES = (
    "orders",
    "shipments",
    "shipment_events",
    "exceptions",
    "recovery_options",
    "recovery_actions",
)


@pytest.fixture()
def bootstrap_database(tmp_path, monkeypatch):
    """
    Re-point every database-path reference (connection factory
    and bootstrap guards) at one fresh temporary file and return
    the path. No schema or data exists yet.
    """

    database_path = tmp_path / "bootstrap_adensa.db"

    monkeypatch.setattr(database, "DATABASE_PATH", database_path)
    monkeypatch.setattr(bootstrap, "DATABASE_PATH", database_path)

    return database_path


def table_counts(connection):
    """
    Return the row count of every operational table.
    """

    return {
        table: connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in COUNTED_TABLES
    }


# --------------------------------------------------
# TWO-TIER GUARDS
# --------------------------------------------------

def test_fresh_database_fails_both_guards(bootstrap_database):
    """
    A non-existent database file reports neither schema nor
    operational data.
    """

    assert not bootstrap_database.exists()
    assert database_schema_exists() is False
    assert database_contains_operational_data() is False


def test_schema_without_data_passes_only_schema_guard(
    bootstrap_database,
):
    """
    A schema-only database satisfies the schema guard but not
    the operational-data guard — bootstrap must still run.
    """

    database.initialize_database()

    assert database_schema_exists() is True
    assert database_contains_operational_data() is False


# --------------------------------------------------
# FULL BOOTSTRAP PIPELINE
# --------------------------------------------------

def test_full_bootstrap_populates_fresh_database(
    bootstrap_database,
):
    """
    Starting from nothing, initialize_adensa() builds the
    complete operational dataset — the fresh-checkout path the
    CI workflow depends on.
    """

    assert not bootstrap_database.exists()

    initialize_adensa()

    connection = database.get_connection()

    try:
        counts = table_counts(connection)

        assert counts["orders"] == 5000
        assert counts["shipments"] == 5000
        assert counts["shipment_events"] > 0
        assert counts["exceptions"] > 0
        assert counts["recovery_options"] > 0
        assert counts["recovery_actions"] > 0

        # Detection must have run and populated the exception
        # pipeline that everything downstream consumes.
        assert database_contains_operational_data() is True

    finally:
        connection.close()


# --------------------------------------------------
# IDEMPOTENCE
# --------------------------------------------------

def test_initialize_adensa_is_idempotent(bootstrap_database, monkeypatch):
    """
    A second initialize_adensa() call on an initialized database
    must regenerate nothing: the generator functions are replaced
    with failing sentinels, and all row counts are unchanged.
    """

    initialize_adensa()

    connection = database.get_connection()

    try:
        counts_before = table_counts(connection)
    finally:
        connection.close()

    def _must_not_regenerate(*args, **kwargs):
        raise AssertionError(
            "bootstrap regenerated data on an initialized database"
        )

    monkeypatch.setattr(
        bootstrap,
        "insert_master_data",
        _must_not_regenerate,
    )
    monkeypatch.setattr(
        bootstrap,
        "generate_orders",
        _must_not_regenerate,
    )
    monkeypatch.setattr(
        bootstrap,
        "generate_shipments",
        _must_not_regenerate,
    )

    initialize_adensa()

    connection = database.get_connection()

    try:
        assert table_counts(connection) == counts_before
    finally:
        connection.close()
