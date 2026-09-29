"""
Operational pipeline refresh service group (P12.3 decomposition).

Sequences the existing idempotent pipeline stages
(detect -> options -> workflow actions) and reports the
run's new-work deltas.
"""

from app.detect_exceptions import detect_exceptions
from app.generate_recovery_options import generate_recovery_options
from app.repositories import exceptions_repo
from app.repositories import recovery_options_repo
from app.workflow_engine import (
    REJECTED,
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
    approve_action,
    reject_action,
    generate_workflow_actions,
)


def run_operational_refresh(connection):
    """
    Re-run the operational processing pipeline:

        detect exceptions
            ↓
        generate recovery options
            ↓
        generate workflow actions

    Each stage is the existing production function with its
    own idempotency guard and transaction boundary; this
    service only sequences them and aggregates the results.
    No business rules and no SQL live here, and unexpected
    errors from any stage propagate to the caller.

    Detection and option generation return no summary, so
    the newly created work is measured as before/after
    deltas through the existing repository counts. The
    action-generation summary is returned by the workflow
    engine and passed through unchanged. The identities of
    newly detected exceptions are reported through the
    latest-exception read so clients can surface exactly
    what the run has just found.

    The three stage functions resolve at call time through
    the package facade so the historical patch seam keeps
    working: tests patch services.detect_exceptions /
    services.generate_recovery_options /
    services.generate_workflow_actions at the package
    namespace, exactly as they did against the pre-split
    module. Same engine functions, same call order.
    """

    from app import services

    exceptions_before = exceptions_repo.count_exceptions(
        connection,
    )

    options_before = (
        recovery_options_repo.get_next_option_number(
            connection,
        )
        - 1
    )

    services.detect_exceptions(connection)

    services.generate_recovery_options(connection)

    actions_summary = services.generate_workflow_actions(connection)

    exceptions_after = exceptions_repo.count_exceptions(
        connection,
    )

    options_after = (
        recovery_options_repo.get_next_option_number(
            connection,
        )
        - 1
    )

    new_exception_count = (
        exceptions_after
        - exceptions_before
    )

    return {
        "new_exceptions": new_exception_count,
        "new_options": (
            options_after
            - options_before
        ),
        "new_exception_ids": (
            exceptions_repo.get_latest_exception_ids(
                connection,
                limit=new_exception_count,
            )
            if new_exception_count
            else []
        ),
        "actions_evaluated": actions_summary["evaluated"],
        "new_actions": actions_summary["created"],
        "actions_without_recommendation": actions_summary[
            "without_recommendation"
        ],
        "actions_skipped": actions_summary["skipped"],
    }
