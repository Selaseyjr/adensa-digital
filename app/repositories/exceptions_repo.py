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


def count_open_follow_up_required(connection):
    """
    Count open exceptions whose latest recovery action has
    been EXECUTED — system recovery has been attempted but
    the exception is still open, so planner follow-up is
    required (Checkpoint S).

    Full-population read over the open exceptions, matching
    the population of count_open_exceptions: the inbox cap
    is deliberately not involved.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM exceptions e
        WHERE e.resolution_status = 'Open'
          AND EXISTS (
              SELECT 1
              FROM recovery_actions ra
              WHERE ra.exception_id = e.exception_id
                AND ra.status = 'Executed'
          )
        """
    )

    return cursor.fetchone()[0]


def get_follow_up_required_exceptions(
    connection,
    limit,
):
    """
    Return the open exceptions that require planner
    follow-up, newest detection first, up to the supplied
    limit.

    Follow-up rule (Checkpoint S): an open exception whose
    latest recovery action has been executed. The execution
    has already happened and did not resolve the exception,
    so renewed planner attention is required. The reason
    details are projected from the same persisted evidence:
    the recorded estimated arrival against the required
    delivery date, plus the action's execution timestamp.

    Read-only; resolves no state and invents nothing.
    """

    cursor = connection.cursor()

    exceptions = cursor.execute(
        """
        SELECT
            e.exception_id,
            e.severity,
            e.exception_type,
            e.detected_at,
            ra.action_id,
            ra.executed_at,
            s.estimated_arrival,
            s.shipment_id,
            o.required_delivery_date,
            (
                SELECT COUNT(*)
                FROM recovery_options ro
                WHERE ro.exception_id = e.exception_id
                  AND ro.feasible = 1
            ) AS feasible_option_count
        FROM exceptions e
        JOIN shipments s
            ON e.shipment_id = s.shipment_id
        JOIN orders o
            ON s.order_id = o.order_id
        JOIN recovery_actions ra
            ON ra.exception_id = e.exception_id
            AND ra.status = 'Executed'
        WHERE e.resolution_status = 'Open'
        ORDER BY
            e.detected_at DESC,
            e.exception_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return exceptions


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
    shipment and order context, ordered by operational
    priority:

    1. actionable exceptions first (exceptions that have at
       least one feasible recovery option — the work a
       planner can act on now);
    2. most recently detected first;
    3. exception_id descending as the deterministic
       tie-break, which also orders records that share a
       detection timestamp by creation sequence — so the
       newest detected exception surfaces at the top of
       the actionable queue.

    Severity is rendered on every inbox row (triage
    labels) but does not gate queue position: with the
    bounded row cap, severity-first ordering buried newly
    detected actionable exceptions behind severity buckets
    larger than the cap itself (the bootstrap dataset
    holds 271 open Critical exceptions), making new
    operational work undiscoverable. The queue now
    surfaces the newest actionable work first; severity
    remains visible for triage and in the control-tower
    counts.

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
            o.required_delivery_date,
            (
                SELECT COUNT(*)
                FROM recovery_options ro
                WHERE ro.exception_id = e.exception_id
                  AND ro.feasible = 1
            ) AS feasible_option_count,
            (
                SELECT ra.status
                FROM recovery_actions ra
                WHERE ra.exception_id = e.exception_id
                  AND ra.status = 'Executed'
                LIMIT 1
            ) IS NOT NULL AS executed_still_open
        FROM exceptions e
        JOIN shipments s
            ON e.shipment_id = s.shipment_id
        JOIN orders o
            ON s.order_id = o.order_id
        WHERE e.resolution_status = 'Open'
        ORDER BY
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM recovery_options ro
                    WHERE ro.exception_id = e.exception_id
                      AND ro.feasible = 1
                ) THEN 0
                ELSE 1
            END,
            e.detected_at DESC,
            e.exception_id DESC
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
# OPERATIONAL CONTEXT READS (shared by engines)
# ==================================================

def get_exception_operational_context(
    connection,
    exception_id,
):
    """
    Return the exception's operational context row with its
    shipment and order fields, or None when the exception
    does not exist.

    Consolidates the exception → shipment → order context
    reads previously duplicated by the decision engine and
    the execution engine. Missing-record handling stays with
    the calling engine.
    """

    cursor = connection.cursor()

    exception = cursor.execute(
        """
        SELECT
            e.exception_id,
            e.shipment_id,
            e.exception_type,
            e.severity,
            e.resolution_status,
            e.description,

            s.order_id,
            s.transport_mode,
            s.carrier_id,
            s.planned_departure,
            s.estimated_arrival,
            s.status AS shipment_status,

            o.required_delivery_date,

            s.priority,

            s.origin,
            s.destination,

            o.customer_id,
            c.customer_name

        FROM exceptions e

        JOIN shipments s
            ON e.shipment_id = s.shipment_id

        JOIN orders o
            ON s.order_id = o.order_id

        JOIN customers c
            ON o.customer_id = c.customer_id

        WHERE e.exception_id = ?
        """,
        (exception_id,),
    ).fetchone()

    return exception


def get_latest_exception_ids(
    connection,
    limit,
):
    """
    Return the most recently numbered exception IDs,
    ordered from newest to oldest, up to the given limit.

    Used by the operational refresh to report which
    exceptions a processing run has just detected.
    """

    cursor = connection.cursor()

    rows = cursor.execute(
        """
        SELECT exception_id
        FROM exceptions
        ORDER BY exception_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [row["exception_id"] for row in rows]


def get_open_exception_contexts(connection):
    """
    Return the operational context of all open exceptions,
    ordered by exception_id.

    Moved verbatim from the generator's open-exception
    context read in app/generate_recovery_options.py.
    Severity filtering and option generation stay with the
    generator.
    """

    cursor = connection.cursor()

    exceptions = cursor.execute(
        """
        SELECT
            e.exception_id,
            e.shipment_id,
            e.exception_type,
            e.severity,
            e.description,

            s.origin,
            s.destination,
            s.transport_mode,
            s.quantity,
            s.weight_kg,
            s.distance_km,
            s.priority,
            s.estimated_arrival,

            o.required_delivery_date

        FROM exceptions e

        JOIN shipments s
            ON e.shipment_id = s.shipment_id

        JOIN orders o
            ON s.order_id = o.order_id

        WHERE e.resolution_status = 'Open'

        ORDER BY e.exception_id
        """
    ).fetchall()

    return exceptions


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


def mark_exception_resolved(
    connection,
    exception_id,
    resolved_at,
):
    """
    Mark an open exception as Resolved and stamp the
    resolution time.

    The WHERE clause restricts the update to currently open
    exceptions, mirroring the execution engine's resolution
    update; the caller owns the transaction so this write
    commits together with its intervention record.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE exceptions
        SET
            resolution_status = 'Resolved',
            resolved_at = ?
        WHERE exception_id = ?
          AND resolution_status = 'Open'
        """,
        (
            resolved_at,
            exception_id,
        ),
    )

    return cursor.rowcount


def get_open_exception_ids(connection):
    """
    Return the IDs of all open exceptions ordered by
    exception_id.

    Moved verbatim from the open-exception iteration read
    previously embedded in decision_engine.run_decision_engine.
    """

    cursor = connection.cursor()

    return cursor.execute(
        """
        SELECT exception_id
        FROM exceptions
        WHERE resolution_status = 'Open'
        ORDER BY exception_id
        """
    ).fetchall()


def get_shipment_ids_with_exceptions(connection):
    """
    Return the set of shipment IDs that are already
    represented by an exception.

    Entity-level idempotency read for the detection
    module: shipments in this set are skipped on
    repeated detection runs, so newly arrived shipments
    can be processed on an already-populated database
    without duplicating exceptions.
    """

    cursor = connection.cursor()

    rows = cursor.execute(
        """
        SELECT DISTINCT shipment_id
        FROM exceptions
        """
    ).fetchall()

    return {row["shipment_id"] for row in rows}


def get_next_exception_number(connection):
    """
    Determine the next exception number from the existing
    database records.

    This keeps exception IDs deterministic and unique
    across repeated detection runs, mirroring the
    option-ID approach in the recovery-options
    repository, so detection can continue numbering on a
    populated database without primary-key collisions.
    """

    cursor = connection.cursor()

    exceptions = cursor.execute(
        """
        SELECT exception_id
        FROM exceptions
        WHERE exception_id LIKE 'EXC-%'
        """
    ).fetchall()

    numbers = []

    for exception in exceptions:

        exception_id = exception["exception_id"]

        try:
            number = int(
                exception_id.replace("EXC-", "")
            )

            numbers.append(number)

        except ValueError:
            continue

    if not numbers:
        return 1

    return max(numbers) + 1


def get_recently_resolved_exceptions(
    connection,
    limit,
):
    """
    Return the most recently resolved exceptions, newest
    resolution first, up to the supplied limit.

    Additive read over the existing resolution fields: no
    schema knowledge beyond the exceptions table, no new
    business rules, read-only.
    """

    cursor = connection.cursor()

    exceptions = cursor.execute(
        """
        SELECT
            exception_id,
            exception_type,
            severity,
            resolution_status,
            resolved_at
        FROM exceptions
        WHERE resolution_status = 'Resolved'
        ORDER BY resolved_at DESC, exception_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return exceptions


def get_exception_lifecycle(
    connection,
    exception_id,
):
    """
    Return an exception's lifecycle fields — detection
    details and current resolution state — or None when the
    exception does not exist.

    Used for the operational history.
    """

    cursor = connection.cursor()

    exception = cursor.execute(
        """
        SELECT
            e.exception_id,
            e.shipment_id,
            e.exception_type,
            e.severity,
            e.description,
            e.estimated_impact,
            e.detected_at,
            e.resolution_status,
            e.resolved_at,

            s.estimated_arrival,
            o.required_delivery_date
        FROM exceptions e

        JOIN shipments s
            ON e.shipment_id = s.shipment_id

        JOIN orders o
            ON s.order_id = o.order_id

        WHERE e.exception_id = ?
        """,
        (exception_id,),
    ).fetchone()

    return exception
