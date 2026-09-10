from datetime import datetime, timedelta

from app.config import (
    RECOVERY_EXECUTION_OFFSET_DAYS,
)
from app.database import get_connection
from app.workflow_engine import (
    APPROVED,
    EXECUTED,
    validate_transition,
)


# ==================================================
# DETERMINE RECOVERY EXECUTION TIME
# ==================================================

def calculate_execution_time(planned_departure):
    """
    Calculate the simulated recovery execution time.

    Adensa Digital uses a controlled simulation timeline
    rather than the computer's actual current date.

    Recovery execution occurs a configurable number of
    days after the original planned departure.
    """

    departure_date = datetime.strptime(
        planned_departure,
        "%Y-%m-%d",
    )

    execution_date = (
        departure_date
        + timedelta(
            days=RECOVERY_EXECUTION_OFFSET_DAYS
        )
    )

    return execution_date


# ==================================================
# EXECUTE RECOVERY ACTION
# ==================================================

def execute_recovery_action(
    connection,
    action_id,
):
    """
    Execute an approved recovery action.

    Valid transition:

        Approved → Executed

    The function also updates the shipment, records a
    recovery event, and evaluates whether the exception
    has actually been resolved.

    Important:

        Executed ≠ Resolved

    A recovery action may execute successfully while the
    shipment still fails to meet the required delivery date.
    """

    cursor = connection.cursor()

    # --------------------------------------------------
    # 1. GET RECOVERY ACTION
    # --------------------------------------------------

    action = cursor.execute(
        """
        SELECT
            action_id,
            exception_id,
            option_id,
            status
        FROM recovery_actions
        WHERE action_id = ?
        """,
        (action_id,),
    ).fetchone()

    if action is None:
        raise ValueError(
            f"Action {action_id} not found."
        )

    # --------------------------------------------------
    # 2. VALIDATE WORKFLOW TRANSITION
    # --------------------------------------------------
    #
    # This prevents:
    #
    # Pending Approval → Executed
    # Executed → Executed
    # Rejected → Executed
    #
    # Only:
    #
    # Approved → Executed
    #
    # is permitted.
    #

    validate_transition(
        action["status"],
        EXECUTED,
    )

    # --------------------------------------------------
    # 3. GET RECOVERY OPTION
    # --------------------------------------------------

    option = cursor.execute(
        """
        SELECT
            option_id,
            exception_id,
            transport_mode,
            carrier_id,
            estimated_cost,
            estimated_transit_days,
            risk_score
        FROM recovery_options
        WHERE option_id = ?
        """,
        (action["option_id"],),
    ).fetchone()

    if option is None:
        raise ValueError(
            f"Recovery option {action['option_id']} "
            f"not found."
        )

    # --------------------------------------------------
    # 4. VERIFY OPTION BELONGS TO EXCEPTION
    # --------------------------------------------------

    if option["exception_id"] != action["exception_id"]:
        raise ValueError(
            f"Recovery option {action['option_id']} "
            f"does not belong to exception "
            f"{action['exception_id']}."
        )

    # --------------------------------------------------
    # 5. GET EXCEPTION + SHIPMENT + ORDER
    # --------------------------------------------------

    exception = cursor.execute(
        """
        SELECT
            e.exception_id,
            e.shipment_id,
            e.exception_type,
            e.severity,
            e.resolution_status,

            s.order_id,
            s.transport_mode,
            s.carrier_id,
            s.planned_departure,
            s.estimated_arrival,
            s.status AS shipment_status,

            o.required_delivery_date

        FROM exceptions e

        JOIN shipments s
            ON e.shipment_id = s.shipment_id

        JOIN orders o
            ON s.order_id = o.order_id

        WHERE e.exception_id = ?
        """,
        (action["exception_id"],),
    ).fetchone()

    if exception is None:
        raise ValueError(
            f"Exception {action['exception_id']} "
            f"not found."
        )

    # --------------------------------------------------
    # 6. VERIFY EXCEPTION IS STILL OPEN
    # --------------------------------------------------

    if exception["resolution_status"] != "Open":
        raise ValueError(
            f"Action {action_id} cannot be executed "
            f"because exception "
            f"{action['exception_id']} is already "
            f"{exception['resolution_status']}."
        )

    # --------------------------------------------------
    # 7. CALCULATE SIMULATED EXECUTION TIME
    # --------------------------------------------------

    execution_datetime = calculate_execution_time(
        exception["planned_departure"]
    )

    executed_at = execution_datetime.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # --------------------------------------------------
    # 8. CALCULATE NEW ESTIMATED ARRIVAL
    # --------------------------------------------------

    recovery_transit_days = float(
        option["estimated_transit_days"]
    )

    new_estimated_arrival = (
        execution_datetime
        + timedelta(
            days=recovery_transit_days
        )
    )

    new_estimated_arrival_date = (
        new_estimated_arrival.strftime(
            "%Y-%m-%d"
        )
    )

    # --------------------------------------------------
    # 9. UPDATE SHIPMENT
    # --------------------------------------------------

    shipment_update = cursor.execute(
        """
        UPDATE shipments
        SET
            transport_mode = ?,
            carrier_id = ?,
            estimated_arrival = ?,
            last_updated = ?
        WHERE shipment_id = ?
        """,
        (
            option["transport_mode"],
            option["carrier_id"],
            new_estimated_arrival_date,
            executed_at,
            exception["shipment_id"],
        ),
    )

    if shipment_update.rowcount != 1:
        raise ValueError(
            f"Shipment update failed for "
            f"{exception['shipment_id']}."
        )

    # --------------------------------------------------
    # 10. CREATE RECOVERY SHIPMENT EVENT
    # --------------------------------------------------

    event_id = (
        f"EVT-REC-{action_id.replace('ACT-', '')}"
    )

    # Defensive check against duplicate event creation.
    existing_event = cursor.execute(
        """
        SELECT event_id
        FROM shipment_events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()

    if existing_event is not None:
        raise ValueError(
            f"Recovery event {event_id} already exists. "
            f"Action {action_id} may already have been executed."
        )

    cursor.execute(
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
        (
            event_id,
            exception["shipment_id"],
            "Recovery Executed",
            executed_at,
            "Network",
            (
                f"Recovery action {action_id} executed. "
                f"Shipment switched to "
                f"{option['transport_mode']} using carrier "
                f"{option['carrier_id']}. "
                f"New estimated arrival: "
                f"{new_estimated_arrival_date}."
            ),
        ),
    )

    # --------------------------------------------------
    # 11. MARK ACTION AS EXECUTED
    # --------------------------------------------------

    action_update = cursor.execute(
        """
        UPDATE recovery_actions
        SET
            status = ?,
            executed_at = ?
        WHERE action_id = ?
          AND status = ?
        """,
        (
            EXECUTED,
            executed_at,
            action_id,
            APPROVED,
        ),
    )

    if action_update.rowcount != 1:
        raise ValueError(
            f"Action {action_id} could not be marked "
            f"as Executed."
        )

    # --------------------------------------------------
    # 12. DETERMINE EXCEPTION RESOLUTION
    # --------------------------------------------------

    required_delivery_date = datetime.strptime(
        exception["required_delivery_date"],
        "%Y-%m-%d",
    )

    if new_estimated_arrival <= required_delivery_date:

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
                executed_at,
                action["exception_id"],
            ),
        )

        resolution_message = "Resolved"

    else:

        resolution_message = "Still Open"

    # --------------------------------------------------
    # 13. COMMIT TRANSACTION
    # --------------------------------------------------

    connection.commit()

    # --------------------------------------------------
    # 14. DISPLAY EXECUTION RESULT
    # --------------------------------------------------

    print("\nRecovery Execution")
    print("=" * 50)

    print(
        f"Action: "
        f"{action_id}"
    )

    print(
        f"Exception: "
        f"{action['exception_id']}"
    )

    print(
        f"Shipment: "
        f"{exception['shipment_id']}"
    )

    print(
        f"Transport mode: "
        f"{exception['transport_mode']} → "
        f"{option['transport_mode']}"
    )

    print(
        f"Carrier: "
        f"{exception['carrier_id']} → "
        f"{option['carrier_id']}"
    )

    print(
        f"Recovery execution: "
        f"{executed_at}"
    )

    print(
        f"Recovery transit: "
        f"{recovery_transit_days} days"
    )

    print(
        f"New estimated arrival: "
        f"{new_estimated_arrival_date}"
    )

    print(
        f"Required delivery: "
        f"{exception['required_delivery_date']}"
    )

    print(
        f"Event created: "
        f"{event_id}"
    )

    print(
        f"Action status: "
        f"{EXECUTED}"
    )

    print(
        f"Exception status: "
        f"{resolution_message}"
    )

    return True


# ==================================================
# VERIFY EXECUTION
# ==================================================

def show_execution_result(
    connection,
    action_id,
):
    """
    Display the current database state of an executed
    recovery action.
    """

    cursor = connection.cursor()

    result = cursor.execute(
        """
        SELECT
            ra.action_id,
            ra.exception_id,
            ra.option_id,
            ra.status AS action_status,
            ra.executed_at,

            e.resolution_status,
            e.resolved_at,

            s.shipment_id,
            s.transport_mode,
            s.carrier_id,
            s.estimated_arrival

        FROM recovery_actions ra

        JOIN exceptions e
            ON ra.exception_id = e.exception_id

        JOIN shipments s
            ON e.shipment_id = s.shipment_id

        WHERE ra.action_id = ?
        """,
        (action_id,),
    ).fetchone()

    if result is None:
        print(
            f"Action {action_id} not found."
        )
        return

    print("\nExecution Result")
    print("=" * 50)

    print(
        f"Action: "
        f"{result['action_id']}"
    )

    print(
        f"Exception: "
        f"{result['exception_id']}"
    )

    print(
        f"Option: "
        f"{result['option_id']}"
    )

    print(
        f"Action status: "
        f"{result['action_status']}"
    )

    print(
        f"Executed at: "
        f"{result['executed_at']}"
    )

    print(
        f"Shipment: "
        f"{result['shipment_id']}"
    )

    print(
        f"Transport mode: "
        f"{result['transport_mode']}"
    )

    print(
        f"Carrier: "
        f"{result['carrier_id']}"
    )

    print(
        f"Estimated arrival: "
        f"{result['estimated_arrival']}"
    )

    print(
        f"Exception status: "
        f"{result['resolution_status']}"
    )

    print(
        f"Resolved at: "
        f"{result['resolved_at']}"
    )


# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":

    connection = get_connection()

    try:

        print(
            "Execution engine loaded successfully."
        )

        print(
            "No recovery action was executed."
        )

    finally:

        connection.close()