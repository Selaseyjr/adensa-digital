"""
Data access for the analytical visualization layer (ADR-014).

Read-only aggregate queries for the /v1/analytics/overview
projection. Analytics introduces no new tables and no new
business rules: every query aggregates recorded operational
data that already exists, and each result carries the metadata
the frontend needs to state its analytical basis honestly
(the discovery report's honesty rules — no metric is exposed
without its true population and time basis).

Dialect constraints: the SQL uses only constructs the shared
persistence layer serves to both backends unchanged (plain
aggregates, GROUP BY, CASE, substr, and ISO-text date
comparison — actual_arrival <= planned_arrival compares the
stored YYYY-MM-DD strings lexicographically under both SQLite
and PostgreSQL; no SQLite date function appears anywhere —
see app/pg_compat.py's single-SQL-source-of-truth principle).
Repositories never commit and contain no business rules; every
function accepts an existing connection and returns plain
dictionaries so no persistence-layer row type reaches the
service boundary (ADR-011).
"""

# ==================================================
# TIME-SERIES READS
# ==================================================

def get_service_performance_by_month(connection):
    """
    On-time delivery percentage by planned-arrival month,
    over DELIVERED shipments with a recorded actual arrival.

    Basis: the planned_arrival month of delivered shipments.
    A shipment is on time when actual_arrival <= planned_arrival.
    Months are returned only when delivered records exist —
    empty months are not fabricated (the frontend labels each
    point with its delivered count).
    """

    rows = connection.execute(
        """
        SELECT substr(planned_arrival, 1, 7) AS month,
               COUNT(*) AS delivered,
               SUM(CASE
                       WHEN actual_arrival <= planned_arrival
                       THEN 1 ELSE 0
                   END) AS on_time
        FROM shipments
        WHERE status = 'Delivered'
          AND actual_arrival IS NOT NULL
          AND planned_arrival IS NOT NULL
        GROUP BY month
        ORDER BY month
        """
    ).fetchall()

    points = []

    for row in rows:
        delivered = row["delivered"]
        on_time = row["on_time"]

        points.append(
            {
                "month": row["month"],
                "delivered": delivered,
                "on_time": on_time,
                # Zero denominator is structurally impossible
                # inside a month group (every grouped row has at
                # least one delivered shipment), but the guard
                # keeps the arithmetic total.
                "on_time_rate": (
                    round(100.0 * on_time / delivered, 1)
                    if delivered > 0
                    else None
                ),
            }
        )

    return points


def get_shipment_volume_by_month(connection):
    """
    Shipment activity by planned-departure month — all
    recorded shipments, no status filter (the volume of the
    network's planned activity).
    """

    rows = connection.execute(
        """
        SELECT substr(planned_departure, 1, 7) AS month,
               COUNT(*) AS shipments
        FROM shipments
        WHERE planned_departure IS NOT NULL
        GROUP BY month
        ORDER BY month
        """
    ).fetchall()

    return [
        {
            "month": row["month"],
            "shipments": row["shipments"],
        }
        for row in rows
    ]


def get_exception_incidence_by_month(connection):
    """
    Departure-month incidence: exceptions relative to the
    shipments departing in each planned-departure month.

    This is deliberately NOT exception detection over time —
    detection is a batch operational event, so the honest
    time axis is the shipment's planned departure month.
    Both series derive from the same join and the same month
    axis; months where shipments departed but no exception
    occurred are explicitly zero, not absent.
    """

    rows = connection.execute(
        """
        SELECT substr(s.planned_departure, 1, 7) AS month,
               COUNT(DISTINCT s.shipment_id) AS departing,
               COUNT(DISTINCT e.exception_id) AS exceptions
        FROM shipments s
        LEFT JOIN exceptions e
            ON e.shipment_id = s.shipment_id
        WHERE s.planned_departure IS NOT NULL
        GROUP BY month
        ORDER BY month
        """
    ).fetchall()

    points = []

    for row in rows:
        departing = row["departing"]
        exceptions = row["exceptions"]

        points.append(
            {
                "month": row["month"],
                "departing": departing,
                "exceptions": exceptions,
                "incidence_rate": (
                    round(100.0 * exceptions / departing, 1)
                    if departing > 0
                    else None
                ),
            }
        )

    return points


# ==================================================
# CATEGORICAL READS
# ==================================================

def get_transport_mode_performance(connection):
    """
    On-time delivery percentage by transport mode over the
    same delivered population as the service-performance
    series (delivered shipments with recorded actual arrivals).
    """

    rows = connection.execute(
        """
        SELECT transport_mode,
               COUNT(*) AS delivered,
               SUM(CASE
                       WHEN actual_arrival <= planned_arrival
                       THEN 1 ELSE 0
                   END) AS on_time
        FROM shipments
        WHERE status = 'Delivered'
          AND actual_arrival IS NOT NULL
          AND planned_arrival IS NOT NULL
        GROUP BY transport_mode
        ORDER BY delivered DESC, transport_mode
        """
    ).fetchall()

    entries = []

    for row in rows:
        delivered = row["delivered"]

        entries.append(
            {
                "transport_mode": row["transport_mode"],
                "delivered": delivered,
                "on_time": row["on_time"],
                "on_time_rate": (
                    round(100.0 * row["on_time"] / delivered, 1)
                    if delivered > 0
                    else None
                ),
            }
        )

    return entries


def get_carrier_performance(connection):
    """
    On-time delivery percentage per carrier over the delivered
    population, with the carrier's display name from the
    carriers table.
    """

    rows = connection.execute(
        """
        SELECT c.carrier_id,
               c.carrier_name,
               COUNT(*) AS delivered,
               SUM(CASE
                       WHEN s.actual_arrival <= s.planned_arrival
                       THEN 1 ELSE 0
                   END) AS on_time
        FROM shipments s
        JOIN carriers c ON c.carrier_id = s.carrier_id
        WHERE s.status = 'Delivered'
          AND s.actual_arrival IS NOT NULL
          AND s.planned_arrival IS NOT NULL
        GROUP BY c.carrier_id, c.carrier_name
        ORDER BY delivered DESC, c.carrier_name
        """
    ).fetchall()

    entries = []

    for row in rows:
        delivered = row["delivered"]

        entries.append(
            {
                "carrier_id": row["carrier_id"],
                "carrier_name": row["carrier_name"],
                "delivered": delivered,
                "on_time": row["on_time"],
                "on_time_rate": (
                    round(100.0 * row["on_time"] / delivered, 1)
                    if delivered > 0
                    else None
                ),
            }
        )

    return entries


def get_exceptions_by_warehouse(connection):
    """
    Exception count per warehouse — the origin distribution
    along the exception → shipment → order → warehouse join.
    Warehouses with no exception-bearing shipments are absent
    (the count is over recorded exceptions, not capacity).
    """

    rows = connection.execute(
        """
        SELECT w.warehouse_id,
               w.warehouse_name,
               COUNT(e.exception_id) AS exceptions
        FROM exceptions e
        JOIN shipments s ON s.shipment_id = e.shipment_id
        JOIN orders o ON o.order_id = s.order_id
        JOIN warehouses w ON w.warehouse_id = o.warehouse_id
        GROUP BY w.warehouse_id, w.warehouse_name
        ORDER BY exceptions DESC, w.warehouse_name
        """
    ).fetchall()

    return [
        {
            "warehouse_id": row["warehouse_id"],
            "warehouse_name": row["warehouse_name"],
            "exceptions": row["exceptions"],
        }
        for row in rows
    ]


def get_severity_composition(connection):
    """
    Current severity composition of the OPEN exception
    population — the workflow snapshot, not a time series.
    """

    rows = connection.execute(
        """
        SELECT severity, COUNT(*) AS exceptions
        FROM exceptions
        WHERE resolution_status = 'Open'
        GROUP BY severity
        ORDER BY exceptions DESC, severity
        """
    ).fetchall()

    return [
        {
            "severity": row["severity"],
            "exceptions": row["exceptions"],
        }
        for row in rows
    ]
