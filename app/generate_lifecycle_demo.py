"""
Lifecycle demo seeder (P12.6 — Demo Dataset & Product Realism).

The bootstrap pipeline ends at "Pending Approval": detection,
option generation, recommendation and action generation all
run, but the human lifecycle stages (approval, execution,
resolution) are operational work the seed never exercises.
The demo product therefore never shows Awaiting execution,
Executed — still open, the follow-up queue or Recently
Resolved, and the bounded inbox (actionable-first, capped at
100 rows) hides the entire monitoring population behind the
828 pending-actionable rows.

This seeder progresses a deterministic historical cohort of
the OLDEST actionable exceptions through the REAL lifecycle
mechanisms — the workflow engine's approval transition and
the execution engine's execution transition, including their
shipment updates, recovery shipment events and the
executed-vs-resolved arrival arithmetic. No business rule is
reproduced here: the engines remain the only writers of
workflow semantics. The seeder owns exactly two seed-data
adjustments the engines cannot express:

- the historical cohort's `detected_at` is moved onto its
  shipment's departure date (detection historically preceded
  the decision), and the cohort's `approved_at` is moved onto
  the same date — so the rendered operational history reads
  detected → approved → executed in true chronological
  order instead of placing historical executions after the
  simulation's "today";
- manual resolutions are recorded through the manual-
  intervention repository primitives with deterministic
  timestamps, because the manual-resolution service stamps
  wall-clock time by design and a demo seed must not depend
  on when it was generated.

Everything is derived from data that already exists and the
controlled simulation timeline. No second clock is
introduced: execution timestamps come from the execution
engine's own rule (planned departure + the configured
offset), and the remaining stamps are fixed deterministic
positions on the shipment's own chronology.

Determinism and idempotency:

- the cohort selection is a deterministic ordering
  (planned_departure, exception_id) over persisted rows;
- the seeder is a no-op as soon as any lifecycle evidence
  exists (an Approved/Executed/Rejected action or any manual
  intervention) — a database a real planner has already
  worked in is never touched, and reruns can never duplicate
  lifecycle evidence;
- the E2E fixture exceptions (EXC-000008 / EXC-000009) are
  excluded explicitly so the browser suite's "Decision
  required" fixtures always remain exactly that.

The result is a demo dataset whose backlog reads like a
season of operational work: a current pending queue, a small
awaiting-execution set, historical executions that mostly
resolved and a realistic tail that stayed open for follow-up,
a manually resolved population, and a monitoring population
that becomes visible in the bounded inbox because the
historical actionable work has genuinely moved on.
"""

import logging
from datetime import datetime, timedelta

from app.config import SIMULATION_DATE
from app.execution_engine import execute_recovery_action
from app.repositories import exceptions_repo
from app.repositories import manual_interventions_repo
from app.services.manual_resolution import INTERVENTION_TYPES
from app.workflow_engine import (
    PENDING_APPROVAL,
    approve_action,
)

logger = logging.getLogger(__name__)


# ==================================================
# SEED PARAMETERS (deterministic, deliberately small)
# ==================================================

#: Exceptions the browser E2E suite depends on: they must stay
#: Open with a Pending Approval action ("Decision required").
E2E_FIXTURE_EXCEPTION_IDS = (
    "EXC-000008",
    "EXC-000009",
)

#: Pending actionable exceptions left untouched as the current
#: work queue (the actionable backlog the demo operates on).
PENDING_BACKLOG_TARGET = 35

#: Historical exceptions left Approved (awaiting execution) —
#: approved "today" on the simulation clock, not yet executed.
AWAITING_EXECUTION_TARGET = 8

#: No-recovery exceptions resolved manually by a planner.
MANUAL_RESOLUTION_TARGET = 6

#: Deterministic planner identities for the seeded decisions.
PLANNER_NAMES = (
    "A. Rivera",
    "K. Stein",
    "M. Okafor",
    "J. Lindqvist",
    "P. Novak",
    "T. Marchetti",
)

#: Days before the simulation date on which the manual
#: resolutions are recorded (newest exception gets the newest
#: recording date), so Recently Resolved interleaves the two
#: resolution paths instead of showing only one.
MANUAL_RESOLUTION_DAYS_BACK = (9, 7, 5, 3, 2, 1)

#: Times of day (simulation-local) for the seeded stamps.
DETECTION_TIME_OF_DAY = "08:00:00"
APPROVAL_TIME_OF_DAY = "12:00:00"
MANUAL_RESOLUTION_TIME_OF_DAY = "16:00:00"


def _has_lifecycle_evidence(connection):
    """
    True when any lifecycle stage beyond generation has
    already happened in this database (a decision was made,
    an action was executed, or a manual intervention was
    recorded). The seeder never runs on such a database.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM recovery_actions
                WHERE status IN ('Approved', 'Executed', 'Rejected')
            )
            +
            (
                SELECT COUNT(*)
                FROM manual_interventions
            )
        """
    )

    return cursor.fetchone()[0] > 0


def _select_pending_cohort(connection):
    """
    The deterministic historical cohort: open exceptions with
    a Pending Approval action and a feasible recommendation,
    oldest shipment departure first (exception_id as the
    deterministic tie-break), E2E fixtures excluded.

    The newest members of this ordering become the retained
    backlog; the oldest are progressed through the lifecycle.
    """

    placeholders = ", ".join("?" for _ in E2E_FIXTURE_EXCEPTION_IDS)

    return connection.cursor().execute(
        f"""
        SELECT
            e.exception_id,
            ra.action_id,
            s.planned_departure
        FROM exceptions e
        JOIN recovery_actions ra
            ON ra.exception_id = e.exception_id
            AND ra.status = '{PENDING_APPROVAL}'
        JOIN shipments s
            ON e.shipment_id = s.shipment_id
        WHERE e.resolution_status = 'Open'
          AND e.exception_id NOT IN ({placeholders})
          AND EXISTS (
              SELECT 1
              FROM recovery_options ro
              WHERE ro.exception_id = e.exception_id
                AND ro.feasible = 1
          )
        ORDER BY
            s.planned_departure ASC,
            e.exception_id ASC
        """,
        E2E_FIXTURE_EXCEPTION_IDS,
    ).fetchall()


def _select_manual_cohort(connection):
    """
    The deterministic manual-resolution cohort: open
    exceptions with no recovery action and no feasible
    option (monitoring population), oldest departure first,
    E2E fixtures excluded. These are exactly the cases where
    a planner resolution outside the system is the plausible
    operational outcome.
    """

    placeholders = ", ".join("?" for _ in E2E_FIXTURE_EXCEPTION_IDS)

    return connection.cursor().execute(
        f"""
        SELECT
            e.exception_id,
            s.estimated_arrival,
            s.planned_departure
        FROM exceptions e
        JOIN shipments s
            ON e.shipment_id = s.shipment_id
        WHERE e.resolution_status = 'Open'
          AND e.exception_id NOT IN ({placeholders})
          AND NOT EXISTS (
              SELECT 1
              FROM recovery_actions ra
              WHERE ra.exception_id = e.exception_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM recovery_options ro
              WHERE ro.exception_id = e.exception_id
                AND ro.feasible = 1
          )
        ORDER BY
            s.planned_departure ASC,
            e.exception_id ASC
        LIMIT {MANUAL_RESOLUTION_TARGET}
        """,
        E2E_FIXTURE_EXCEPTION_IDS,
    ).fetchall()


def _backdate_detection(connection, exception_id, planned_departure):
    """
    Move one seeded exception's detection timestamp onto its
    shipment's departure date (detection historically
    preceded the decision it received). Part of the seeder's
    seed-data ownership, not workflow semantics.
    """

    detected_at = (
        f"{planned_departure} {DETECTION_TIME_OF_DAY}"
    )

    connection.cursor().execute(
        """
        UPDATE exceptions
        SET detected_at = ?
        WHERE exception_id = ?
        """,
        (detected_at, exception_id),
    )


def _progress_through_execution(connection, cohort):
    """
    Approve and execute the historical cohort through the
    real engines, then place the approval stamp on the
    shipment's own chronology so the recorded history reads
    detected → approved → executed. The execution stamp
    needs no adjustment: the execution engine already derives
    it deterministically from the planned departure.
    """

    progressed = 0

    for row in cohort:

        exception_id = row["exception_id"]
        action_id = row["action_id"]
        planned_departure = row["planned_departure"]

        _backdate_detection(connection, exception_id, planned_departure)

        # The real workflow transition (validates the state
        # machine, stamps the audit fields, commits).
        approve_action(
            connection,
            action_id,
            approved_by=PLANNER_NAMES[progressed % len(PLANNER_NAMES)],
        )

        # The real execution transition: updates the shipment,
        # writes the recovery shipment event, marks the action
        # Executed and resolves the exception exactly when the
        # recorded arrival meets the required delivery date.
        execute_recovery_action(
            connection,
            action_id,
        )

        # Historical placement of the human decision (see the
        # module docstring): the engine stamped the simulation
        # "today"; this seeded record's decision happened on
        # the shipment's departure date.
        approved_at = (
            f"{planned_departure} {APPROVAL_TIME_OF_DAY}"
        )

        connection.cursor().execute(
            """
            UPDATE recovery_actions
            SET approved_at = ?
            WHERE action_id = ?
              AND status = 'Executed'
            """,
            (approved_at, action_id),
        )

        progressed += 1

    return progressed


def _record_manual_resolutions(connection, cohort):
    """
    Record deterministic manual resolutions for the no-recovery
    cohort through the manual-intervention repository
    primitives, mirroring the manual-resolution service's
    atomic write shape (intervention record + status update in
    one commit) with deterministic timestamps in place of the
    service's wall-clock stamp.
    """

    if len(cohort) < MANUAL_RESOLUTION_TARGET:

        logger.warning(
            "Manual-resolution cohort holds only %s of the %s "
            "configured resolutions; the remainder is skipped.",
            len(cohort),
            MANUAL_RESOLUTION_TARGET,
        )

    recorded = 0

    for offset, row in zip(
        MANUAL_RESOLUTION_DAYS_BACK,
        cohort,
    ):

        exception_id = row["exception_id"]
        planned_departure = row["planned_departure"]

        _backdate_detection(connection, exception_id, planned_departure)

        recorded_at = (
            datetime.strptime(SIMULATION_DATE, "%Y-%m-%d")
            - timedelta(days=offset)
        ).strftime("%Y-%m-%d") + f" {MANUAL_RESOLUTION_TIME_OF_DAY}"

        intervention_id = (
            "INT-"
            f"{manual_interventions_repo.get_next_intervention_number(connection):06d}"
        )

        manual_interventions_repo.insert_manual_intervention(
            connection,
            (
                intervention_id,
                exception_id,
                # The coordination type a delayed-delivery call
                # actually is; the vocabulary is the service's
                # own domain constant.
                INTERVENTION_TYPES[0],
                "Carrier operations",
                (
                    "Coordinated a revised delivery plan with the "
                    "carrier; the customer accepted the revised "
                    "arrival date and the shipment continues "
                    "under monitoring."
                ),
                # The accepted revised date is the arrival the
                # shipment already carries — no new data invented.
                row["estimated_arrival"],
                "Resolved",
                None,
                PLANNER_NAMES[recorded % len(PLANNER_NAMES)],
                recorded_at,
            ),
        )

        rows_marked = exceptions_repo.mark_exception_resolved(
            connection,
            exception_id,
            resolved_at=recorded_at,
        )

        if rows_marked != 1:
            connection.rollback()
            raise RuntimeError(
                f"Manual resolution could not mark {exception_id} "
                f"as Resolved."
            )

        recorded += 1

    connection.commit()

    return recorded


def generate_lifecycle_demo(connection):
    """
    Seed the demo lifecycle history (idempotent, deterministic).

    Returns a small report dict describing what was seeded —
    or that the database already carries lifecycle evidence
    and was left untouched.
    """

    if _has_lifecycle_evidence(connection):

        logger.info(
            "Lifecycle demo history already present — "
            "seed left untouched."
        )

        return {"seeded": False}

    pending_cohort = _select_pending_cohort(connection)

    retain = PENDING_BACKLOG_TARGET + AWAITING_EXECUTION_TARGET

    if len(pending_cohort) <= retain:

        logger.warning(
            "Lifecycle demo seed skipped: the pending cohort "
            "(%s) is too small to progress while retaining the "
            "configured backlog.",
            len(pending_cohort),
        )

        return {"seeded": False, "reason": "cohort-too-small"}

    executed_cohort = pending_cohort[:-retain]
    awaiting_cohort = pending_cohort[-AWAITING_EXECUTION_TARGET:]

    manual_cohort = _select_manual_cohort(connection)

    executed_count = _progress_through_execution(
        connection,
        executed_cohort,
    )

    awaiting_count = 0

    for row in awaiting_cohort:

        _backdate_detection(
            connection,
            row["exception_id"],
            row["planned_departure"],
        )

        # Approved "today" on the simulation clock — exactly
        # what the workflow engine stamps — so these records
        # read as current work awaiting execution.
        approve_action(
            connection,
            row["action_id"],
            approved_by=PLANNER_NAMES[awaiting_count % len(PLANNER_NAMES)],
        )

        awaiting_count += 1

    manual_count = _record_manual_resolutions(
        connection,
        manual_cohort,
    )

    logger.info("Lifecycle demo seed complete.")
    logger.info(
        "Executed: %s | Awaiting execution: %s | "
        "Manual resolutions: %s",
        executed_count,
        awaiting_count,
        manual_count,
    )

    return {
        "seeded": True,
        "executed": executed_count,
        "awaiting_execution": awaiting_count,
        "manual_resolutions": manual_count,
    }
