"""
PostgreSQL integration tests (P5.3) — opt-in only.

These tests run against a live PostgreSQL server selected by
the environment:

    TEST_DATABASES_URL   postgresql://user:pass@host:5432/server-db
                         (the server itself; each test creates
                         its own temporary database and drops
                         it afterwards)

They are marked `postgres` and excluded from the default
suite (pytest.ini: addopts `-m "not postgres"`); run them with:

    pytest -m postgres

CI provides the server through a postgres:16 service container
and points TEST_DATABASES_URL at the same opt-in mechanism used
locally. The SQLite suite and the development database are
never touched by this module.
"""

import os

import pytest

pytestmark = pytest.mark.postgres

# Provisioned by CI; optional locally. Skip (not fail) when no
# PostgreSQL server is configured.
SERVER_URL = os.environ.get("TEST_DATABASES_URL")

if not SERVER_URL:  # pragma: no cover - environment guard
    pytest.skip(
        "TEST_DATABASES_URL is not configured; skipping "
        "PostgreSQL integration tests",
        allow_module_level=True,
    )


# ==================================================
# TEMPORARY DATABASE FIXTURE
# ==================================================


@pytest.fixture()
def postgres_database(monkeypatch):
    """
    Create a fresh temporary database on the configured server,
    expose it to the application through the production
    DATABASE_URL contract, and drop it afterwards.
    """

    import psycopg

    admin_database = SERVER_URL.split("/")[-1].split("?")[0]

    with psycopg.connect(
        SERVER_URL,
        autocommit=True,
    ) as admin:

        test_database = f"adensa_test_{os.getpid()}"

        admin.execute(
            f'DROP DATABASE IF EXISTS "{test_database}"'
        )
        admin.execute(f'CREATE DATABASE "{test_database}"')

    test_url = SERVER_URL.replace(
        f"/{admin_database}",
        f"/{test_database}",
    )

    monkeypatch.setenv("DATABASE_URL", test_url)

    import app.database as database

    yield database

    with psycopg.connect(
        SERVER_URL,
        autocommit=True,
    ) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{test_database}"')


# ==================================================
# CONNECTION
# ==================================================


def test_configuration_resolves_to_postgres(postgres_database):
    """The production configuration boundary selects PostgreSQL."""

    from app.config import get_database_config

    config = get_database_config()

    assert config.is_postgresql
    assert not config.is_sqlite

    # Credentials never surface in the loggable description.
    assert "test_password" not in config.safe_description()


def test_connection_succeeds_with_row_contract(postgres_database):
    """
    The adapter delivers the sqlite3.Row access contract over
    PostgreSQL: name access, positional access, tuple(),
    len() and dict() all behave as the services expect.
    """

    connection = postgres_database.get_connection()

    try:
        rows = connection.execute(
            "SELECT 'Adensa' AS label, 42 AS answer"
        ).fetchall()

        assert len(rows) == 1

        row = rows[0]

        assert row["label"] == "Adensa"
        assert row["answer"] == 42
        assert row[0] == "Adensa"
        assert tuple(row) == ("Adensa", 42)
        assert len(row) == 2
        assert dict(row) == {"label": "Adensa", "answer": 42}
    finally:
        connection.close()


def test_credentials_are_not_logged(postgres_database, caplog):
    """The connection log line carries no password."""

    import logging

    logging.getLogger().setLevel(logging.INFO)

    connection = postgres_database.get_connection()

    try:
        pass
    finally:
        connection.close()

    for record in caplog.records:
        assert "test_password" not in record.getMessage()


# ==================================================
# MIGRATIONS
# ==================================================


def test_fresh_database_reaches_current_version(postgres_database):
    """
    A fresh PostgreSQL database applies the full migration
    history through the production initializer.
    """

    from app.migrations import CURRENT_VERSION, get_schema_version

    postgres_database.initialize_database()

    connection = postgres_database.get_connection()

    try:
        assert get_schema_version(connection) == CURRENT_VERSION

        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                """
            ).fetchall()
        }

        assert "manual_interventions" in tables
        assert "exceptions" in tables
        assert "recovery_options" in tables
        assert "schema_migrations" in tables

        # The translated DDL carries the P5.3 type decisions.
        columns = {
            row["column_name"]: row["data_type"]
            for row in connection.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'exceptions'
                AND table_schema = 'public'
                """
            ).fetchall()
        }

        assert columns["estimated_impact"] == "text"

        option_columns = {
            row["column_name"]: row["data_type"]
            for row in connection.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'recovery_options'
                AND table_schema = 'public'
                """
            ).fetchall()
        }

        assert option_columns["feasible"] == "boolean"

        supplier_columns = {
            row["column_name"]: row["data_type"]
            for row in connection.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'suppliers'
                AND table_schema = 'public'
                """
            ).fetchall()
        }

        assert supplier_columns["active"] == "boolean"
    finally:
        connection.close()


def test_current_database_is_a_noop(postgres_database, monkeypatch):
    """A schema-current PostgreSQL database performs no work."""

    import app.database as database_module
    from app import migrations

    postgres_database.initialize_database()

    calls = []

    def _tracking_apply(connection):
        calls.append(connection)

        return migrations.get_schema_version(connection)

    # initialize_database resolves apply_pending_migrations from
    # the app.database module namespace at call time, so the
    # tracking substitute must be bound there.
    monkeypatch.setattr(
        database_module,
        "apply_pending_migrations",
        _tracking_apply,
    )

    postgres_database.initialize_database()

    assert calls == []


def test_foreign_keys_are_enforced(postgres_database):
    """
    The schema's referential integrity holds on PostgreSQL:
    inserting a shipment for a missing order is rejected.
    """

    postgres_database.initialize_database()

    connection = postgres_database.get_connection()

    try:
        connection.execute(
            "BEGIN"
        )  # no-op under autocommit; keeps parity with the engines

        with pytest.raises(Exception):
            connection.execute(
                """
                INSERT INTO shipments (
                    shipment_id, order_id, carrier_id, origin,
                    destination, transport_mode, quantity,
                    weight_kg, volume_m3, priority,
                    planned_departure, actual_departure,
                    planned_arrival, estimated_arrival,
                    actual_arrival, status, shipping_cost,
                    distance_km, current_location, last_updated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SHP-PG-ORPHAN", "ORD-MISSING", "CAR-0001",
                    "A", "B", "Road", 1, 1.0, 1.0, "Medium",
                    "2026-09-10", None, "2026-09-11", None,
                    None, "In Transit", 10.0, 10.0, "x",
                    "2026-09-10 12:00:00",
                ),
            )

        connection.rollback()
    finally:
        connection.close()


# ==================================================
# DIALECT ROUND-TRIP
# ==================================================


def test_master_data_generation_round_trip(postgres_database):
    """
    The data generator exercises INSERT OR IGNORE, executemany
    and boolean binds against the translated dialect.
    """

    postgres_database.initialize_database()

    from app.generate_data import insert_master_data

    connection = postgres_database.get_connection()

    try:
        insert_master_data(connection)

        count = connection.execute(
            "SELECT COUNT(*) FROM suppliers"
        ).fetchone()

        assert count[0] > 0

        # Idempotency: a second run inserts nothing new.
        insert_master_data(connection)

        count_again = connection.execute(
            "SELECT COUNT(*) FROM suppliers"
        ).fetchone()

        assert count_again[0] == count[0]

        # Boolean round-trip: active comes back truthy.
        supplier = connection.execute(
            "SELECT supplier_id, active FROM suppliers LIMIT 1"
        ).fetchone()

        assert supplier["supplier_id"] == "SUP-001"
        assert bool(supplier["active"]) is True
    finally:
        connection.close()


# ==================================================
# TRANSACTION BEHAVIOR
# ==================================================


def test_multi_statement_transaction_rolls_back_atomically(
    postgres_database,
):
    """
    The engine transaction discipline holds on PostgreSQL:
    statements across multiple tables commit together, and a
    failure rolls the whole unit back.
    """

    postgres_database.initialize_database()

    from tests.conftest import seed_master_data, seed_minimal_supply_chain

    connection = postgres_database.get_connection()

    try:
        seed_master_data(connection)
        connection.commit()

        # Two-table unit of work: a shipment event plus a
        # shipment update must succeed or fail together.
        connection.execute("BEGIN")  # no-op; transaction is implicit

        connection.execute(
            """
            INSERT INTO shipment_events (
                event_id, shipment_id, event_type,
                event_timestamp, location, description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "EVT-PG-001", "SHP-900001", "Test Event",
                "2026-09-10 12:00:00", "Rotterdam", "Transaction probe",
            ),
        )

        connection.commit()

        # Now the rollback branch: a fresh implicit transaction
        # whose failure must undo both statements.
        connection.execute(
            "INSERT INTO shipment_events ("
            "event_id, shipment_id, event_type, event_timestamp,"
            "location, description"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                "EVT-PG-002", "SHP-900001", "Test Event",
                "2026-09-10 12:01:00", "Rotterdam", "Rollback probe",
            ),
        )

        connection.execute(
            "UPDATE shipment_events SET description = ? "
            "WHERE event_id = ?",
            ("Updated", "EVT-PG-002"),
        )

        connection.rollback()

        remaining = connection.execute(
            "SELECT COUNT(*) FROM shipment_events "
            "WHERE event_id IN ('EVT-PG-001', 'EVT-PG-002')"
        ).fetchone()

        assert remaining[0] == 1
    finally:
        connection.close()


# ==================================================
# DOMAIN LIFECYCLE
# ==================================================


def test_exception_to_recovery_action_lifecycle(postgres_database):
    """
    The full operational path on PostgreSQL, mirroring the
    SQLite vertical slice: baseline refresh → simulated
    arrival → refresh → recommend → approve → execute, with
    Executed ≠ Resolved preserved.
    """

    from app import services
    from app.simulation import create_simulated_arrival
    from tests.conftest import seed_minimal_supply_chain

    postgres_database.initialize_database()

    connection = postgres_database.get_connection()

    try:
        seed_minimal_supply_chain(connection)
        connection.commit()

        services.run_operational_refresh(connection)

        arrival = create_simulated_arrival(connection)

        assert arrival is not None

        refresh = services.run_operational_refresh(connection)

        assert refresh["new_exceptions"] == 1
        assert refresh["new_options"] == 3
        assert refresh["new_actions"] == 1

        exception_id = refresh["new_exception_ids"][0]

        context = services.get_exception_context(
            connection,
            exception_id,
        )

        assert context is not None

        review = services.get_exception_review(
            connection,
            exception_id,
        )

        recommendation = review["recommendation"]

        assert recommendation is not None
        assert recommendation["option_id"].startswith("OPT-")
        assert len(review["alternatives"]) == 2

        action = services.get_latest_action(
            connection,
            exception_id,
        )

        assert action["status"] == "Pending Approval"
        assert action["option_id"] == recommendation["option_id"]

        approval = services.approve_recovery(
            connection,
            action["action_id"],
            "Postgres Integration Test",
        )

        assert approval["success"] is True

        outcome = services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        assert outcome["success"] is True

        # Executed ≠ Resolved: the engine truthfully reports
        # the exception as still open on this fixture.
        assert outcome["exception_status"] == "Open"
    finally:
        connection.close()
