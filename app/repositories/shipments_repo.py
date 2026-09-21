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


# ==================================================
# ARRIVAL SCENARIO READS
# ==================================================

def get_arrival_scenario_context(connection):
    """
    Return the deterministic baseline context for the
    controlled arrival scenario: the first shipment's
    order and carrier by order_id, with the order's
    required delivery date and the shipment's route.

    The arrival scenario derives its dates from this
    order's required delivery date so the simulated
    delay always lands on a real customer commitment.
    Returns None when no operational data exists.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            s.order_id,
            o.required_delivery_date,
            s.carrier_id,
            s.origin,
            s.destination
        FROM shipments s
        JOIN orders o
            ON s.order_id = o.order_id
        ORDER BY s.order_id
        LIMIT 1
        """
    )

    return cursor.fetchone()


def get_next_simulation_shipment_number(connection):
    """
    Determine the next simulation shipment number from
    existing SHP-SIM-% records.

    Keeps simulated arrival IDs deterministic and unique
    across repeated simulations, mirroring the option and
    exception numbering approach, without colliding with
    bootstrap shipment IDs.
    """

    cursor = connection.cursor()

    shipments = cursor.execute(
        """
        SELECT shipment_id
        FROM shipments
        WHERE shipment_id LIKE 'SHP-SIM-%'
        """
    ).fetchall()

    numbers = []

    for shipment in shipments:

        shipment_id = shipment["shipment_id"]

        try:
            number = int(
                shipment_id.replace("SHP-SIM-", "")
            )

            numbers.append(number)

        except ValueError:
            continue

    if not numbers:
        return 1

    return max(numbers) + 1


def get_max_simulation_event_number(connection):
    """
    Return the highest existing EVT-SIM-% event number,
    or 0 when none exist, so simulated event IDs continue
    the sequence across repeated arrivals.
    """

    cursor = connection.cursor()

    events = cursor.execute(
        """
        SELECT event_id
        FROM shipment_events
        WHERE event_id LIKE 'EVT-SIM-%'
        """
    ).fetchall()

    numbers = []

    for event in events:

        event_id = event["event_id"]

        try:
            number = int(
                event_id.replace("EVT-SIM-", "")
            )

            numbers.append(number)

        except ValueError:
            continue

    if not numbers:
        return 0

    return max(numbers)


# ==================================================
# ARRIVAL WRITES
# ==================================================

def insert_shipment(
    connection,
    shipment_record,
):
    """
    Insert one shipment record.

    No commit happens here: the caller owns the arrival
    transaction so shipment and events are created
    atomically.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO shipments (
            shipment_id, order_id, carrier_id, origin,
            destination, transport_mode, quantity, weight_kg,
            volume_m3, priority, planned_departure,
            actual_departure, planned_arrival,
            estimated_arrival, actual_arrival, status,
            shipping_cost, distance_km, current_location,
            last_updated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        shipment_record,
    )


def insert_shipment_events(
    connection,
    event_records,
):
    """
    Insert a batch of shipment event records.

    No commit happens here: the caller owns the arrival
    transaction so shipment and events are created
    atomically.
    """

    cursor = connection.cursor()

    cursor.executemany(
        """
        INSERT INTO shipment_events (
            event_id,
            shipment_id,
            event_type,
            event_timestamp,
            location,
            description
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        event_records,
    )


def get_shipment_emissions_inputs(
    connection,
    shipment_id,
):
    """
    Return the persisted physical inputs for the
    sustainability estimation of one shipment — its weight
    and route distance — or None when the shipment does not
    exist.

    Read-only projection of existing columns; no
    sustainability logic lives here.
    """

    cursor = connection.cursor()

    return cursor.execute(
        """
        SELECT
            weight_kg,
            distance_km
        FROM shipments
        WHERE shipment_id = ?
        """,
        (shipment_id,),
    ).fetchone()
