"""
Inbox / dashboard data service group (P12.3 decomposition).

Aggregated dashboard metrics and the bounded exception
inbox, including the workflow-state derivation shared with
the operational-state classifier.
"""

from app.repositories import exceptions_repo
from app.repositories import recovery_actions_repo
from app.workflow_engine import (
    REJECTED,
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
    approve_action,
    reject_action,
    generate_workflow_actions,
)


def get_dashboard_metrics(connection):
    """
    Return the KPI metrics shown on the dashboard.

    Aggregated from the repositories; no business rules.
    """

    return {
        "open_exceptions":
            exceptions_repo.count_open_exceptions(connection),
        "critical_exceptions":
            exceptions_repo.count_open_critical_exceptions(connection),
        "pending_approvals": recovery_actions_repo.count_actions_by_status(
            connection,
            status="Pending Approval",
        ),
    }


def get_exception_inbox(connection):
    """
    Return the open-exception inbox rows for the dashboard.

    Each row carries the count of feasible recovery options
    (feasible_option_count) from the existing option data,
    and rows are ordered actionable-first inside each
    severity class. The count is retrieved operational
    data; the UI renders the actionable/monitoring wording.

    Rows are returned as plain dictionaries so no client —
    UI, API or CLI — depends on the persistence layer's row
    type (the versioned application-boundary contract,
    ADR-011).

    Each row also carries `workflow_state` — the exception's
    operational state from the SAME derivation as
    `classify_investigation_state` (checkpoint S): latest
    recovery-action status mapped through the documented
    open-state vocabulary. No parallel state machine: the
    values are exactly the classifier's open states, computed
    per row from the same persisted evidence (the latest
    recovery action's status, latest by `action_id`).
    """

    rows = []
    for row in exceptions_repo.get_open_exceptions_inbox(
        connection,
    ):
        item = dict(row)
        item["workflow_state"] = _workflow_state_from_action_status(
            item.get("latest_action_status"),
        )
        # The raw status is a derivation input, not contract
        # surface — the derived state supersedes it.
        del item["latest_action_status"]
        rows.append(item)
    return rows


def _workflow_state_from_action_status(latest_action_status):
    """
    The open-state vocabulary shared by the inbox rows and
    `classify_investigation_state` (checkpoint S), derived
    from the latest recovery action's status — the identical
    evidence the classifier reads. No state is invented:
    every branch mirrors the classifier's checks in order.
    """

    if latest_action_status is None:
        return "No system recovery available"
    if latest_action_status == APPROVED:
        return "Awaiting execution"
    if latest_action_status == EXECUTED:
        return "Executed — still open"
    return "Decision required"


# The documented open-state vocabulary the inbox contract
# exposes (P8.8): exactly the classifier's open states, in
# lifecycle order. The frontend filter grammar and the KPI
# deep-links consume this list verbatim.
WORKFLOW_STATES = (
    "Decision required",
    "Awaiting execution",
    "Executed — still open",
    "No system recovery available",
)
