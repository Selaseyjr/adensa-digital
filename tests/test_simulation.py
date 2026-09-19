"""
Focused tests for the controlled data-arrival simulation.

The simulation must create ARRIVAL DATA ONLY: one
deterministic delayed shipment plus its shipment events.
Exceptions, recovery options and workflow actions must be
produced exclusively by the existing operational pipeline
when run_operational_refresh() is triggered.

All tests run on the temporary database fixtures; the
development database is never touched.
"""

import pytest

from app import services
from app.repositories import shipments_repo
from app.simulation import create_simulated_arrival


# ==================================================
# HELPERS
# ==================================================

def _count(connection, table):
    """Return the raw row count of a table."""

    return connection.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]


def _count_simulated_shipments(connection):
    """Return the number of SHP-SIM-% shipments."""

    return connection.execute(
        """
        SELECT COUNT(*)
        FROM shipments
        WHERE shipment_id LIKE 'SHP-SIM-%'
        """
    ).fetchone()[0]


def _establish_processed_baseline(connection):
    """
    Bring the seeded fixture to the fully processed
    control-tower state the demo starts from: detection
    finds nothing new, the High-severity exception has its
    three options and the workflow engine has created its
    action.
    """

    return services.run_operational_refresh(connection)


# ==================================================
# SIMULATION CREATION
# ==================================================

def test_simulation_creates_one_shipment_with_events(
    seeded_database,
):
    """
    One simulated arrival creates exactly one shipment with
    exactly two events, under the simulation ID convention.
    """

    connection = seeded_database

    shipments_before = _count(connection, "shipments")
    events_before = _count(connection, "shipment_events")

    result = create_simulated_arrival(connection)

    assert result is not None
    assert result["shipment_id"] == "SHP-SIM-0001"
    assert result["event_count"] == 2

    assert _count_simulated_shipments(connection) == 1
    assert _count(connection, "shipments") == (
        shipments_before + 1
    )
    assert _count(connection, "shipment_events") == (
        events_before + 2
    )


def test_simulation_shipment_satisfies_all_constraints(
    seeded_database,
):
    """
    The simulated shipment references a valid existing order
    and carrier, fills every NOT NULL column and passes the
    database's foreign-key integrity check.
    """

    connection = seeded_database

    result = create_simulated_arrival(connection)

    shipment = connection.execute(
        """
        SELECT *
        FROM shipments
        WHERE shipment_id = ?
        """,
        (result["shipment_id"],),
    ).fetchone()

    assert shipment is not None

    # Valid existing order and carrier references.
    order = connection.execute(
        "SELECT order_id FROM orders WHERE order_id = ?",
        (shipment["order_id"],),
    ).fetchone()

    carrier = connection.execute(
        "SELECT carrier_id FROM carriers WHERE carrier_id = ?",
        (shipment["carrier_id"],),
    ).fetchone()

    assert order is not None
    assert carrier is not None

    # Every NOT NULL shipment column is populated.
    for column in (
        "order_id",
        "carrier_id",
        "origin",
        "destination",
        "transport_mode",
        "quantity",
        "weight_kg",
        "volume_m3",
        "priority",
        "planned_departure",
        "planned_arrival",
        "status",
        "shipping_cost",
        "distance_km",
        "current_location",
        "last_updated",
    ):
        assert shipment[column] is not None, column

    # The arrival's events reference the simulated shipment
    # and are unique.
    events = connection.execute(
        """
        SELECT event_id
        FROM shipment_events
        WHERE shipment_id = ?
        """,
        (result["shipment_id"],),
    ).fetchall()

    assert len(events) == 2
    assert len({row["event_id"] for row in events}) == 2

    # Full-database foreign-key integrity holds.
    assert connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []


def test_simulation_returns_none_without_operational_data(
    master_database,
):
    """
    Without any shipment to derive the scenario from, the
    simulation creates nothing and reports None.
    """

    connection = master_database

    result = create_simulated_arrival(connection)

    assert result is None
    assert _count_simulated_shipments(connection) == 0


# ==================================================
# DETERMINISM
# ==================================================

def test_simulation_scenario_is_deterministic(seeded_database):
    """
    The arrival is fully derived from the baseline order's
    required delivery date: required + 6 days estimated
    arrival, a Sea shipment in transit, and no randomness
    or wall-clock time anywhere.
    """

    connection = seeded_database

    result = create_simulated_arrival(connection)

    assert result["order_id"] == "ORD-900001"
    assert result["carrier_id"] == "CAR-900001"
    assert result["required_delivery"] == "2026-09-15"
    assert result["estimated_arrival"] == "2026-09-21"
    assert result["delay_days"] == 6

    shipment = connection.execute(
        """
        SELECT transport_mode, priority, status,
               planned_departure, planned_arrival,
               estimated_arrival
        FROM shipments
        WHERE shipment_id = ?
        """,
        (result["shipment_id"],),
    ).fetchone()

    assert shipment["transport_mode"] == "Sea"
    assert shipment["priority"] == "Medium"
    assert shipment["status"] == "In Transit"
    assert shipment["planned_departure"] == "2026-09-11"
    assert shipment["planned_arrival"] == "2026-09-14"
    assert shipment["estimated_arrival"] == "2026-09-21"


def test_repeated_simulations_continue_the_sequence(
    seeded_database,
):
    """
    Each simulation creates the next unique simulation
    shipment and event IDs, and never modifies the baseline
    operational records.
    """

    connection = seeded_database

    baseline_shipments = _count(connection, "shipments")
    baseline_exceptions = _count(connection, "exceptions")

    first = create_simulated_arrival(connection)
    second = create_simulated_arrival(connection)

    assert first["shipment_id"] == "SHP-SIM-0001"
    assert second["shipment_id"] == "SHP-SIM-0002"

    simulated = connection.execute(
        """
        SELECT shipment_id
        FROM shipments
        WHERE shipment_id LIKE 'SHP-SIM-%'
        ORDER BY shipment_id
        """
    ).fetchall()

    assert [row["shipment_id"] for row in simulated] == [
        "SHP-SIM-0001",
        "SHP-SIM-0002",
    ]

    event_ids = connection.execute(
        """
        SELECT event_id
        FROM shipment_events
        WHERE event_id LIKE 'EVT-SIM-%'
        ORDER BY event_id
        """
    ).fetchall()

    assert [row["event_id"] for row in event_ids] == [
        "EVT-SIM-0001",
        "EVT-SIM-0002",
        "EVT-SIM-0003",
        "EVT-SIM-0004",
    ]

    # Baseline operational records are untouched.
    assert _count(connection, "shipments") == (
        baseline_shipments + 2
    )
    assert _count(connection, "exceptions") == (
        baseline_exceptions
    )


# ==================================================
# PIPELINE INTEGRATION
# ==================================================

def test_simulated_arrival_flows_through_operational_pipeline(
    seeded_database,
):
    """
    The key acceptance flow: a simulated arrival is detected
    and processed entirely by the existing operational
    pipeline, producing exactly one exception, three
    recovery options and one workflow action, all correctly
    linked by their real identities.
    """

    connection = seeded_database

    # Existing control-tower state: baseline fully processed.
    _establish_processed_baseline(connection)

    # Simulate one arrival.
    result = create_simulated_arrival(connection)

    # Refresh processes the arrival through the real
    # detection → options → actions pipeline.
    refresh = services.run_operational_refresh(connection)

    assert refresh["new_exceptions"] == 1
    assert refresh["new_options"] == 3
    assert refresh["new_actions"] == 1

    # The new exception belongs to the simulated shipment.
    exception_row = connection.execute(
        """
        SELECT exception_id, resolution_status
        FROM exceptions
        WHERE shipment_id = ?
        """,
        (result["shipment_id"],),
    ).fetchone()

    assert exception_row is not None
    assert exception_row["resolution_status"] == "Open"

    exception_id = exception_row["exception_id"]

    # The exception received exactly the three feasible
    # recovery options.
    option_rows = connection.execute(
        """
        SELECT option_id
        FROM recovery_options
        WHERE exception_id = ?
        ORDER BY option_id
        """,
        (exception_id,),
    ).fetchall()

    assert len(option_rows) == 3

    option_ids = {
        row["option_id"] for row in option_rows
    }

    # The workflow action for the exception carries one of
    # those option identities.
    action_row = connection.execute(
        """
        SELECT action_id, option_id, status
        FROM recovery_actions
        WHERE exception_id = ?
        """,
        (exception_id,),
    ).fetchone()

    assert action_row is not None
    assert action_row["option_id"] in option_ids
    assert action_row["status"] == "Pending Approval"


def test_refresh_without_new_arrival_is_steady_state(
    seeded_database,
):
    """
    After an arrival has been processed, refreshing again
    without another simulated arrival creates nothing: the
    incremental pipeline remains idempotent.
    """

    connection = seeded_database

    _establish_processed_baseline(connection)

    create_simulated_arrival(connection)

    first = services.run_operational_refresh(connection)

    assert first["new_exceptions"] == 1
    assert first["new_options"] == 3
    assert first["new_actions"] == 1

    second = services.run_operational_refresh(connection)

    assert second["new_exceptions"] == 0
    assert second["new_options"] == 0
    assert second["new_actions"] == 0


# ==================================================
# ATOMICITY
# ==================================================

def test_failed_event_insert_leaves_no_partial_arrival(
    seeded_database,
    monkeypatch,
):
    """
    A failure while recording the arrival's events rolls the
    whole arrival back: no half-created simulated shipment
    is left behind.
    """

    connection = seeded_database

    def failing_insert(connection, event_records):
        raise RuntimeError("event insert failed")

    monkeypatch.setattr(
        shipments_repo,
        "insert_shipment_events",
        failing_insert,
    )

    with pytest.raises(RuntimeError):
        create_simulated_arrival(connection)

    assert _count_simulated_shipments(connection) == 0

    # The connection is still usable after the rollback.
    assert _count(connection, "shipments") == 2
