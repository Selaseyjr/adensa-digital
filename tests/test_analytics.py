"""
Analytics overview tests (P8.7.1, ADR-014).

These tests verify the analytical projection contract of
services.get_analytics_overview and the read-only
analytics_repo queries: seven honest datasets with their
analytical bases as contract metadata.

Honesty rules under test (the P8.7 discovery constraints):

- no invented history: empty/fresh databases produce empty
  series, never zero-filled synthetic months;
- zero denominators cannot produce rates (the None rate is
  the contract for a month/entry that cannot compute one);
- the incidence series is keyed on shipment DEPARTURE month,
  never on detection time (detection is a batch event);
- months where shipments departed but no exception occurred
  are explicit zeros, not absent points;
- recovery/resolution/detection-trend series do not exist.

All tests run on isolated temporary databases; the
development database is never touched.
"""

from pathlib import Path

import pytest

from app import services
from app.repositories import analytics_repo

from tests.conftest import seed_master_data


# ==================================================
# HELPERS
# ==================================================

def _insert_shipment(
    connection,
    shipment_id,
    *,
    planned_departure="2026-01-10",
    planned_arrival="2026-01-20",
    actual_arrival=None,
    status="Delivered",
    transport_mode="Road",
    carrier_id="CAR-900001",
):
    """
    Insert one shipment row on the shared fixture master data.
    actual_arrival None keeps the shipment undelivered-arrival
    (In Transit) unless status is given explicitly.
    """

    connection.execute(
        """
        INSERT INTO shipments (
            shipment_id, order_id, carrier_id, origin, destination,
            transport_mode, quantity, weight_kg, volume_m3, priority,
            planned_departure, actual_departure, planned_arrival,
            estimated_arrival, actual_arrival, status, shipping_cost,
            distance_km, current_location, last_updated
        )
        VALUES (
            ?, 'ORD-900001', ?, 'Rotterdam', 'Hamburg',
            ?, 10, 100, 1, 'Medium',
            ?, ?, ?, ?, ?, ?,
            100, 400, 'En route', '2026-09-10 12:00:00'
        )
        """,
        (
            shipment_id,
            carrier_id,
            transport_mode,
            planned_departure,
            planned_departure,
            planned_arrival,
            planned_arrival,
            actual_arrival,
            status,
        ),
    )


def _insert_exception(
    connection,
    exception_id,
    shipment_id,
    severity="Medium",
):
    """Insert one exception row against an existing shipment."""

    connection.execute(
        """
        INSERT INTO exceptions (
            exception_id, shipment_id, exception_type, severity,
            detected_at, description, estimated_impact,
            resolution_status, resolved_at
        )
        VALUES (
            ?, ?, 'Delivery Delay', ?,
            '2026-09-10 12:00:00', 'Fixture exception',
            'Estimated delivery delay of 1 day(s). Customer delivery commitment at risk.',
            'Open', NULL
        )
        """,
        (exception_id, shipment_id, severity),
    )


# ==================================================
# EMPTY / FRESH DATABASE — NO INVENTED HISTORY
# ==================================================

def test_empty_database_produces_empty_series(master_database):
    """
    A database with only master rows (no shipments, no
    exceptions) yields EMPTY series — the contract never
    fabricates months or zero-filled history.
    """

    overview = services.get_analytics_overview(master_database)

    assert overview["service_performance"]["points"] == []
    assert overview["exception_incidence"]["points"] == []
    assert overview["shipment_volume"]["points"] == []
    assert overview["transport"]["entries"] == []
    assert overview["carriers"]["entries"] == []
    assert overview["warehouses"]["entries"] == []
    assert overview["severity"]["entries"] == []


def test_every_dataset_carries_its_basis_even_when_empty(master_database):
    """
    The basis metadata is part of the contract and present
    even when the series itself is empty, so the frontend can
    always label the analytical question it would have asked.
    """

    overview = services.get_analytics_overview(master_database)

    assert overview["service_performance"]["basis"] == (
        "Delivered shipments by planned-arrival month"
    )
    assert overview["exception_incidence"]["basis"] == (
        "Exceptions by shipment departure month"
    )
    assert overview["shipment_volume"]["basis"] == (
        "All shipments by planned-departure month"
    )
    assert overview["transport"]["basis"] == (
        "Delivered shipments by transport mode"
    )
    assert overview["carriers"]["basis"] == (
        "Delivered shipments per carrier"
    )
    assert overview["warehouses"]["basis"] == (
        "Exceptions per origin warehouse"
    )
    assert overview["severity"]["basis"] == (
        "Open exceptions by severity (current snapshot)"
    )


# ==================================================
# SERVICE PERFORMANCE
# ==================================================

def test_service_performance_rate_and_month_basis(seeded_database):
    """
    On-time rate is computed per planned-arrival month over
    DELIVERED shipments only, with the counts preserved so
    the frontend can show the denominator.
    """

    connection = seeded_database

    # Jan: 3 delivered — 2 on time, 1 late.
    _insert_shipment(
        connection, "SHP-A1",
        planned_arrival="2026-01-20", actual_arrival="2026-01-19",
    )
    _insert_shipment(
        connection, "SHP-A2",
        planned_arrival="2026-01-25", actual_arrival="2026-01-25",
    )
    _insert_shipment(
        connection, "SHP-A3",
        planned_arrival="2026-01-30", actual_arrival="2026-02-02",
    )
    # Feb: 1 delivered, on time.
    _insert_shipment(
        connection, "SHP-B1",
        planned_arrival="2026-02-20", actual_arrival="2026-02-20",
    )
    # An undelivered shipment with an actual arrival (In
    # Transit) must be excluded from the delivered population.
    _insert_shipment(
        connection, "SHP-C1",
        status="In Transit",
        planned_arrival="2026-01-28", actual_arrival="2026-01-28",
    )
    connection.commit()

    points = analytics_repo.get_service_performance_by_month(connection)

    jan = next(p for p in points if p["month"] == "2026-01")
    feb = next(p for p in points if p["month"] == "2026-02")

    assert jan["delivered"] == 3
    assert jan["on_time"] == 2
    assert jan["on_time_rate"] == round(100.0 * 2 / 3, 1)

    assert feb["delivered"] == 1
    assert feb["on_time_rate"] == 100.0


def test_service_performance_excludes_shipments_without_actual_arrival(
    seeded_database,
):
    """
    Delivered status with no recorded actual arrival cannot be
    assessed for on-time performance — it stays out of both
    numerator and denominator.
    """

    connection = seeded_database

    _insert_shipment(
        connection, "SHP-D1",
        planned_arrival="2026-03-20", actual_arrival=None,
        status="Delivered",
    )
    connection.commit()

    points = analytics_repo.get_service_performance_by_month(connection)

    assert points == []


# ==================================================
# EXCEPTION INCIDENCE — DEPARTURE-MONTH BASIS
# ==================================================

def test_incidence_is_keyed_on_departure_month_not_detection(seeded_database):
    """
    The incidence time axis is the shipment's planned-departure
    month. Detection timestamps (a single batch event in the
    current data) never influence the grouping.
    """

    connection = seeded_database

    _insert_shipment(
        connection, "SHP-E1",
        planned_departure="2026-01-10", planned_arrival="2026-02-20",
        actual_arrival="2026-02-21",
    )
    _insert_shipment(
        connection, "SHP-E2",
        planned_departure="2026-01-15", planned_arrival="2026-02-25",
        actual_arrival="2026-02-26",
    )
    _insert_shipment(
        connection, "SHP-E3",
        planned_departure="2026-03-05", planned_arrival="2026-03-20",
        actual_arrival="2026-03-20",
    )
    _insert_exception(connection, "EXC-A1", "SHP-E1")
    _insert_exception(connection, "EXC-A2", "SHP-E2")
    _insert_exception(connection, "EXC-A3", "SHP-E3")
    connection.commit()

    points = analytics_repo.get_exception_incidence_by_month(connection)

    jan = next(p for p in points if p["month"] == "2026-01")
    mar = next(p for p in points if p["month"] == "2026-03")

    assert jan["departing"] == 2
    assert jan["exceptions"] == 2
    assert jan["incidence_rate"] == 100.0
    assert mar["incidence_rate"] == 100.0
    # Only months with departing shipments appear — the two
    # fixture shipments depart in 2026-09 and form the third
    # (baseline) month.
    assert [p["month"] for p in points] == [
        "2026-01", "2026-03", "2026-09",
    ]


def test_incidence_zero_exception_months_are_explicit_zeros(seeded_database):
    """
    A departure month with shipments but no exceptions is an
    explicit zero point, not an absent month — dropping it
    would visually fabricate activity.
    """

    connection = seeded_database

    _insert_shipment(
        connection, "SHP-F1",
        planned_departure="2026-01-10", planned_arrival="2026-01-20",
        actual_arrival="2026-01-20",
    )
    _insert_shipment(
        connection, "SHP-F2",
        planned_departure="2026-02-10", planned_arrival="2026-02-20",
        actual_arrival="2026-02-20",
    )
    _insert_exception(connection, "EXC-B1", "SHP-F2")
    connection.commit()

    points = analytics_repo.get_exception_incidence_by_month(connection)

    jan = next(p for p in points if p["month"] == "2026-01")

    assert jan["departing"] == 1
    assert jan["exceptions"] == 0
    assert jan["incidence_rate"] == 0.0


# ==================================================
# SHIPMENT VOLUME
# ==================================================

def test_shipment_volume_counts_all_shipments_by_departure_month(
    seeded_database,
):
    """
    Volume is the count of all recorded shipments per
    planned-departure month regardless of status.
    """

    connection = seeded_database

    _insert_shipment(
        connection, "SHP-G1", planned_departure="2026-01-05",
        status="Delivered", planned_arrival="2026-01-20",
        actual_arrival="2026-01-20",
    )
    _insert_shipment(
        connection, "SHP-G2", planned_departure="2026-01-18",
        status="In Transit", planned_arrival="2026-01-30",
    )
    _insert_shipment(
        connection, "SHP-G3", planned_departure="2026-02-02",
        status="Delayed", planned_arrival="2026-02-15",
    )
    connection.commit()

    points = analytics_repo.get_shipment_volume_by_month(connection)

    jan = next(p for p in points if p["month"] == "2026-01")
    feb = next(p for p in points if p["month"] == "2026-02")

    assert jan["shipments"] == 2
    assert feb["shipments"] == 1


# ==================================================
# CATEGORICAL READS
# ==================================================

def test_transport_and_carrier_performance_grouping(seeded_database):
    """
    Mode and carrier rates use the same delivered population;
    carriers carry their display names for the frontend.
    """

    connection = seeded_database

    _insert_shipment(
        connection, "SHP-H1", transport_mode="Road",
        planned_arrival="2026-01-20", actual_arrival="2026-01-20",
    )
    _insert_shipment(
        connection, "SHP-H2", transport_mode="Road",
        planned_arrival="2026-01-22", actual_arrival="2026-01-30",
    )
    _insert_shipment(
        connection, "SHP-H3", transport_mode="Sea",
        planned_arrival="2026-01-24", actual_arrival="2026-01-24",
    )
    connection.commit()

    transport = analytics_repo.get_transport_mode_performance(connection)

    road = next(e for e in transport if e["transport_mode"] == "Road")
    sea = next(e for e in transport if e["transport_mode"] == "Sea")

    assert road["delivered"] == 2
    assert road["on_time_rate"] == 50.0
    assert sea["on_time_rate"] == 100.0

    carriers = analytics_repo.get_carrier_performance(connection)

    fixture = next(
        e for e in carriers if e["carrier_id"] == "CAR-900001"
    )

    assert fixture["carrier_name"] == "Fixture Carrier"
    assert fixture["delivered"] == 3
    assert fixture["on_time"] == 2


def test_warehouse_distribution_uses_the_full_join_path(seeded_database):
    """
    Warehouse attribution follows exception → shipment →
    order → warehouse; warehouses with no exception-bearing
    shipments are absent.
    """

    connection = seeded_database

    _insert_shipment(
        connection, "SHP-I1",
        planned_arrival="2026-01-20", actual_arrival="2026-01-22",
    )
    _insert_shipment(
        connection, "SHP-I2",
        planned_arrival="2026-01-25", actual_arrival="2026-01-26",
    )
    _insert_exception(connection, "EXC-C1", "SHP-I1")
    _insert_exception(connection, "EXC-C2", "SHP-I1")
    _insert_exception(connection, "EXC-C3", "SHP-I2")
    connection.commit()

    entries = analytics_repo.get_exceptions_by_warehouse(connection)

    # All exception-bearing shipments route through the shared
    # fixture order/warehouse: 3 inserted + the 2 fixture
    # exceptions.
    assert len(entries) == 1
    assert entries[0]["warehouse_name"] == "Fixture Warehouse"
    assert entries[0]["exceptions"] == 5


def test_severity_composition_counts_only_open_exceptions(seeded_database):
    """
    The severity dataset is the open-population snapshot —
    resolved exceptions are excluded by construction.
    """

    connection = seeded_database

    _insert_shipment(
        connection, "SHP-J1",
        planned_arrival="2026-01-20", actual_arrival="2026-01-25",
    )
    _insert_exception(connection, "EXC-D1", "SHP-J1", severity="Critical")
    _insert_exception(connection, "EXC-D2", "SHP-J1", severity="Low")
    connection.execute(
        """
        UPDATE exceptions SET resolution_status = 'Resolved',
        resolved_at = '2026-09-11 12:00:00'
        WHERE exception_id = 'EXC-D2'
        """
    )
    connection.commit()

    entries = analytics_repo.get_severity_composition(connection)

    severities = {e["severity"]: e["exceptions"] for e in entries}

    # My Critical (open) plus the fixture baseline: EXC-900001
    # Low (open) and EXC-900002 High (open); my resolved Low is
    # excluded, and the fixture's Low remains.
    assert severities["Critical"] == 1
    assert severities["High"] == 1
    assert severities["Low"] == 1


# ==================================================
# SERVICE COMPOSITION / HONESTY GUARD
# ==================================================

def test_service_overview_has_exactly_the_seven_supported_datasets(
    seeded_database,
):
    """
    The projection exposes precisely the genuinely supported
    analytical datasets — no recovery-performance,
    resolution-performance or exception-detection-trend
    series may appear while the data cannot support them.
    """

    overview = services.get_analytics_overview(seeded_database)

    assert set(overview.keys()) == {
        "service_performance",
        "exception_incidence",
        "shipment_volume",
        "transport",
        "carriers",
        "warehouses",
        "severity",
    }


def test_service_overview_rows_are_plain_dictionaries(seeded_database):
    """
    No persistence-layer row object crosses the service
    boundary (ADR-011): every point/entry is an ordinary dict.
    """

    overview = services.get_analytics_overview(seeded_database)

    for key in (
        "service_performance", "exception_incidence",
        "shipment_volume",
    ):
        for point in overview[key]["points"]:
            assert type(point) is dict

    for key in ("transport", "carriers", "warehouses", "severity"):
        for entry in overview[key]["entries"]:
            assert type(entry) is dict


def test_analytics_sql_avoids_sqlite_only_date_functions():
    """
    The persistence layer does NOT translate SQLite date
    functions (app/pg_compat.py handles paramstyle, booleans
    and DDL types only), so a single date function in the
    analytics SQL would be silently SQLite-only and fail on
    PostgreSQL (ADR-014's cross-backend-by-construction
    requirement). The on-time classification compares the
    stored ISO date text directly — portable in both engines.

    This pins the property the P8.7.1 portability review
    verified: no backend-specific expression may appear in
    the analytics module, including in its documentation.
    """

    source = Path(analytics_repo.__file__).read_text(
        encoding="utf-8",
    )

    for token in (
        "julianday",
        "strftime",
        "date(",
        "datetime(",
    ):
        assert token not in source, token
