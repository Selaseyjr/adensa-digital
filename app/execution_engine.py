import logging
from datetime import datetime, timedelta

from app.config import (
    RECOVERY_EXECUTION_OFFSET_DAYS,
)
from app.database import get_connection
from app.errors import RecoveryWorkflowError
from app.repositories import exceptions_repo
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo
from app.workflow_engine import (
    APPROVED,
    EXECUTED,
    validate_transition,
)

logger = logging.getLogger(__name__)


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

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    if action is None:
        raise RecoveryWorkflowError(
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

    option = recovery_options_repo.get_option_by_id(
        connection,
        action["option_id"],
    )

    if option is None:
        raise RecoveryWorkflowError(
            f"Recovery option {action['option_id']} "
            f"not found."
        )

    # --------------------------------------------------
    # 4. VERIFY OPTION BELONGS TO EXCEPTION
    # --------------------------------------------------

    if option["exception_id"] != action["exception_id"]:
        raise RecoveryWorkflowError(
            f"Recovery option {action['option_id']} "
            f"does not belong to exception "
            f"{action['exception_id']}."
        )

    # --------------------------------------------------
    # 5. GET EXCEPTION + SHIPMENT + ORDER
    # --------------------------------------------------

    exception = exceptions_repo.get_exception_operational_context(
        connection,
        action["exception_id"],
    )

    if exception is None:
        raise RecoveryWorkflowError(
            f"Exception {action['exception_id']} "
            f"not found."
        )

    # --------------------------------------------------
    # 6. VERIFY EXCEPTION IS STILL OPEN
    # --------------------------------------------------

    if exception["resolution_status"] != "Open":
        raise RecoveryWorkflowError(
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
        raise RecoveryWorkflowError(
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
        raise RecoveryWorkflowError(
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

    action_rows_updated = recovery_actions_repo.mark_action_executed(
        connection,
        action_id=action_id,
        executed_at=executed_at,
        expected_current_status=APPROVED,
    )

    if action_rows_updated != 1:
        raise RecoveryWorkflowError(
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

    logger.info("\nRecovery Execution")
    logger.info("=" * 50)

    logger.info(
        f"Action: "
        f"{action_id}"
    )

    logger.info(
        f"Exception: "
        f"{action['exception_id']}"
    )

    logger.info(
        f"Shipment: "
        f"{exception['shipment_id']}"
    )

    logger.info(
        f"Transport mode: "
        f"{exception['transport_mode']} → "
        f"{option['transport_mode']}"
    )

    logger.info(
        f"Carrier: "
        f"{exception['carrier_id']} → "
        f"{option['carrier_id']}"
    )

    logger.info(
        f"Recovery execution: "
        f"{executed_at}"
    )

    logger.info(
        f"Recovery transit: "
        f"{recovery_transit_days} days"
    )

    logger.info(
        f"New estimated arrival: "
        f"{new_estimated_arrival_date}"
    )

    logger.info(
        f"Required delivery: "
        f"{exception['required_delivery_date']}"
    )

    logger.info(
        f"Event created: "
        f"{event_id}"
    )

    logger.info(
        f"Action status: "
        f"{EXECUTED}"
    )

    logger.info(
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
        logger.info(
            f"Action {action_id} not found."
        )
        return

    logger.info("\nExecution Result")
    logger.info("=" * 50)

    logger.info(
        f"Action: "
        f"{result['action_id']}"
    )

    logger.info(
        f"Exception: "
        f"{result['exception_id']}"
    )

    logger.info(
        f"Option: "
        f"{result['option_id']}"
    )

    logger.info(
        f"Action status: "
        f"{result['action_status']}"
    )

    logger.info(
        f"Executed at: "
        f"{result['executed_at']}"
    )

    logger.info(
        f"Shipment: "
        f"{result['shipment_id']}"
    )

    logger.info(
        f"Transport mode: "
        f"{result['transport_mode']}"
    )

    logger.info(
        f"Carrier: "
        f"{result['carrier_id']}"
    )

    logger.info(
        f"Estimated arrival: "
        f"{result['estimated_arrival']}"
    )

    logger.info(
        f"Exception status: "
        f"{result['resolution_status']}"
    )

    logger.info(
        f"Resolved at: "
        f"{result['resolved_at']}"
    )


# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    connection = get_connection()

    try:

        logger.info(
            "Execution engine loaded successfully."
        )

        logger.info(
            "No recovery action was executed."
        )

    finally:

        connection.close()