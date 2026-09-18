"""
Data access for the exceptions table.

All SQL is moved verbatim from the modules that previously
owned it (the UI in app/main.py and the detection module
app/detect_exceptions.py).

Every function accepts an existing sqlite connection and
never commits: transaction boundaries stay with the caller.
"""

# ==================================================
# QUERIES
# ==================================================

def count_exceptions(connection):
    """
    Count all exception records.

    Moved verbatim from the detection module's
    existing-data guard in app/detect_exceptions.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM exceptions
        """
    )

    return cursor.fetchone()[0]


def count_open_exceptions(connection):
    """
    Count open exceptions.

    Moved verbatim from the UI KPI query
    in app/main.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM exceptions
        WHERE resolution_status = 'Open'
        """
    )

    return cursor.fetchone()[0]


def count_open_critical_exceptions(connection):
    """
    Count open exceptions with Critical severity.

    Moved verbatim from the UI KPI query
    in app/main.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM exceptions
        WHERE resolution_status = 'Open'
        AND severity = 'Critical'
        """
    )

    return cursor.fetchone()[0]


def get_open_exceptions_inbox(connection):
    """
    Return the open exceptions for the UI inbox with their
    shipment and order context, ordered by severity rank
    and detection time.

    Moved verbatim from the UI inbox query
    in app/main.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            e.exception_id,
            e.shipment_id,
            e.exception_type,
            e.severity,
            e.estimated_impact,
            e.resolution_status,
            s.transport_mode,
            s.current_location,
            s.estimated_arrival,
            o.priority,
            o.required_delivery_date
        FROM exceptions e
        JOIN shipments s
            ON e.shipment_id = s.shipment_id
        JOIN orders o
            ON s.order_id = o.order_id
        WHERE e.resolution_status = 'Open'
        ORDER BY
            CASE e.severity
                WHEN 'Critical' THEN 1
                WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3
                WHEN 'Low' THEN 4
                ELSE 5
            END,
            e.detected_at
        LIMIT 100
        """
    )

    return cursor.fetchall()


def get_exception_resolution_status(
    connection,
    exception_id,
):
    """
    Return the resolution status of an exception, or None
    when the exception does not exist.

    Moved verbatim from the UI execution-outcome read
    in app/main.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT resolution_status
        FROM exceptions
        WHERE exception_id = ?
        """,
        (exception_id,),
    )

    return cursor.fetchone()


# ==================================================
# WRITES
# ==================================================

def insert_exceptions(
    connection,
    exception_records,
):
    """
    Insert a batch of exception records and return the
    number of rows inserted.

    Moved verbatim from the detection module
    in app/detect_exceptions.py. The caller owns the
    transaction: no commit happens here.
    """

    cursor = connection.cursor()

    cursor.executemany(
        """
        INSERT INTO exceptions (
            exception_id,
            shipment_id,
            exception_type,
            severity,
            detected_at,
            description,
            estimated_impact,
            resolution_status,
            resolved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        exception_records,
    )

    return cursor.rowcount
