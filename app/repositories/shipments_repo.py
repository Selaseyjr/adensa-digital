"""
Data access for the shipments and shipment_events tables.

All SQL is moved verbatim from the modules that previously
owned it (the UI in app/main.py and the detection module
app/detect_exceptions.py).

Every function accepts an existing sqlite connection and
never commits: transaction boundaries stay with the caller.
"""

# ==================================================
# QUERIES
# ==================================================

def get_shipments_with_required_delivery(connection):
    """
    Return all shipments with their order's required
    delivery date, ordered by shipment_id.

    Moved verbatim from the detection module's
    operational read in app/detect_exceptions.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            s.shipment_id,
            s.planned_arrival,
            s.estimated_arrival,
            s.status,
            s.priority,
            o.required_delivery_date
        FROM shipments s
        JOIN orders o
            ON s.order_id = o.order_id
        ORDER BY s.shipment_id
        """
    )

    return cursor.fetchall()


def get_shipment_transport_mode_and_carrier(
    connection,
    shipment_id,
):
    """
    Return the transport mode and carrier of a shipment,
    or None when the shipment does not exist.

    Moved verbatim from the UI pre-execution read
    in app/main.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            transport_mode,
            carrier_id
        FROM shipments
        WHERE shipment_id = ?
        """,
        (shipment_id,),
    )

    return cursor.fetchone()


def get_shipment_delivery_state(
    connection,
    shipment_id,
):
    """
    Return the transport mode, carrier and estimated
    arrival of a shipment, or None when the shipment does
    not exist.

    Moved verbatim from the UI post-execution read
    in app/main.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            transport_mode,
            carrier_id,
            estimated_arrival
        FROM shipments
        WHERE shipment_id = ?
        """,
        (shipment_id,),
    )

    return cursor.fetchone()


def get_latest_recovery_event_id(
    connection,
    shipment_id,
):
    """
    Return the most recent recovery-execution event ID for
    a shipment, or None when no such event exists.

    Moved verbatim from the UI execution-outcome read
    in app/main.py.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT event_id
        FROM shipment_events
        WHERE shipment_id = ?
        AND event_type = 'Recovery Executed'
        ORDER BY event_timestamp DESC
        LIMIT 1
        """,
        (shipment_id,),
    )

    return cursor.fetchone()
