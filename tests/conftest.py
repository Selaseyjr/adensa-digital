"""
Shared pytest fixtures for Adensa Digital database tests.

Design:

- Every database-dependent test receives an isolated SQLite
  database in a pytest-managed temporary directory.
- The schema is created with the production initializer
  (app.database.initialize_database) so tests always validate
  the real DDL.
- The temporary path is activated by re-pointing
  app.database.DATABASE_PATH for the duration of the test only.
  pytest's monkeypatch restores the original value automatically,
  so data/adensa.db is never read or written by fixture tests and
  no permanent override exists.
- Foreign-key enforcement is enabled on the test connection.
- The connection is closed after the test; pytest removes tmp_path.

seed_master_data() inserts the shared deterministic master rows
(warehouse, customer, carrier, order).

seed_minimal_supply_chain() inserts the smallest deterministic
master/operational dataset needed by database tests:

- EXC-900001: Low severity, on-time Road shipment.
  The recovery generator skips Low-severity exceptions, so this
  exception has zero recovery options and its decision-engine
  result contains recommendation None.
- EXC-900002: High severity, Sea shipment five days late.
  The generator creates three feasible options (Air/Road/Rail;
  the current mode Sea is never recommended).
"""

import pytest

import app.database as database


@pytest.fixture()
def temp_database(tmp_path, monkeypatch):
    """
    Provide an isolated, schema-initialized SQLite database
    for a single test.
    """

    database_path = tmp_path / "test_adensa.db"

    # Point only the schema/connection module at the temporary
    # path for the duration of this test. app.config.DATABASE_PATH
    # and every other module stay untouched; monkeypatch reverts
    # this automatically afterwards.
    monkeypatch.setattr(database, "DATABASE_PATH", database_path)

    database.initialize_database()

    # Production connection factory: row factory + FK enforcement.
    connection = database.get_connection()

    yield connection

    connection.close()


def seed_master_data(connection):
    """
    Insert the shared deterministic master rows used by every
    database test (warehouse, customer, carrier, order).
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO warehouses (
            warehouse_id, warehouse_name, city, country, capacity_units
        )
        VALUES (
            'WH-900001', 'Fixture Warehouse', 'Rotterdam', 'NL', 10000
        )
        """
    )

    cursor.execute(
        """
        INSERT INTO customers (
            customer_id, customer_name, customer_type, country, city,
            service_level
        )
        VALUES (
            'CUS-900001', 'Fixture Customer', 'Retailer', 'NL',
            'Amsterdam', 'Standard'
        )
        """
    )

    cursor.execute(
        """
        INSERT INTO carriers (
            carrier_id, carrier_name, transport_modes, reliability_score
        )
        VALUES (
            'CAR-900001', 'Fixture Carrier',
            'Air, Road, Rail, Sea', 95
        )
        """
    )

    cursor.execute(
        """
        INSERT INTO orders (
            order_id, customer_id, order_date, required_delivery_date,
            required_delivery_time, service_level, priority, status,
            warehouse_id
        )
        VALUES (
            'ORD-900001', 'CUS-900001', '2026-09-01', '2026-09-15',
            '12:00', 'Standard', 'Medium', 'Confirmed', 'WH-900001'
        )
        """
    )


def seed_minimal_supply_chain(connection):
    """
    Insert the minimal deterministic dataset used by
    database-dependent tests (two exceptions with opposite
    recommendation outcomes).
    """

    seed_master_data(connection)

    cursor = connection.cursor()

    # On-time Road shipment backing the Low-severity exception.
    cursor.execute(
        """
        INSERT INTO shipments (
            shipment_id, order_id, carrier_id, origin, destination,
            transport_mode, quantity, weight_kg, volume_m3, priority,
            planned_departure, actual_departure, planned_arrival,
            estimated_arrival, actual_arrival, status, shipping_cost,
            distance_km, current_location, last_updated
        )
        VALUES (
            'SHP-900001', 'ORD-900001', 'CAR-900001', 'Rotterdam',
            'Hamburg', 'Road', 50, 200, 1, 'Medium', '2026-09-12',
            '2026-09-12', '2026-09-13', '2026-09-13', NULL,
            'In Transit', 200, 450, 'En route', '2026-09-10 12:00:00'
        )
        """
    )

    # Delayed Sea shipment backing the High-severity exception.
    cursor.execute(
        """
        INSERT INTO shipments (
            shipment_id, order_id, carrier_id, origin, destination,
            transport_mode, quantity, weight_kg, volume_m3, priority,
            planned_departure, actual_departure, planned_arrival,
            estimated_arrival, actual_arrival, status, shipping_cost,
            distance_km, current_location, last_updated
        )
        VALUES (
            'SHP-900002', 'ORD-900001', 'CAR-900001', 'Rotterdam',
            'Hamburg', 'Sea', 100, 1000, 5, 'Medium', '2026-09-12',
            '2026-09-12', '2026-09-14', '2026-09-20', NULL,
            'In Transit', 500, 1500, 'At sea', '2026-09-10 12:00:00'
        )
        """
    )

    # Low severity: the generator creates no options for this one.
    cursor.execute(
        """
        INSERT INTO exceptions (
            exception_id, shipment_id, exception_type, severity,
            detected_at, description, estimated_impact,
            resolution_status, resolved_at
        )
        VALUES (
            'EXC-900001', 'SHP-900001', 'Shipment Delay', 'Low',
            '2026-09-10 12:00:00',
            'Fixture exception: monitored, no recovery needed', 500,
            'Open', NULL
        )
        """
    )

    # High severity: delayed, yields three feasible options.
    cursor.execute(
        """
        INSERT INTO exceptions (
            exception_id, shipment_id, exception_type, severity,
            detected_at, description, estimated_impact,
            resolution_status, resolved_at
        )
        VALUES (
            'EXC-900002', 'SHP-900002', 'Shipment Delay', 'High',
            '2026-09-10 12:00:00',
            'Fixture exception: five days late', 5000,
            'Open', NULL
        )
        """
    )

    connection.commit()


@pytest.fixture()
def master_database(temp_database):
    """
    Provide an isolated database containing only the deterministic
    master rows (warehouse, customer, carrier, order) and no
    operational data — the starting point for testing the
    detection and generation modules.
    """

    seed_master_data(temp_database)

    return temp_database


@pytest.fixture()
def seeded_database(temp_database):
    """
    Provide an isolated database pre-populated with the minimal
    deterministic supply-chain dataset.
    """

    seed_minimal_supply_chain(temp_database)

    return temp_database
