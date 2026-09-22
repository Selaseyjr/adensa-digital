"""
Application service layer.

Owns the application/workflow orchestration that previously
lived in the Streamlit UI (app/main.py):

    Streamlit UI
         ↓
      main.py
         ↓
      services        ← this module
         ↓
      engines
         ↓
    repositories
         ↓
       SQLite

Rules:

- Services sequence engines and repositories and construct
  application-level result dictionaries for any frontend.
- Business rules stay in the engines; this module never
  duplicates them.
- No Streamlit imports and no UI strings: the UI consumes
  the returned dictionaries.
- No commits and no transaction management: transaction
  boundaries remain exactly where they were (inside the
  engine operations).
- Plain functions only: no classes, no frameworks.
"""

from datetime import datetime

from app.config import DECISION_WEIGHTS
from app.detect_exceptions import detect_exceptions
from app.decision_engine import get_recommendation
from app.errors import (
    ActionNotFoundError,
    ManualInterventionNotAllowedError,
    RecoveryWorkflowError,
)
from app.execution_engine import execute_recovery_action
from app.generate_recovery_options import generate_recovery_options
from app.ai_support import (
    DEFAULT_PROVIDER,
    AiProviderError,
    BriefValidationError,
    unavailable_brief,
    validate_decision_brief,
)
from app.sustainability import build_sustainability_comparison
from app.repositories import exceptions_repo
from app.repositories import manual_interventions_repo
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo
from app.repositories import shipments_repo
from app.simulation import create_simulated_arrival
from app.workflow_engine import (
    REJECTED,
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
    approve_action,
    reject_action,
    generate_workflow_actions,
)


# ==================================================
# DASHBOARD DATA
# ==================================================

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
    """

    return [
        dict(row)
        for row in exceptions_repo.get_open_exceptions_inbox(
            connection,
        )
    ]


# ==================================================
# EXCEPTION REVIEW
# ==================================================

def get_exception_review(
    connection,
    exception_id,
):
    """
    Build the decision-engine review for an exception.

    The returned dictionary contains the engine's
    recommendation structure unchanged, including the
    selected option_id when a feasible recommendation
    exists.
    """

    return get_recommendation(
        connection,
        exception_id,
    )


def get_latest_action(
    connection,
    exception_id,
):
    """
    Return the most recent recovery action for an
    exception, or None.

    The action is returned as a plain dictionary so no
    client depends on the persistence layer's row type
    (the versioned application-boundary contract,
    ADR-011).
    """

    action = recovery_actions_repo.get_latest_action_for_exception(
        connection,
        exception_id,
    )

    return dict(action) if action is not None else None


# Factor columns used in the rationale projection, in a
# fixed, planner-readable order. Each entry pairs the UI
# label with the decision-engine factor-score key, its
# configured weight key and the engine's weighted-
# contribution key.

RATIONALE_FACTORS = (
    ("Cost fit", "cost_score", "cost", "cost_contribution"),
    (
        "Transit fit",
        "transit_score",
        "transit",
        "transit_contribution",
    ),
    (
        "Risk fit",
        "risk_component",
        "risk",
        "risk_contribution",
    ),
    (
        "Priority fit",
        "priority_score",
        "priority_alignment",
        "priority_contribution",
    ),
)


def get_recommendation_rationale(review):
    """
    Build a structured, presentation-oriented rationale for
    an existing decision-engine review.

    This is a projection layer only: every value is taken
    from the engine's own output (factor scores, weighted
    contributions, decision scores, confidence) or from the
    authoritative decision configuration (DECISION_WEIGHTS).
    No factor is recomputed and no business rule is
    re-applied here.

    The projection exists so the planner can answer "why
    this option, and what trade-offs did it make?" without
    reverse-engineering the score:

    - factor_breakdown: one row per factor comparing the
      recommendation with each alternative (raw score,
      weight, weighted contribution);
    - trade_offs: per-alternative, factor-level statements
      of where an alternative beats the recommendation;
    - weights: the configured policy itself, straight from
      app.config (never duplicated in the UI);
    - confidence_basis: the factual basis of the confidence
      label (score separation) so it is not mistaken for a
      statistical probability.
    """

    recommendation = review.get("recommendation")

    if recommendation is None:

        return None

    weights = DECISION_WEIGHTS
    alternatives = review.get("alternatives") or []

    # One row per factor per compared option: the
    # recommendation first, then every alternative, all in
    # the engine's own ranking order.

    compared = [recommendation, *alternatives]

    factor_breakdown = []

    for factor_label, score_key, weight_key, contribution_key in (
        RATIONALE_FACTORS
    ):

        weight = weights[weight_key]

        factor_breakdown.append(
            {
                "factor": factor_label,
                "weight": weight,
                "values": [
                    {
                        "option_id": option["option_id"],
                        "transport_mode": (
                            option["transport_mode"]
                        ),
                        "score": option[score_key],
                        "contribution": option[
                            contribution_key
                        ],
                    }
                    for option in compared
                ],
            }
        )

    # Trade-offs: where an alternative is genuinely stronger
    # than the recommendation on an individual factor, say
    # so factually. The recommendation can still win because
    # the weighted total favours it.

    trade_offs = []

    for option in alternatives:

        stronger_factors = []

        for factor_label, score_key, _weight_key, _contribution_key in (
            RATIONALE_FACTORS
        ):

            if option[score_key] > recommendation[score_key]:

                stronger_factors.append(factor_label)

        if stronger_factors:

            trade_offs.append(
                {
                    "option_id": option["option_id"],
                    "transport_mode": option["transport_mode"],
                    "stronger_factors": stronger_factors,
                }
            )

    # Confidence semantics: the engine derives the label
    # from the separation between the recommendation's score
    # and the next-best alternative (sole feasible option is
    # reported High). Expose that basis explicitly so the
    # label is not misread as a probability of success.

    if not alternatives:

        confidence_basis = (
            "High confidence reflects a single feasible "
            "recovery option, not a probability of success."
        )

    else:

        next_best_score = max(
            option["decision_score"]
            for option in alternatives
        )

        score_gap = (
            recommendation["decision_score"]
            - next_best_score
        )

        confidence_basis = (
            "Derived from the separation between the "
            "recommended option's score and the next-best "
            f"alternative ({score_gap:.2f} points). It is "
            "not a probability of success."
        )

    return {
        "weights": {
            "cost": weights["cost"],
            "transit": weights["transit"],
            "risk": weights["risk"],
            "priority_alignment": (
                weights["priority_alignment"]
            ),
        },
        "factor_breakdown": factor_breakdown,
        "trade_offs": trade_offs,
        "confidence_basis": confidence_basis,
    }


def get_recovery_assessment(
    connection,
    exception_id,
):
    """
    Return the recovery assessment for an exception: the
    decision-engine review plus, when no recommendation
    exists, the evaluated options that explain why.

    When the engine has a feasible option to recommend,
    the assessment carries the recommendation and its
    alternatives exactly as the review does, plus a
    structured rationale (weights, per-factor breakdown,
    trade-offs, confidence basis) projected from the
    engine's own output. When it has none, the previously
    generated options - feasible and infeasible - are
    included as evaluated_options, each with its own
    operational data (mode, carrier, cost, transit, risk)
    and its feasibility verdict. The engines
    do not persist a granular rejection reason, so none is
    invented here: the verdict and the option's operational
    data are the strongest truthful information available.

    Returns None when the exception does not exist.
    """

    review = get_recommendation(
        connection,
        exception_id,
    )

    if review is None:
        return None

    if review["recommendation"] is not None:

        return {
            "recommendation": review["recommendation"],
            "alternatives": review["alternatives"],
            "evaluated_options": [],
            "rationale": get_recommendation_rationale(
                review,
            ),
        }

    return {
        "recommendation": None,
        "alternatives": [],
        "rationale": None,
        "evaluated_options": [
            {
                "option_id": option["option_id"],
                "transport_mode": option["transport_mode"],
                "carrier_id": option["carrier_id"],
                "estimated_cost": option["estimated_cost"],
                "estimated_transit_days": option[
                    "estimated_transit_days"
                ],
                "risk_score": option["risk_score"],
                "feasible": bool(option["feasible"]),
            }
            for option in (
                recovery_options_repo.get_options_for_exception(
                    connection,
                    exception_id,
                )
            )
        ],
    }


# ==================================================
# WORKFLOW OUTCOMES
# ==================================================

def approve_recovery(
    connection,
    action_id,
    approved_by,
):
    """
    Approve a pending recovery action and return the
    application outcome dictionary.

    The workflow transition is performed by the workflow
    engine, including its transaction boundary and its
    validation: a missing action, an invalid transition or
    a closed exception raises before any state changes.

    The outcome context is resolved from application state
    through the repositories: the action's exception and
    option identity, the exception's operational context
    and the recovery option stored on the action.
    """

    approve_action(
        connection,
        action_id,
        approved_by,
    )

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    context = exceptions_repo.get_exception_operational_context(
        connection,
        action["exception_id"],
    )

    option = recovery_options_repo.get_option_by_id(
        connection,
        action["option_id"],
    )

    return {
        "success": True,
        "message": (
            f"Recovery action "
            f"{action_id} "
            f"approved successfully."
        ),
        "action_id": action_id,
        "shipment_id": context["shipment_id"],
        "previous_mode": context["transport_mode"],
        "new_mode": option["transport_mode"],
        "carrier_id": option["carrier_id"],
        "new_eta": "Pending execution",
        "recovery_event": "Pending execution",
        "required_delivery": context["required_delivery_date"],
        "exception_status": "Open",
    }


def reject_recovery(
    connection,
    action_id,
    rejected_by,
):
    """
    Reject a pending recovery action and return the
    application outcome dictionary.

    The workflow transition is performed by the workflow
    engine, including its transaction boundary and its
    validation. No recovery option is consulted: rejection
    does not execute anything, so the outcome carries the
    existing sentinel values.
    """

    reject_action(
        connection,
        action_id,
        rejected_by,
    )

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    context = exceptions_repo.get_exception_operational_context(
        connection,
        action["exception_id"],
    )

    return {
        "success": True,
        "message": (
            f"Recovery action "
            f"{action_id} "
            f"rejected."
        ),
        "action_id": action_id,
        "shipment_id": context["shipment_id"],
        "previous_mode": context["transport_mode"],
        "new_mode": context["transport_mode"],
        "carrier_id": "No execution",
        "new_eta": "No execution",
        "recovery_event": "None",
        "required_delivery": context["required_delivery_date"],
        "exception_status": "Open",
    }


def execute_approved_recovery(
    connection,
    action_id,
):
    """
    Execute an approved recovery action and return the
    application outcome dictionary.

    The service resolves its own context through the
    repositories: the action's exception, the exception's
    operational context and the shipment's transport mode
    captured BEFORE the engine mutates it. The engine then
    performs the execution and its transaction boundary;
    this service collects the resulting application state
    and normalizes it into the outcome dictionary.

    On failure the returned dictionary carries
    success False and the error message, mirroring the
    application behavior previously implemented by the UI.
    """

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    if action is None:
        raise ActionNotFoundError(
            f"Action {action_id} not found."
        )

    context = exceptions_repo.get_exception_operational_context(
        connection,
        action["exception_id"],
    )

    shipment_id = context["shipment_id"]

    exception_id = action["exception_id"]

    required_delivery = context["required_delivery_date"]

    # Capture the current shipment state before execution.
    previous_shipment = shipments_repo.get_shipment_transport_mode_and_carrier(
        connection,
        shipment_id,
    )

    previous_mode = (
        previous_shipment["transport_mode"]
    )

    try:
        execute_recovery_action(
            connection,
            action_id,
        )
    except RecoveryWorkflowError as error:

        return {
            "success": False,
            "message": (
                f"Recovery execution failed: "
                f"{error}"
            ),
        }

    updated_shipment = shipments_repo.get_shipment_delivery_state(
        connection,
        shipment_id,
    )

    recovery_event = shipments_repo.get_latest_recovery_event_id(
        connection,
        shipment_id,
    )

    final_exception = exceptions_repo.get_exception_resolution_status(
        connection,
        exception_id,
    )

    exception_status = (
        final_exception[
            "resolution_status"
        ]
    )

    return {
        "success": True,
        "message": (
            f"Recovery executed successfully "
            f"for "
            f"{shipment_id}."
        ),
        "action_id": action_id,
        "shipment_id": shipment_id,
        "previous_mode": previous_mode,
        "new_mode": updated_shipment[
            "transport_mode"
        ],
        "carrier_id": updated_shipment[
            "carrier_id"
        ],
        "new_eta": updated_shipment[
            "estimated_arrival"
        ],
        "recovery_event": (
            recovery_event["event_id"]
            if recovery_event
            else "Not recorded"
        ),
        "required_delivery": required_delivery,
        "exception_status": exception_status,
    }


# ==================================================
# EXCEPTION INVESTIGATION CONTEXT
# ==================================================

def get_exception_context(
    connection,
    exception_id,
):
    """
    Return the operational investigation context for one
    exception, or None when the exception does not exist.

    Projects the existing shared context read into an
    application-facing structure for the UI and any other
    client. Contains no business rules: every field is
    retrieved operational data, including the recorded
    detection description (what happened) and the current
    resolution status.
    """

    context = exceptions_repo.get_exception_operational_context(
        connection,
        exception_id,
    )

    if context is None:
        return None

    return {
        "exception_id": context["exception_id"],
        "shipment_id": context["shipment_id"],
        "order_id": context["order_id"],
        "customer_id": context["customer_id"],
        "customer_name": context["customer_name"],
        "exception_type": context["exception_type"],
        "severity": context["severity"],
        "status": context["resolution_status"],
        "description": context["description"],
        "priority": context["priority"],
        "origin": context["origin"],
        "destination": context["destination"],
        "route": (
            f"{context['origin']} → "
            f"{context['destination']}"
        ),
        "transport_mode": context["transport_mode"],
        "carrier_id": context["carrier_id"],
        "shipment_status": context["shipment_status"],
        "planned_departure": context["planned_departure"],
        "estimated_arrival": context["estimated_arrival"],
        "required_delivery_date": context[
            "required_delivery_date"
        ],
    }


# ==================================================
# OPERATIONAL PIPELINE REFRESH
# ==================================================

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
    """

    exceptions_before = exceptions_repo.count_exceptions(
        connection,
    )

    options_before = (
        recovery_options_repo.get_next_option_number(
            connection,
        )
        - 1
    )

    detect_exceptions(connection)

    generate_recovery_options(connection)

    actions_summary = generate_workflow_actions(connection)

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


# ==================================================
# MANUAL RESOLUTION (HUMAN-DRIVEN RECOVERY)
# ==================================================

INTERVENTION_TYPES = (
    "Carrier call",
    "Carrier email",
    "Supplier coordination",
    "Customer coordination",
    "Internal coordination",
    "Other",
)

OUTCOME_RESOLVED = "Resolved"

OUTCOME_STILL_OPEN = "Still Open"


def record_manual_resolution(
    connection,
    exception_id,
    intervention_type,
    external_party,
    resolution_summary,
    recorded_by,
    outcome,
    new_expected_delivery=None,
    notes=None,
):
    """
    Record a manual resolution for an exception that the
    human planner resolved outside Adensa.

    A manual intervention is a distinct operational event:
    it never creates recovery-option or recovery-action
    records and never touches the system-driven recovery
    workflow. The intervention record and the exception
    status update commit atomically in one transaction.

    Validation (all failures raise before any write):

    - the exception must exist and be open;
    - a system recovery action for the exception must not
      be Pending Approval or Approved, so recording a
      manual resolution can never silently bypass the
      human-in-the-loop recovery workflow;
    - intervention type and outcome must be valid domain
      values; free-text fields must not be empty.

    Resolution follows the existing state rules: the
    exception becomes Resolved only when the recorded
    outcome is Resolved; otherwise it remains open and
    monitored. recorded_at is the current wall-clock time.
    """

    if intervention_type not in INTERVENTION_TYPES:
        raise ManualInterventionNotAllowedError(
            f"Unknown intervention type: {intervention_type}."
        )

    if outcome not in (OUTCOME_RESOLVED, OUTCOME_STILL_OPEN):
        raise ManualInterventionNotAllowedError(
            f"Unknown outcome: {outcome}."
        )

    for field_value, field_name in (
        (external_party, "external party"),
        (resolution_summary, "resolution summary"),
        (recorded_by, "recorder"),
    ):

        if not field_value or not field_value.strip():
            raise ManualInterventionNotAllowedError(
                f"The {field_name} is required."
            )

    exception = exceptions_repo.get_exception_resolution_status(
        connection,
        exception_id,
    )

    if exception is None:
        raise ActionNotFoundError(
            f"Exception {exception_id} not found."
        )

    if exception["resolution_status"] != "Open":
        raise ManualInterventionNotAllowedError(
            f"Exception {exception_id} is already "
            f"{exception['resolution_status']} and cannot "
            f"receive further interventions."
        )

    action = recovery_actions_repo.get_latest_action_for_exception(
        connection,
        exception_id,
    )

    if action and action["status"] in (
        "Pending Approval",
        "Approved",
    ):
        raise ManualInterventionNotAllowedError(
            f"Exception {exception_id} has a system recovery "
            f"action ({action['action_id']}) that is "
            f"{action['status']}. Resolve it through the "
            f"recovery workflow before recording a manual "
            f"resolution."
        )

    intervention_id = (
        f"INT-{manual_interventions_repo.get_next_intervention_number(connection):06d}"
    )

    recorded_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    try:

        manual_interventions_repo.insert_manual_intervention(
            connection,
            (
                intervention_id,
                exception_id,
                intervention_type,
                external_party.strip(),
                resolution_summary.strip(),
                new_expected_delivery,
                outcome,
                notes,
                recorded_by.strip(),
                recorded_at,
            ),
        )

        if outcome == OUTCOME_RESOLVED:

            rows_updated = exceptions_repo.mark_exception_resolved(
                connection,
                exception_id,
                resolved_at=recorded_at,
            )

            if rows_updated != 1:
                raise RecoveryWorkflowError(
                    f"Exception {exception_id} could not be "
                    f"marked as Resolved."
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return {
        "success": True,
        "message": (
            f"Manual resolution {intervention_id} recorded "
            f"for {exception_id}."
        ),
        "intervention_id": intervention_id,
        "exception_id": exception_id,
        "intervention_type": intervention_type,
        "external_party": external_party.strip(),
        "resolution_summary": resolution_summary.strip(),
        "new_expected_delivery": new_expected_delivery,
        "outcome": outcome,
        "notes": notes,
        "recorded_by": recorded_by.strip(),
        "recorded_at": recorded_at,
        "exception_status": (
            "Resolved"
            if outcome == OUTCOME_RESOLVED
            else "Open"
        ),
    }


def get_exception_history(
    connection,
    exception_id,
):
    """
    Compose the chronological operational history of one
    exception from real persisted records — never invented
    events.

    Every entry carries the timestamp actually stored for
    that lifecycle step; steps with no persisted timestamp
    (option evaluation, the still-open outcome) are dated
    "—" in the UI so no time is fabricated. Timestamps
    across the domain share the same ISO format, so sorting
    on (anchor, sequence) is chronological even when several
    steps share a timestamp: dated entries sort by their
    stored time, the undated evaluation entry is anchored to
    its detection time (it always follows detection), and
    the undated still-open outcome — the current state, not
    a past event — sorts last.

    Sources:

    - exceptions.detected_at        -> detection
    - recovery_options rows         -> evaluated options
    - recovery_actions rows         -> recommendation,
                                      decision, execution
    - manual_interventions rows     -> recorded interventions
    - exceptions.resolved_at        -> resolution
    """

    exception = exceptions_repo.get_exception_lifecycle(
        connection,
        exception_id,
    )

    if exception is None:
        return None

    history = []

    # --------------------------------------------------
    # DETECTION (always present)
    # --------------------------------------------------

    history.append(
        {
            "timestamp": exception["detected_at"],
            "event": "Exception detected",
            "detail": (
                f"{exception['severity']} severity — "
                f"{exception['description']}"
            ),
            "actor": "Adensa operational pipeline",
            "sequence": 0,
        }
    )

    # --------------------------------------------------
    # OPTION EVALUATION (narrative position: right after
    # detection; the options carry no timestamps)
    # --------------------------------------------------

    options = (
        recovery_options_repo.get_options_for_exception(
            connection,
            exception_id,
        )
    )

    option_count = len(options)

    if option_count:

        feasible_count = len(
            recovery_options_repo.get_feasible_options_for_exception(
                connection,
                exception_id,
            )
        )

        if feasible_count:
            result = (
                f"{feasible_count} feasible — "
                f"{option_count - feasible_count} "
                f"infeasible"
            )
        else:
            result = "none feasible — no system " "recommendation"

        history.append(
            {
                "timestamp": None,
                "event": "Recovery options evaluated",
                "detail": (
                    f"{option_count} options assessed; "
                    f"{result}"
                ),
                "actor": "Adensa recovery engine",
                "sequence": 1,
            }
        )

    # --------------------------------------------------
    # SYSTEM RECOVERY ACTIONS (oldest first)
    # --------------------------------------------------

    for action in (
        recovery_actions_repo.get_actions_for_exception(
            connection,
            exception_id,
        )
    ):

        history.append(
            {
                "timestamp": action["approved_at"],
                "event": "Recommendation generated",
                "detail": (
                    f"{action['action_id']} — "
                    f"{action['description']}"
                ),
                "actor": "Adensa decision engine",
                "sequence": len(history),
            }
        )

        if action["status"] == REJECTED:

            history.append(
                {
                    "timestamp": action["approved_at"],
                    "event": "Recovery rejected",
                    "detail": (
                        f"{action['action_id']} — system "
                        f"recommendation not accepted"
                    ),
                    "actor": action["approved_by"],
                    "sequence": len(history),
                }
            )

        elif action["approved_at"]:

            # A human decision was recorded: the action's
            # approval audit fields are the persisted record
            # of it. This covers Approved and Executed
            # actions alike — the decision happened in both
            # cases.

            history.append(
                {
                    "timestamp": action["approved_at"],
                    "event": "Recovery approved",
                    "detail": (
                        f"{action['action_id']} by "
                        f"{action['approved_by']}"
                    ),
                    "actor": action["approved_by"],
                    "sequence": len(history),
                }
            )

            if action["executed_at"]:

                history.append(
                    {
                        "timestamp": action["executed_at"],
                        "event": "Recovery executed",
                        "detail": (
                            f"{action['action_id']} — shipment "
                            f"recovered through the system "
                            f"recovery workflow"
                        ),
                        "actor": action["approved_by"],
                        "sequence": len(history),
                    }
                )

    # --------------------------------------------------
    # MANUAL INTERVENTIONS (newest first from the repo;
    # emitted oldest first for the timeline)
    # --------------------------------------------------

    for intervention in reversed(
        manual_interventions_repo.get_interventions_for_exception(
            connection,
            exception_id,
        )
    ):

        history.append(
            {
                "timestamp": intervention["recorded_at"],
                "event": "Manual intervention recorded",
                "detail": (
                    f"{intervention['intervention_id']} — "
                    f"{intervention['intervention_type']} with "
                    f"{intervention['external_party']}: "
                    f"{intervention['resolution_summary']}"
                ),
                "actor": intervention["recorded_by"],
                "sequence": len(history),
            }
        )

        if intervention["outcome"] == "Resolved":

            history.append(
                {
                    "timestamp": intervention["recorded_at"],
                    "event": "Exception resolved through "
                    "manual intervention",
                    "detail": (
                        f"Outcome recorded by "
                        f"{intervention['recorded_by']}"
                    ),
                    "actor": intervention["recorded_by"],
                    "sequence": len(history),
                }
            )

    # --------------------------------------------------
    # OUTCOME
    #
    # The outcome entry states the current resolution state
    # with the persisted evidence behind it: the shipment's
    # recorded estimated arrival (updated by the execution
    # engine) against the order's required delivery date.
    # Executed does not imply resolved: when the recorded
    # arrival still misses the required date, the entry
    # says so explicitly.
    # --------------------------------------------------

    if exception["resolution_status"] == "Resolved":

        history.append(
            {
                "timestamp": exception["resolved_at"],
                "event": "Exception resolved",
                "detail": (
                    f"Current status: Resolved — estimated "
                    f"arrival "
                    f"{exception['estimated_arrival']} meets "
                    f"required delivery "
                    f"{exception['required_delivery_date']} "
                    f"({exception['estimated_impact']} "
                    f"estimated impact)"
                ),
                "actor": "Adensa operational pipeline",
                "sequence": len(history),
            }
        )

    else:

        history.append(
            {
                "timestamp": None,
                "event": "Exception still open",
                "detail": (
                    f"Current status: Open — estimated "
                    f"arrival "
                    f"{exception['estimated_arrival']} still "
                    f"misses required delivery "
                    f"{exception['required_delivery_date']} "
                    f"— monitored until recovery is recorded"
                ),
                "actor": "Adensa operational pipeline",
                "sequence": len(history),
            }
        )

    # --------------------------------------------------
    # CHRONOLOGICAL ORDER: stable sort on (anchor,
    # sequence). Dated entries anchor to their stored
    # timestamp. The undated evaluation entry anchors to
    # the detection time — it always happens right after
    # detection and before any action. The undated
    # still-open outcome is the current state, not a past
    # event, so it anchors last.
    # --------------------------------------------------

    undated_anchors = {
        "Recovery options evaluated": (
            exception["detected_at"]
        ),
        "Exception still open": "9999-12-31 23:59:59",
    }

    def _sort_key(entry):

        if entry["timestamp"] is not None:

            return (
                entry["timestamp"],
                entry["sequence"],
            )

        return (
            undated_anchors.get(
                entry["event"],
                "9999-12-31 23:59:59",
            ),
            entry["sequence"],
        )

    history.sort(key=_sort_key)

    return history


def get_manual_interventions(
    connection,
    exception_id,
):
    """
    Return the recorded manual interventions for an
    exception, newest first, as plain dictionaries for any
    client.
    """

    return [
        dict(row)
        for row in (
            manual_interventions_repo.get_interventions_for_exception(
                connection,
                exception_id,
            )
        )
    ]


# ==================================================
# AI DECISION SUPPORT (ADVISORY)
# ==================================================

def build_decision_brief_evidence(
    connection,
    exception_id,
):
    """
    Compose the structured evidence an advisory AI provider
    receives: exception facts, the deterministic assessment
    (recommendation, alternatives, rationale) and the
    persisted operational history.

    Every value is established operational data read through
    the existing service functions — nothing is invented for
    the AI layer, and the AI layer receives nothing the
    planner cannot already see in the investigation view.
    Returns None when the exception does not exist.
    """

    exception = get_exception_context(
        connection,
        exception_id,
    )

    if exception is None:
        return None

    assessment = get_recovery_assessment(
        connection,
        exception_id,
    )

    history = get_exception_history(
        connection,
        exception_id,
    ) or []

    return {
        "exception": exception,
        "recommendation": (
            assessment["recommendation"]
            if assessment
            else None
        ),
        "alternatives": (
            assessment["alternatives"]
            if assessment
            else []
        ),
        "rationale": (
            assessment.get("rationale")
            if assessment
            else None
        ),
        "sustainability": get_sustainability_comparison(
            connection,
            exception_id,
        ),
        "history": history,
    }


def get_decision_brief(
    connection,
    exception_id,
    provider=None,
):
    """
    Produce the planner-facing AI decision brief for one
    exception.

    Advisory layer only. The provider receives the structured
    deterministic evidence and must return contract-valid
    output; it can never change operational state because it
    never touches the engines, the repositories or the
    connection, and the brief is never persisted. A brief that
    mentions identifiers absent from the evidence, claims an
    approved/executed/resolved action, or violates the output
    contract is rejected, and the caller receives the honest
    unavailable state instead of unverified text.

    Failure behaviour is total: missing evidence, a provider
    error or an invalid brief all return the structured
    unavailable state and never raise — investigation, the
    deterministic recommendation, and every workflow action
    keep working exactly as before.

    provider: injectable for testing. Defaults to the module
    default (resolved at call time so tests can replace it).
    No provider call happens unless the caller asks for a
    brief: the control tower, inbox and investigation views
    never trigger one automatically.
    """

    evidence = build_decision_brief_evidence(
        connection,
        exception_id,
    )

    if evidence is None:
        return unavailable_brief(
            "Exception not found — no decision brief "
            "available."
        )

    recommendation = evidence["recommendation"]

    if recommendation is None:
        return unavailable_brief(
            "No deterministic recommendation exists for this "
            "exception, so there is no decision to explain. "
            "The exception remains open for manual "
            "intervention."
        )

    if provider is None:
        provider = DEFAULT_PROVIDER

    try:

        raw_brief = provider(evidence)

        return validate_decision_brief(
            raw_brief,
            evidence,
        )

    except (
        AiProviderError,
        BriefValidationError,
    ) as error:

        return unavailable_brief(
            f"AI decision brief unavailable ({error}). "
            "Deterministic recommendation remains available."
        )


# ==================================================
# SUSTAINABILITY IMPACT (INFORMATIONAL)
# ==================================================

def get_sustainability_comparison(
    connection,
    exception_id,
):
    """
    Estimated transport emissions for an exception's
    deterministic recommendation and its feasible
    alternatives.

    Purely informational decision support (Checkpoint V): the
    calculation uses the persisted shipment weight and route
    distance plus the configured prototype emissions factors,
    and it never influences the recommendation, the scores,
    the confidence or any workflow state.

    Returns None when the exception or the deterministic
    recommendation does not exist (nothing to compare),
    otherwise the structured comparison projection from the
    sustainability module — including honest per-option
    unavailable records when an estimate cannot be produced.
    """

    exception_context = get_exception_context(
        connection,
        exception_id,
    )

    if exception_context is None:
        return None

    assessment = get_recovery_assessment(
        connection,
        exception_id,
    )

    if (
        assessment is None
        or assessment.get("recommendation") is None
    ):
        return None

    inputs = shipments_repo.get_shipment_emissions_inputs(
        connection,
        exception_context["shipment_id"],
    )

    if inputs is None:
        return {
            "status": "unavailable",
            "reason": "Shipment record not found.",
        }

    return build_sustainability_comparison(
        inputs["weight_kg"],
        inputs["distance_km"],
        [
            assessment["recommendation"],
            *assessment["alternatives"],
        ],
    )


# ==================================================
# DATA-ARRIVAL SIMULATION
# ==================================================

def run_data_arrival_simulation(connection):
    """
    Create one deterministic simulated shipment arrival.

    The simulation represents new operational data
    arriving: it creates ONLY the arrival records
    (shipment + shipment events) through the simulation
    module and repositories.

    It never creates exceptions, recovery options,
    recommendations or recovery actions, and it never
    calls the operational refresh: detecting and
    processing the arrival is the explicit job of
    run_operational_refresh(), which the user triggers
    separately.

    Returns the arrival summary dictionary from the
    simulation module, or None when the database
    contains no operational data to derive the scenario
    from.
    """

    return create_simulated_arrival(connection)


# ==================================================
# CONTROL-TOWER SUMMARY
# ==================================================

# ==================================================
# OPERATIONAL STATE CLASSIFICATION (Checkpoint S)
# ==================================================

def classify_investigation_state(
    connection,
    exception_id,
):
    """
    Classify an investigated exception's current operational
    state from persisted evidence only, so the planner can
    distinguish what needs what kind of attention.

    States (mutually exclusive, checked in order):

    - 'Resolved': the persisted resolution status is
      Resolved (via system execution or a recorded manual
      intervention outcome).
    - 'Awaiting execution': the latest recovery action is
      Approved — a human has decided; execution remains.
    - 'Executed — still open': the latest recovery action
      is Executed but the exception remains open, with the
      persisted arrival-versus-required evidence for why it
      is still open. This situation requires follow-up.
    - 'Decision required': the latest recovery action is
      Pending Approval.
    - 'No system recovery available': no recovery action
      exists (no feasible system recovery was found, or
      none was generated).

    Returns None when the exception does not exist. No
    state is invented: every branch reads a persisted
    column, and the follow-up reason quotes the recorded
    dates rather than a vague verdict.
    """

    exception = exceptions_repo.get_exception_resolution_status(
        connection,
        exception_id,
    )

    if exception is None:
        return None

    if exception["resolution_status"] == "Resolved":

        return {
            "state": "Resolved",
            "follow_up_required": False,
            "reason": (
                "The persisted operational evidence records "
                "this exception as resolved."
            ),
        }

    action = (
        recovery_actions_repo
        .get_latest_action_for_exception(
            connection,
            exception_id,
        )
    )

    if action is None:

        return {
            "state": "No system recovery available",
            "follow_up_required": False,
            "reason": (
                "No system recovery action exists for this "
                "exception."
            ),
        }

    if action["status"] == APPROVED:

        return {
            "state": "Awaiting execution",
            "follow_up_required": False,
            "reason": (
                f"Recovery action {action['action_id']} has "
                f"been approved and is ready for execution."
            ),
        }

    if action["status"] == EXECUTED:

        execution = recovery_actions_repo.get_execution_result(
            connection,
            action["action_id"],
        )

        return {
            "state": "Executed — still open",
            "follow_up_required": True,
            "reason": (
                f"Recovery executed, but estimated arrival "
                f"{execution['estimated_arrival']} remains "
                f"later than required delivery "
                f"{execution['required_delivery_date']}. "
                f"Exception remains open after recovery "
                f"execution."
            ),
        }

    return {
        "state": "Decision required",
        "follow_up_required": False,
        "reason": (
            f"Recovery action {action['action_id']} is "
            f"awaiting a planner approval or rejection "
            f"decision."
        ),
    }


def get_follow_up_queue(
    connection,
    limit=10,
):
    """
    Return the follow-up work queue: open exceptions whose
    recovery has already been executed without resolving
    them, newest detection first, with the factual reason
    for each entry.

    Bounded work-queue surface (Checkpoint P semantics
    apply): the full-population count of this population is
    reported separately by get_control_tower_summary via
    count_open_follow_up_required.
    """

    rows = exceptions_repo.get_follow_up_required_exceptions(
        connection,
        limit,
    )

    queue = []

    for row in rows:

        queue.append(
            {
                "exception_id": row["exception_id"],
                "severity": row["severity"],
                "exception_type": row["exception_type"],
                "detected_at": row["detected_at"],
                "action_id": row["action_id"],
                "executed_at": row["executed_at"],
                "estimated_arrival": row["estimated_arrival"],
                "required_delivery_date": row[
                    "required_delivery_date"
                ],
                "actionable": row["feasible_option_count"] > 0,
                "reason": (
                    f"Recovery {row['action_id']} executed "
                    f"{row['executed_at']}, but estimated "
                    f"arrival {row['estimated_arrival']} "
                    f"remains later than required delivery "
                    f"{row['required_delivery_date']}."
                ),
            }
        )

    return queue


def get_control_tower_summary(
    connection,
    resolved_limit=10,
):
    """
    Compose the operational control-tower projection: the
    at-a-glance state of the open exception population and
    the most recently resolved outcomes.

    Aggregation/projection only:

    - counts come from the existing repository reads
      (the same reads behind the dashboard metrics and the
      workflow-action status counts);
    - the actionable/monitoring split is derived from the
      feasible-option counts ALREADY carried by the inbox
      rows (get_exception_inbox) — feasibility is never
      recomputed here. The two counts partition the BOUNDED
      inbox work-queue surface (actionable + monitoring =
      the visible inbox row count), not the full open
      population behind the inbox cap;
    - a resolved exception's path is reported only where
      recorded evidence establishes it: an executed recovery
      action for the exception (system-resolved) or a manual
      intervention record (manually resolved). Without such
      evidence the neutral "Resolved" is reported.

    Does not replace get_dashboard_metrics (the external
    API contract); this is the richer internal view the
    control-tower UI renders.
    """

    inbox = get_exception_inbox(connection)

    # The inbox is the bounded operational-work surface
    # (the first rows of the open-exception work queue), so
    # these two counts describe the population the planner
    # can actually discover and act on — NOT the full open
    # population behind the inbox cap. They partition the
    # visible queue: actionable rows (feasible recovery
    # available) + monitoring rows (no feasible recovery)
    # = the inbox row count. Both split numbers come from
    # the feasible-option counts ALREADY carried by the
    # inbox rows; feasibility is never recomputed here.
    actionable = sum(
        1
        for row in inbox
        if row["feasible_option_count"] > 0
    )

    monitoring = len(inbox) - actionable

    recently_resolved = [
        dict(row)
        for row in exceptions_repo.get_recently_resolved_exceptions(
            connection,
            resolved_limit,
        )
    ]

    for resolved in recently_resolved:

        exception_id = resolved["exception_id"]

        actions = recovery_actions_repo.get_actions_for_exception(
            connection,
            exception_id,
        )

        if any(
            action["status"] == EXECUTED
            for action in actions
        ):

            resolved["resolution_path"] = (
                "System-executed recovery"
            )

            continue

        interventions = (
            manual_interventions_repo
            .get_interventions_for_exception(
                connection,
                exception_id,
            )
        )

        if interventions:

            resolved["resolution_path"] = (
                "Manually resolved"
            )

        else:

            resolved["resolution_path"] = "Resolved"

    return {
        "open_exceptions":
            exceptions_repo.count_open_exceptions(connection),
        "actionable_exceptions": actionable,
        "monitoring_exceptions": monitoring,
        "pending_approvals":
            recovery_actions_repo.count_actions_by_status(
                connection,
                status=PENDING_APPROVAL,
            ),
        "awaiting_execution":
            recovery_actions_repo.count_actions_by_status(
                connection,
                status=APPROVED,
            ),
        "critical_exceptions":
            exceptions_repo
            .count_open_critical_exceptions(connection),
        "follow_up_required":
            exceptions_repo
            .count_open_follow_up_required(connection),
        "follow_up_queue": get_follow_up_queue(
            connection,
            resolved_limit,
        ),
        "recently_resolved": recently_resolved,
    }
