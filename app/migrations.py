"""
Database schema evolution for Adensa Digital (ADR-012).

The migration history is the conceptual source of truth for the
database schema. It records the project's real evolution:

    0001 — the founding relational schema (13 tables)
    0002 — manual exception resolution (manual_interventions)

The runner is deliberately small and dependency-free:

- fresh database  -> every migration applies in order
- version-0 file  -> every migration applies in order (additive,
                      historical migrations are idempotent CREATE
                      TABLE IF NOT EXISTS statements, so an existing
                      pre-migration database is upgraded safely)
- current file    -> no work beyond the version read
- each migration  -> applied inside a transaction, so a failure
                      never falsely advances the recorded version

SQLite stores the applied version in `PRAGMA user_version`; the
migration abstraction itself is plain SQL and sequential version
numbers, so the same history can drive PostgreSQL (where the
version stamp becomes a `schema_migrations` row) without a second
competing schema-definition system.

Version-state portability (P5.2): the runner speaks to the
backend's version store through two functions —
`_read_stored_version` and `_write_stored_version` — resolved
per connection by `_version_backend`. The SQLite
implementation is the historical `PRAGMA user_version`; a
PostgreSQL `schema_migrations` table implementation slots in
at that seam without touching the runner, the history, or the
guarantees.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ==================================================
# MIGRATION DEFINITIONS
# ==================================================
#
# Each migration is (version, name, list of SQL statements).
# Statements run in order inside one transaction. DDL here is
# written additively and idempotently so the version-0 upgrade
# path (a database created before migrations existed) applies
# the full history without touching existing data.

MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "founding relational schema",
        [
            """
            CREATE TABLE IF NOT EXISTS customers (
                customer_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                customer_type TEXT NOT NULL,
                country TEXT NOT NULL,
                city TEXT NOT NULL,
                service_level TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS suppliers (
                supplier_id TEXT PRIMARY KEY,
                supplier_name TEXT NOT NULL,
                country TEXT NOT NULL,
                city TEXT NOT NULL,
                reliability_score REAL NOT NULL,
                average_lead_time_days INTEGER NOT NULL,
                active INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                unit_weight_kg REAL NOT NULL,
                unit_volume_m3 REAL NOT NULL,
                unit_value REAL NOT NULL,
                supplier_id TEXT NOT NULL,
                lead_time_days INTEGER NOT NULL,
                reorder_point INTEGER NOT NULL,
                safety_stock INTEGER NOT NULL,
                active INTEGER NOT NULL,

                FOREIGN KEY (supplier_id)
                    REFERENCES suppliers(supplier_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warehouses (
                warehouse_id TEXT PRIMARY KEY,
                warehouse_name TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT NOT NULL,
                capacity_units INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS carriers (
                carrier_id TEXT PRIMARY KEY,
                carrier_name TEXT NOT NULL,
                transport_modes TEXT NOT NULL,
                reliability_score REAL NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                order_date TEXT NOT NULL,
                required_delivery_date TEXT NOT NULL,
                required_delivery_time TEXT NOT NULL,
                service_level TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                warehouse_id TEXT NOT NULL,

                FOREIGN KEY (customer_id)
                    REFERENCES customers(customer_id),

                FOREIGN KEY (warehouse_id)
                    REFERENCES warehouses(warehouse_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS order_items (
                order_item_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,

                FOREIGN KEY (order_id)
                    REFERENCES orders(order_id),

                FOREIGN KEY (product_id)
                    REFERENCES products(product_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS inventory (
                inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                warehouse_id TEXT NOT NULL,
                quantity_on_hand INTEGER NOT NULL,
                quantity_reserved INTEGER NOT NULL,
                quantity_available INTEGER NOT NULL,
                reorder_point INTEGER NOT NULL,
                safety_stock INTEGER NOT NULL,
                inventory_status TEXT NOT NULL,
                last_updated TEXT NOT NULL,

                FOREIGN KEY (product_id)
                    REFERENCES products(product_id),

                FOREIGN KEY (warehouse_id)
                    REFERENCES warehouses(warehouse_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shipments (
                shipment_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                carrier_id TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                transport_mode TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                weight_kg REAL NOT NULL,
                volume_m3 REAL NOT NULL,
                priority TEXT NOT NULL,
                planned_departure TEXT NOT NULL,
                actual_departure TEXT,
                planned_arrival TEXT NOT NULL,
                estimated_arrival TEXT,
                actual_arrival TEXT,
                status TEXT NOT NULL,
                shipping_cost REAL NOT NULL,
                distance_km REAL NOT NULL,
                current_location TEXT NOT NULL,
                last_updated TEXT NOT NULL,

                FOREIGN KEY (order_id)
                    REFERENCES orders(order_id),

                FOREIGN KEY (carrier_id)
                    REFERENCES carriers(carrier_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shipment_events (
                event_id TEXT PRIMARY KEY,
                shipment_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,

                FOREIGN KEY (shipment_id)
                    REFERENCES shipments(shipment_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS exceptions (
                exception_id TEXT PRIMARY KEY,
                shipment_id TEXT NOT NULL,
                exception_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                description TEXT NOT NULL,
                estimated_impact REAL NOT NULL,
                resolution_status TEXT NOT NULL,
                resolved_at TEXT,

                FOREIGN KEY (shipment_id)
                    REFERENCES shipments(shipment_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS recovery_options (
                option_id TEXT PRIMARY KEY,
                exception_id TEXT NOT NULL,
                transport_mode TEXT NOT NULL,
                carrier_id TEXT NOT NULL,
                estimated_cost REAL NOT NULL,
                estimated_transit_days REAL NOT NULL,
                capacity_available REAL NOT NULL,
                risk_score REAL NOT NULL,
                feasible INTEGER NOT NULL,

                FOREIGN KEY (exception_id)
                    REFERENCES exceptions(exception_id),

                FOREIGN KEY (carrier_id)
                    REFERENCES carriers(carrier_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS recovery_actions (
                action_id TEXT PRIMARY KEY,
                exception_id TEXT NOT NULL,
                option_id TEXT,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                approved_by TEXT,
                approved_at TEXT,
                executed_at TEXT,

                FOREIGN KEY (exception_id)
                    REFERENCES exceptions(exception_id),

                FOREIGN KEY (option_id)
                    REFERENCES recovery_options(option_id)
            )
            """,
        ],
    ),
    (
        2,
        "manual exception resolution",
        [
            """
            CREATE TABLE IF NOT EXISTS manual_interventions (
                intervention_id TEXT PRIMARY KEY,
                exception_id TEXT NOT NULL,
                intervention_type TEXT NOT NULL,
                external_party TEXT NOT NULL,
                resolution_summary TEXT NOT NULL,
                new_expected_delivery TEXT,
                outcome TEXT NOT NULL,
                notes TEXT,
                recorded_by TEXT NOT NULL,
                recorded_at TEXT NOT NULL,

                FOREIGN KEY (exception_id)
                    REFERENCES exceptions(exception_id)
            )
            """,
        ],
    ),
]

# Version the schema is expected to reach.
CURRENT_VERSION: int = MIGRATIONS[-1][0]

# SQLite records the applied version here.
_SCHEMA_VERSION_COMMAND = "PRAGMA user_version = {version}"


# ==================================================
# VERSION-STATE BACKEND SEAM (P5.2)
# ==================================================
#
# The runner's only backend-specific concern is where the
# applied version lives. SQLite: PRAGMA user_version.
# PostgreSQL (future): a schema_migrations table. Selecting
# by connection dialect keeps one runner and one history for
# both backends.


def _sqlite_version_backend(connection):

    def read_version():
        row = connection.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    def write_version(version):
        connection.execute(
            _SCHEMA_VERSION_COMMAND.format(version=version)
        )

    return read_version, write_version


def _version_backend(connection):
    """Resolve the version store for a connection's dialect."""

    module_name = type(connection).__module__ or ""

    if "sqlite3" in module_name or type(connection).__name__ == "Connection" and module_name.endswith("sqlite3"):
        return _sqlite_version_backend(connection)

    # Unknown/undialectable connections (test doubles): the
    # runner has only ever been exercised against SQLite, and
    # the PostgreSQL seam is not implemented yet, so the
    # historical default is the only honest choice.
    return _sqlite_version_backend(connection)


# ==================================================
# VERSION INSPECTION
# ==================================================

def get_schema_version(connection) -> int:
    """Return the schema version recorded for this database."""

    read_version, _ = _version_backend(connection)
    return read_version()


# ==================================================
# MIGRATION RUNNER
# ==================================================

def apply_pending_migrations(connection) -> int:
    """
    Apply every migration newer than the recorded schema
    version, in order, and stamp the reached version.

    Each migration commits on its own transaction: a failure
    aborts before the version stamp, so the version can never
    claim success for work that did not complete. Returns the
    schema version after running.
    """

    current = get_schema_version(connection)
    applied = 0

    _, write_version = _version_backend(connection)

    for version, name, statements in MIGRATIONS:
        if version <= current:
            continue

        try:
            connection.execute("BEGIN")
            for statement in statements:
                connection.execute(statement)
            write_version(version)
            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("Migration %04d (%s) failed", version, name)
            raise

        applied += 1
        logger.info("Migration %04d applied: %s", version, name)

    if applied:
        logger.info(
            "Schema migrated %d -> %d (%d migration(s))",
            current,
            get_schema_version(connection),
            applied,
        )

    return get_schema_version(connection)
