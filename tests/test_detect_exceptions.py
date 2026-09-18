"""
Regression tests for the exception-detection business rules
(app.detect_exceptions.detect_exceptions).

The detection module's rules under test:

- Rule 1 (delivery delay): an exception is created only when
  estimated_arrival is strictly later than the order's
  required_delivery_date.
- Severity ladder (delay_days = estimated - required):

      priority High  + delay >= 3  -> Critical
      priority High  (any delay)   -> High
      delay >= 5                   -> High
      delay >= 3                   -> Medium
      otherwise                    -> Low

- Exception IDs are assigned EXC-000001, EXC-000002, ... in
  shipment_id order (the repository read orders by shipment_id).
- Duplicate guard: detection runs only while the exceptions
  table is empty; any existing record suppresses the whole run.

Tests use isolated temporary databases (temp_database /
master_database / seeded_database fixtures) and never touch
data/adensa.db.
"""

import pytest

import app.detect_exceptions as detect_exceptions_module
from app.config import SIMULATION_TIMESTAMP
from app.detect_exceptions import detect_exceptions
from app.repositories import exceptions_repo


# --------------------------------------------------
# TEST HELPERS
# --------------------------------------------------

def insert_shipment(
    connection,
    shipment_id,
    priority,
    estimated_arrival,
    required_delivery_date,
    status="In Transit",
):
    """
    Insert one shipment whose order carries the given required
    delivery date. The shipment's own priority drives the
    severity ladder under test.
    """

    cursor = connection.cursor()

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
            ?, 'ORD-900001', 'CAR-900001', 'Rotterdam', 'Hamburg',
            'Road', 50, 200, 1, ?,
            '2026-09-12', '2026-09-12', ?, ?, NULL, ?, 200, 450,
            'En route', '2026-09-10 12:00:00'
        )
        """,
        (
            shipment_id,
            priority,
            estimated_arrival,
            estimated_arrival,
            status,
        ),
    )

    connection.commit()


def update_required_delivery_date(connection, required_delivery_date):
    """
    Point the fixture order's required delivery date at a
    test-controlled value.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE orders
        SET required_delivery_date = ?
        WHERE order_id = 'ORD-900001'
        """,
        (required_delivery_date,),
    )

    connection.commit()


def get_all_exceptions(connection):
    """
    Return every exception row in shipment_id order.
    """

    cursor = connection.cursor()

    return cursor.execute(
        """
        SELECT *
        FROM exceptions
        ORDER BY shipment_id
        """
    ).fetchall()


# --------------------------------------------------
# RULE 1 — DELIVERY DELAY
# --------------------------------------------------

def test_delayed_shipment_creates_exception_with_full_record(
    master_database,
    monkeypatch,
):
    """
    A late shipment produces exactly one exception with the
    full record contract: Delivery Delay type, Open status,
    simulation timestamp, description, and impact wording.
    """

    monkeypatch.setattr(
        detect_exceptions_module,
        "SIMULATION_TIMESTAMP",
        "2026-09-10 12:00:00",
    )

    update_required_delivery_date(master_database, "2026-09-15")
    insert_shipment(
        master_database,
        "SHP-900001",
        "High",
        "2026-09-18",  # 3 days late -> Critical (High priority)
        "2026-09-15",
    )

    detect_exceptions(master_database)

    exceptions = get_all_exceptions(master_database)

    assert len(exceptions) == 1

    record = exceptions[0]

    assert record["exception_id"] == "EXC-000001"
    assert record["shipment_id"] == "SHP-900001"
    assert record["exception_type"] == "Delivery Delay"
    assert record["severity"] == "Critical"
    assert record["detected_at"] == "2026-09-10 12:00:00"
    assert record["description"] == (
        "Estimated arrival 2026-09-18 is later than required "
        "delivery date 2026-09-15."
    )
    assert record["estimated_impact"] == (
        "Estimated delivery delay of 3 day(s). "
        "Customer delivery commitment at risk."
    )
    assert record["resolution_status"] == "Open"
    assert record["resolved_at"] is None


# --------------------------------------------------
# SEVERITY LADDER
# --------------------------------------------------

@pytest.mark.parametrize(
    (
        "priority",
        "estimated_arrival",
        "required_delivery_date",
        "expected_severity",
    ),
    [
        ("Low", "2026-09-16", "2026-09-15", "Low"),      # 1 day
        ("Medium", "2026-09-17", "2026-09-15", "Low"),   # 2 days
        ("Medium", "2026-09-18", "2026-09-15", "Medium"),  # 3 days
        ("Medium", "2026-09-20", "2026-09-15", "High"),  # 5 days
        ("Medium", "2026-09-25", "2026-09-15", "High"),  # 10 days
        ("High", "2026-09-17", "2026-09-15", "High"),    # 2 days
        ("High", "2026-09-18", "2026-09-15", "Critical"),  # 3 days
        ("High", "2026-09-25", "2026-09-15", "Critical"),  # 10 days
    ],
    ids=[
        "low-1-day",
        "medium-2-day-low",
        "medium-3-day-medium",
        "medium-5-day-high",
        "medium-10-day-high",
        "high-2-day-high",
        "high-3-day-critical",
        "high-10-day-critical",
    ],
)
def test_severity_ladder_boundaries(
    master_database,
    monkeypatch,
    priority,
    estimated_arrival,
    required_delivery_date,
    expected_severity,
):
    """
    One delayed shipment per case must produce the severity
    dictated by the priority/delay ladder.
    """

    monkeypatch.setattr(
        detect_exceptions_module,
        "SIMULATION_TIMESTAMP",
        SIMULATION_TIMESTAMP,
    )

    update_required_delivery_date(
        master_database,
        required_delivery_date,
    )
    insert_shipment(
        master_database,
        "SHP-900001",
        priority,
        estimated_arrival,
        required_delivery_date,
    )

    detect_exceptions(master_database)

    exceptions = get_all_exceptions(master_database)

    assert len(exceptions) == 1
    assert exceptions[0]["severity"] == expected_severity


# --------------------------------------------------
# BOUNDARY — STRICT DELAY COMPARISON
# --------------------------------------------------

@pytest.mark.parametrize(
    "estimated_arrival",
    [
        "2026-09-15",  # exactly on time
        "2026-09-14",  # early
    ],
    ids=["on-time", "early"],
)
def test_on_time_shipments_create_no_exceptions(
    master_database,
    monkeypatch,
    estimated_arrival,
):
    """
    The delay rule is strict: arrival equal to or before the
    required date never creates an exception.
    """

    monkeypatch.setattr(
        detect_exceptions_module,
        "SIMULATION_TIMESTAMP",
        SIMULATION_TIMESTAMP,
    )

    update_required_delivery_date(master_database, "2026-09-15")
    insert_shipment(
        master_database,
        "SHP-900001",
        "High",
        estimated_arrival,
        "2026-09-15",
    )

    detect_exceptions(master_database)

    assert get_all_exceptions(master_database) == []
    assert exceptions_repo.count_exceptions(master_database) == 0


# --------------------------------------------------
# EMPTY INPUT
# --------------------------------------------------

def test_no_shipments_creates_no_exceptions(temp_database):
    """
    A schema-only database (no shipments) is handled without
    error and without creating anything.
    """

    detect_exceptions(temp_database)

    assert exceptions_repo.count_exceptions(temp_database) == 0


# --------------------------------------------------
# EXCEPTION ID ASSIGNMENT
# --------------------------------------------------

def test_exception_ids_follow_shipment_order(
    master_database,
    monkeypatch,
):
    """
    IDs are assigned EXC-000001, EXC-000002, ... following the
    shipment_id ordering of the repository read, independent of
    the physical insert order.
    """

    monkeypatch.setattr(
        detect_exceptions_module,
        "SIMULATION_TIMESTAMP",
        SIMULATION_TIMESTAMP,
    )

    update_required_delivery_date(master_database, "2026-09-15")

    # Insert out of shipment_id order on purpose.
    insert_shipment(
        master_database,
        "SHP-900002",
        "Medium",
        "2026-09-16",  # 1 day -> Low
        "2026-09-15",
    )
    insert_shipment(
        master_database,
        "SHP-900001",
        "Medium",
        "2026-09-20",  # 5 days -> High
        "2026-09-15",
    )

    detect_exceptions(master_database)

    exceptions = get_all_exceptions(master_database)

    assert [
        (row["exception_id"], row["shipment_id"])
        for row in exceptions
    ] == [
        ("EXC-000001", "SHP-900001"),
        ("EXC-000002", "SHP-900002"),
    ]


# --------------------------------------------------
# DUPLICATE GUARD
# --------------------------------------------------

def test_existing_exceptions_suppress_detection(seeded_database):
    """
    Any pre-existing exception record disables the whole
    detection run: newly delayed shipments must NOT create
    further exceptions.
    """

    assert exceptions_repo.count_exceptions(seeded_database) == 2

    update_required_delivery_date(seeded_database, "2026-09-15")
    insert_shipment(
        seeded_database,
        "SHP-900003",
        "High",
        "2026-09-25",  # 10 days late
        "2026-09-15",
    )

    detect_exceptions(seeded_database)

    exceptions = get_all_exceptions(seeded_database)

    assert len(exceptions) == 2
    assert exceptions_repo.count_exceptions(seeded_database) == 2
    assert all(
        row["exception_type"] != "Delivery Delay"
        for row in exceptions
    )


def test_second_run_is_idempotent(master_database, monkeypatch):
    """
    Running detection twice after a productive first run must
    not duplicate the created records.
    """

    monkeypatch.setattr(
        detect_exceptions_module,
        "SIMULATION_TIMESTAMP",
        SIMULATION_TIMESTAMP,
    )

    update_required_delivery_date(master_database, "2026-09-15")
    insert_shipment(
        master_database,
        "SHP-900001",
        "Medium",
        "2026-09-18",
        "2026-09-15",
    )

    detect_exceptions(master_database)
    detect_exceptions(master_database)

    assert exceptions_repo.count_exceptions(master_database) == 1
