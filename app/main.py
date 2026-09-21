import streamlit as st

from app import services
from app.database import get_connection
from app.errors import RecoveryWorkflowError
from app.workflow_engine import (
    PENDING_APPROVAL,
    APPROVED,
    REJECTED,
    EXECUTED,
)


st.set_page_config(
    page_title="Adensa Digital",
    page_icon="🌍",
    layout="wide",
)


def scroll_to_workflow_outcome():
    """
    Scroll the browser to the latest workflow outcome section.

    Streamlit reruns the application after state-changing actions.
    This JavaScript brings the user's attention back to the result.
    """
    st.markdown(
        """
        <script>
        setTimeout(function() {
            const element = window.parent.document.getElementById(
                "workflow-outcome-anchor"
            );

            if (element) {
                element.scrollIntoView({
                    behavior: "smooth",
                    block: "start"
                });
            }
        }, 150);
        </script>
        """,
        unsafe_allow_html=True,
    )




def _initialize_operational_session_state():
    """Initialize the UI session-state keys (original defaults)."""

    # --------------------------------------------------
    # SESSION STATE
    # --------------------------------------------------

    if "selected_exception_id" not in st.session_state:
        st.session_state.selected_exception_id = None

    if "last_workflow_outcome" not in st.session_state:
        st.session_state.last_workflow_outcome = None

    if "scroll_to_outcome" not in st.session_state:
        st.session_state.scroll_to_outcome = False

    if "last_refresh_result" not in st.session_state:
        st.session_state.last_refresh_result = None

    if "last_simulation_result" not in st.session_state:
        st.session_state.last_simulation_result = None

    if "focus_exception_id" not in st.session_state:
        st.session_state.focus_exception_id = None

    if "last_manual_resolution" not in st.session_state:
        st.session_state.last_manual_resolution = None


def _render_sidebar_sections(connection):
    """Sidebar simulation/refresh controls and feedback."""

    with st.sidebar:

        st.header("Simulation")

        if st.button(
            "Simulate Shipment Arrival",
            key="simulate_shipment_arrival",
        ):

            with st.spinner(
                "Creating simulated shipment arrival..."
            ):

                st.session_state.last_simulation_result = (
                    services.run_data_arrival_simulation(
                        connection,
                    )
                )

            st.rerun()

        if st.session_state.last_simulation_result:

            simulation_result = (
                st.session_state.last_simulation_result
            )

            st.success(
                f"{simulation_result['shipment_id']} arrived · "
                f"{simulation_result['event_count']} events recorded"
            )

        st.header("Operations")

        if st.button(
            "Refresh Operations Pipeline",
            key="refresh_operations_pipeline",
        ):

            with st.spinner(
                "Running detect → options → actions..."
            ):

                st.session_state.last_refresh_result = (
                    services.run_operational_refresh(
                        connection,
                    )
                )

            st.rerun()

        if st.session_state.last_refresh_result:

            refresh_result = (
                st.session_state.last_refresh_result
            )

            st.success(
                f"Detected {refresh_result['new_exceptions']} "
                f"new exceptions · "
                f"{refresh_result['new_options']} "
                f"new recovery options · "
                f"{refresh_result['new_actions']} "
                f"new workflow actions"
            )

            # Surface the identities of the exceptions the
            # run has just detected; a single new exception
            # becomes the focused investigation target.
            new_exception_ids = refresh_result[
                "new_exception_ids"
            ]

            if new_exception_ids:

                st.caption(
                    "New exceptions: "
                    + ", ".join(new_exception_ids)
                )

                if len(new_exception_ids) == 1:

                    st.session_state.focus_exception_id = (
                        new_exception_ids[0]
                    )


def render_title():
    """Application title and workflow caption."""

    st.title("🌍 Adensa Digital")
    st.subheader("Supply Chain Exception & Recovery Platform")

    st.caption(
        "Detect → Analyze → Recommend → Approve → Execute → Resolve"
    )


def render_manual_resolution_banner():
    """Banner summarising the most recent manual resolution."""

    if st.session_state.last_manual_resolution:

        manual_resolution = (
            st.session_state.last_manual_resolution
        )

        st.success(
            f"**Manual resolution recorded** — "
            f"{manual_resolution['intervention_id']} · "
            f"{manual_resolution['intervention_type']}"
        )

        banner_col1, banner_col2, banner_col3 = st.columns(3)

        with banner_col1:

            st.write(
                f"**External party:** "
                f"{manual_resolution['external_party']}"
            )

            st.write(
                f"**Resolution:** "
                f"{manual_resolution['resolution_summary']}"
            )

            st.write(
                f"**Outcome:** "
                f"{manual_resolution['outcome']}"
            )

        with banner_col2:

            if manual_resolution[
                "new_expected_delivery"
            ]:

                st.write(
                    f"**New expected delivery:** "
                    f"{manual_resolution['new_expected_delivery']}"
                )

            if manual_resolution["notes"]:

                st.write(
                    f"**Notes:** "
                    f"{manual_resolution['notes']}"
                )

        with banner_col3:

            st.write(
                f"**Recorded by:** "
                f"{manual_resolution['recorded_by']}"
            )

            st.write(
                f"**Recorded at:** "
                f"{manual_resolution['recorded_at']}"
            )

        if (
            manual_resolution["exception_status"]
            == "Resolved"
        ):

            st.info(
                "Resolved through manual intervention."
            )

        else:

            st.warning(
                "The intervention was recorded; the "
                "exception remains open and monitored."
            )


def render_control_tower(connection, summary):
    """Control-tower summary metrics (full + bounded populations)."""

    # summary is composed once in main() and shared with the
    # work-queue sections, exactly as the original monolith
    # shared the local variable.

    # Attention-first hierarchy: the metrics that answer
    # "where do I act now?" lead; population/surface context
    # metrics follow. Labels and population semantics are
    # unchanged (Checkpoint P rules preserved).
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Pending Decisions",
            summary["pending_approvals"],
            help=(
                "Recovery actions awaiting a planner "
                "approval or rejection decision."
            ),
        )

    with col2:
        st.metric(
            "Awaiting Execution",
            summary["awaiting_execution"],
            help=(
                "Approved recovery actions not yet executed."
            ),
        )

    with col3:
        st.metric(
            "Follow-up Required",
            summary["follow_up_required"],
            help=(
                "Open exceptions whose recovery has already "
                "been executed without resolving them, "
                "across the entire open population."
            ),
        )

    with col4:
        st.metric(
            "Critical Open",
            summary["critical_exceptions"],
            help=(
                "Open exceptions with Critical severity, "
                "across the entire open population."
            ),
        )

    col5, col6, col7, col8 = st.columns(4)

    with col5:
        st.metric(
            "Open Exceptions",
            summary["open_exceptions"],
            help=(
                "All open exceptions in the operational "
                "database."
            ),
        )

    with col6:
        st.metric(
            "Actionable",
            summary["actionable_exceptions"],
            help=(
                "Open exceptions with a feasible recovery "
                "option, within the Exception Inbox work "
                "queue (bounded surface — not the entire "
                "open population)."
            ),
        )

    with col7:
        st.metric(
            "Monitoring",
            summary["monitoring_exceptions"],
            help=(
                "Inbox work-queue exceptions without a "
                "feasible recovery option (bounded surface "
                "— not the entire open population)."
            ),
        )

    with col8:
        st.metric(
            "Recently Resolved",
            len(summary["recently_resolved"]),
            help=(
                "Most recent resolutions shown in the "
                "resolved queue below (bounded view)."
            ),
        )


def render_latest_workflow_outcome():
    """Most recent approve/reject/execute outcome."""

    if st.session_state.last_workflow_outcome:

        outcome = st.session_state.last_workflow_outcome

        st.markdown(
            '<div id="workflow-outcome-anchor"></div>',
            unsafe_allow_html=True,
        )

        st.header("Latest Workflow Outcome")

        if outcome["success"]:

            st.success(
                outcome["message"]
            )

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "Action",
                    outcome["action_id"],
                )

            with col2:
                st.metric(
                    "Shipment",
                    outcome["shipment_id"],
                )

            with col3:
                st.metric(
                    "Exception Status",
                    outcome["exception_status"],
                )

            detail_col1, detail_col2 = st.columns(2)

            with detail_col1:

                st.write(
                    f"**Previous Mode:** "
                    f"{outcome['previous_mode']}"
                )

                st.write(
                    f"**New Mode:** "
                    f"{outcome['new_mode']}"
                )

                st.write(
                    f"**Carrier:** "
                    f"{outcome['carrier_id']}"
                )

                st.write(
                    f"**Recovery Event:** "
                    f"{outcome['recovery_event']}"
                )

            with detail_col2:

                st.write(
                    f"**New ETA:** "
                    f"{outcome['new_eta']}"
                )

                st.write(
                    f"**Required Delivery:** "
                    f"{outcome['required_delivery']}"
                )

                if outcome["exception_status"] == "Resolved":

                    st.info(
                        "The recovery action was executed and "
                        "the shipment now meets the required "
                        "delivery date."
                    )

                else:

                    st.warning(
                        "The recovery action was executed, "
                        "but the shipment still requires "
                        "further recovery."
                    )

        else:

            st.error(
                outcome["message"]
            )

        st.divider()


def render_work_queues(connection, summary):
    """Follow-up-required and recently-resolved queues."""

    # Unconditional section boundaries: the section is opened
    # and closed by dividers regardless of queue contents, so
    # the surrounding flow stays consistent when both queues
    # are empty.
    st.divider()

    follow_up_queue = summary["follow_up_queue"]

    if follow_up_queue:

        st.header("Follow-up Required")

        st.caption(
            "Executed recoveries that did not resolve the "
            "exception — the recorded arrival still misses "
            "the required delivery date."
        )

        follow_up_rows = [
            {
                "Exception": (
                    entry["exception_id"]
                ),
                "Severity": entry["severity"],
                "Action": entry["action_id"],
                "Evidence": entry["reason"],
            }
            for entry in follow_up_queue
        ]

        st.dataframe(
            follow_up_rows,
            hide_index=True,
            width="stretch",
        )

        st.caption(
            "Bounded view of the follow-up work queue; the "
            "Follow-up Required count above is the full "
            "open population."
        )

    recently_resolved = summary["recently_resolved"]

    if recently_resolved:

        st.header("Recently Resolved")

        resolved_rows = []

        for resolved in recently_resolved:

            resolved_rows.append(
                {
                    "Exception": (
                        resolved["exception_id"]
                    ),
                    "Type": (
                        resolved["exception_type"]
                    ),
                    "Severity": (
                        resolved["severity"]
                    ),
                    "Resolution Path": (
                        resolved["resolution_path"]
                    ),
                    "Resolved At": (
                        resolved["resolved_at"]
                    ),
                }
            )

        st.dataframe(
            resolved_rows,
            hide_index=True,
            width="stretch",
        )

        st.caption(
            "The most recent outcomes (bounded view, newest "
            "first). Open an exception's Operational "
            "History for the full timeline."
        )

    st.divider()


def render_exception_inbox(connection):
    """Exception inbox: bounded work queue and exception selection."""

    st.header("Exception Inbox")

    st.caption(
        "Bounded operational work queue (newest actionable "
        "work first) — the Actionable and Monitoring "
        "counts above describe this surface, not the full "
        "open population."
    )

    exceptions = services.get_exception_inbox(
        connection,
    )

    if not exceptions:

        st.success(
            "No open shipment exceptions currently require attention."
        )

        return

    # Triage state: the actionability verdict from the
    # existing option/action data — so the operator can
    # distinguish exceptions requiring action from exceptions
    # under monitoring (unchanged semantics).
    def _triage_state(row):
        if row["executed_still_open"]:
            return "Follow-up required"
        if row["feasible_option_count"]:
            return "Actionable"
        return "No feasible recovery"

    # Selection universe: the inbox identifiers, in the
    # repository's deterministic actionable-first order.
    exception_options = [
        row["exception_id"]
        for row in exceptions
    ]

    # Focus a newly detected exception after an
    # operational refresh; otherwise preserve the
    # currently selected exception when possible.
    focus_exception_id = (
        st.session_state.focus_exception_id
    )

    if (
        focus_exception_id
        and focus_exception_id in exception_options
    ):
        st.session_state.selected_exception_id = (
            focus_exception_id
        )

    st.session_state.focus_exception_id = None

    if (
        st.session_state.selected_exception_id
        not in exception_options
    ):
        st.session_state.selected_exception_id = (
            exception_options[0]
        )

    # Work-queue table: the scannable operational surface.
    # One row per inbox entry, in the repository's existing
    # actionable-first ordering, with the fields a planner
    # triages on. All values come from the inbox service —
    # nothing is recomputed or re-queried here.
    queue_rows = [
        {
            "Exception": row["exception_id"],
            "Severity": row["severity"],
            "Issue": row["exception_type"],
            "Mode": row["transport_mode"],
            "Location": row["current_location"],
            "Required": row["required_delivery_date"],
            "State": _triage_state(row),
        }
        for row in exceptions
    ]

    st.dataframe(
        queue_rows,
        hide_index=True,
        width="stretch",
        key="exception_work_queue",
    )

    st.caption(
        "Select an exception below to investigate it in the "
        "workspace underneath."
    )

    # Selection control: short, stable labels (identifier
    # plus the recorded issue) rather than the overloaded
    # triage string — the operational fields now live in the
    # queue table above.
    label_by_id = {
        row["exception_id"]:
        f"{row['exception_id']} - {row['exception_type']}"
        for row in exceptions
    }

    selected_display = st.selectbox(
        "Select an exception to investigate",
        list(label_by_id.values()),
        index=list(label_by_id.values()).index(
            label_by_id[
                st.session_state.selected_exception_id
            ]
        ),
    )

    st.session_state.selected_exception_id = (
        selected_display.split(" - ")[0]
    )

    return True


def _selected_inbox_exception(connection):
    """
    The inbox row of the exception currently selected for
    investigation. The original monolith passed this row as a
    local variable; sections now re-read it through the same
    service the inbox uses.
    """

    selected_exception_id = st.session_state.selected_exception_id

    return next(
        row
        for row in services.get_exception_inbox(connection)
        if row["exception_id"] == selected_exception_id
    )


def render_exception_context(connection):
    """Shipment/order context for the selected exception."""

    selected_exception_id = st.session_state.selected_exception_id

    context = services.get_exception_context(
        connection,
        selected_exception_id,
    )

    if context:

        st.caption(
            f"Investigating {context['route']} · "
            f"Shipment {context['shipment_id']} is "
            f"{context['shipment_status'].lower()} · "
            f"Order {context['order_id']} for "
            f"{context['customer_name']} "
            f"({context['customer_id']})"
        )

        # The recorded operational issue, exactly as the
        # detection pipeline persisted it.
        st.info(
            f"**{context['exception_type']}** — "
            f"{context['description']}"
        )


def render_exception_details(connection):
    """Operational detail columns for the selected exception."""

    selected_exception_id = st.session_state.selected_exception_id
    selected_exception = _selected_inbox_exception(connection)

    st.subheader("Exception Details")

    detail_col1, detail_col2, detail_col3 = st.columns(3)

    with detail_col1:

        st.write(
            f"**Exception:** "
            f"{selected_exception['exception_id']}"
        )

        st.write(
            f"**Shipment:** "
            f"{selected_exception['shipment_id']}"
        )

        st.write(
            f"**Exception Type:** "
            f"{selected_exception['exception_type']}"
        )

        st.write(
            f"**Severity:** "
            f"{selected_exception['severity']}"
        )

    with detail_col2:

        st.write(
            f"**Priority:** "
            f"{selected_exception['priority']}"
        )

        st.write(
            f"**Transport Mode:** "
            f"{selected_exception['transport_mode']}"
        )

        st.write(
            f"**Current Location:** "
            f"{selected_exception['current_location']}"
        )

    with detail_col3:

        st.write(
            f"**Estimated Arrival:** "
            f"{selected_exception['estimated_arrival']}"
        )

        st.write(
            f"**Required Delivery:** "
            f"{selected_exception['required_delivery_date']}"
        )

        st.write(
            f"**Estimated Impact:** "
            f"{selected_exception['estimated_impact']}"
        )


def render_decision_support(connection):
    """
    Decision engine, recommendation, rationale, sustainability,
    AI brief and workflow action for the selected exception.
    """

    selected_exception_id = st.session_state.selected_exception_id

    st.header("Decision Engine")

    assessment = services.get_recovery_assessment(
        connection,
        selected_exception_id,
    )

    if (
        assessment is None
        or assessment.get("recommendation") is None
    ):

        # --------------------------------------------------
        # RECOVERY ASSESSMENT
        #
        # No recommendation is itself an operational
        # result: the evaluated options explain why the
        # decision engine cannot currently recommend a
        # recovery. The exception remains open and
        # monitored.
        # --------------------------------------------------

        st.subheader("Recovery Assessment")

        st.info(
            "No recovery recommendation is currently "
            "available."
        )

        evaluated_options = (
            assessment.get("evaluated_options", [])
            if assessment
            else []
        )

        if evaluated_options:

            st.write(
                "The decision engine evaluated the "
                "following recovery options, but none "
                "satisfied the operational constraints:"
            )

            assessment_rows = []

            for option in evaluated_options:

                assessment_rows.append(
                    {
                        "Option": (
                            option["option_id"]
                        ),
                        "Mode": (
                            option["transport_mode"]
                        ),
                        "Carrier": (
                            option["carrier_id"]
                        ),
                        "Cost (€)": (
                            f"{option['estimated_cost']:,.2f}"
                        ),
                        "Transit (days)": (
                            f"{option['estimated_transit_days']:.0f}"
                        ),
                        "Risk": (
                            f"{option['risk_score']:.0f}"
                        ),
                        "Result": (
                            "Infeasible"
                            if not option["feasible"]
                            else "Feasible"
                        ),
                    }
                )

            st.dataframe(
                assessment_rows,
                hide_index=True,
                width="stretch",
            )

        st.caption(
            "This exception remains open and is monitored."
        )

        # --------------------------------------------------
        # MANUAL RESOLUTION (HUMAN-DRIVEN RECOVERY)
        # --------------------------------------------------

        st.subheader("Human Intervention")

        st.write(
            "No system recovery option currently satisfies "
            "the operational constraints. If the planner "
            "resolved the issue externally, the outcome "
            "can be recorded here."
        )

        interventions = services.get_manual_interventions(
            connection,
            selected_exception_id,
        )

        if interventions:

            st.caption(
                "Recorded interventions"
            )

            for intervention in interventions:

                with st.expander(
                    f"{intervention['intervention_id']} — "
                    f"{intervention['intervention_type']}"
                ):

                    st.write(
                        f"**External party:** "
                        f"{intervention['external_party']}"
                    )

                    st.write(
                        f"**Resolution:** "
                        f"{intervention['resolution_summary']}"
                    )

                    if intervention[
                        "new_expected_delivery"
                    ]:

                        st.write(
                            f"**New expected delivery:** "
                            f"{intervention['new_expected_delivery']}"
                        )

                    st.write(
                        f"**Outcome:** "
                        f"{intervention['outcome']}"
                    )

                    if intervention["notes"]:

                        st.write(
                            f"**Notes:** "
                            f"{intervention['notes']}"
                        )

                    st.write(
                        f"**Recorded by:** "
                        f"{intervention['recorded_by']} "
                        f"at {intervention['recorded_at']}"
                    )

                    if (
                        intervention["outcome"]
                        == "Resolved"
                    ):

                        st.success(
                            "Resolved through manual "
                            "intervention."
                        )

        with st.expander(
            "Record Manual Resolution"
        ):

            intervention_type = st.selectbox(
                "Intervention method",
                services.INTERVENTION_TYPES,
                key=f"intervention_type_{selected_exception_id}",
            )

            external_party = st.text_input(
                "External party",
                key=f"intervention_party_{selected_exception_id}",
            )

            resolution_summary = st.text_area(
                "Agreed resolution",
                key=f"intervention_resolution_{selected_exception_id}",
            )

            new_expected_delivery = st.text_input(
                "New expected delivery (optional, YYYY-MM-DD)",
                key=f"intervention_eta_{selected_exception_id}",
            )

            outcome = st.selectbox(
                "Outcome",
                (
                    "Resolved",
                    "Still Open",
                ),
                key=f"intervention_outcome_{selected_exception_id}",
            )

            notes = st.text_area(
                "Notes (optional)",
                key=f"intervention_notes_{selected_exception_id}",
            )

            recorder = st.text_input(
                "Recorded by",
                key=f"intervention_recorder_{selected_exception_id}",
            )

            if st.button(
                "Save Manual Resolution",
                type="primary",
                key=f"intervention_save_{selected_exception_id}",
            ):

                if (
                    not external_party.strip()
                    or not resolution_summary.strip()
                    or not recorder.strip()
                ):

                    st.warning(
                        "External party, agreed resolution "
                        "and recorder are required."
                    )

                else:

                    try:

                        st.session_state.last_manual_resolution = services.record_manual_resolution(
                            connection,
                            selected_exception_id,
                            intervention_type,
                            external_party.strip(),
                            resolution_summary.strip(),
                            recorder.strip(),
                            outcome,
                            new_expected_delivery=(
                                new_expected_delivery.strip()
                                or None
                            ),
                            notes=(
                                notes.strip() or None
                            ),
                        )

                        st.rerun()

                    except RecoveryWorkflowError as error:

                        st.error(
                            f"Recording failed: {error}"
                        )

    else:

        recovery = assessment["recommendation"]

        alternatives = assessment.get(
            "alternatives",
            [],
        )

        st.success(
            "Recovery recommendation available."
        )

        st.subheader("Recommended Recovery")

        recommendation_col1, recommendation_col2 = st.columns(2)

        with recommendation_col1:

            st.write(
                f"**Transport Mode:** "
                f"{recovery['transport_mode']}"
            )

            st.write(
                f"**Carrier:** "
                f"{recovery['carrier_id']}"
            )

            st.write(
                f"**Estimated Cost:** "
                f"€{recovery['estimated_cost']:,.2f}"
            )

            st.write(
                f"**Transit Time:** "
                f"{recovery['estimated_transit_days']:.0f} days"
            )

        with recommendation_col2:

            st.write(
                f"**Risk Score:** "
                f"{recovery['risk_score']:.0f}"
            )

            st.write(
                f"**Decision Score:** "
                f"{recovery['decision_score']:.2f}"
            )

            st.write(
                f"**Confidence:** "
                f"{recovery['confidence']}"
            )

            st.write(
                f"**Reason:** "
                f"{recovery['reason']}"
            )

        # --------------------------------------------------
        # ALTERNATIVES
        # --------------------------------------------------

        if alternatives:

            st.subheader("Recovery Options Comparison")

            # One comparable row per feasible option: the
            # recommendation first, then the alternatives
            # in the decision engine's own ranking. All
            # values come from the existing scoring
            # contract; nothing is recalculated here.
            comparison_options = [
                recovery,
                *alternatives,
            ]

            comparison_rows = []

            for position, option in enumerate(
                comparison_options
            ):

                comparison_rows.append(
                    {
                        "Option": (
                            "Recommended"
                            if position == 0
                            else "Alternative"
                        ),
                        "Mode": (
                            option["transport_mode"]
                        ),
                        "Carrier": (
                            option["carrier_id"]
                        ),
                        "Cost (€)": (
                            f"{option['estimated_cost']:,.2f}"
                        ),
                        "Transit (days)": (
                            f"{option['estimated_transit_days']:.0f}"
                        ),
                        "Risk": (
                            f"{option['risk_score']:.0f}"
                        ),
                        "Cost fit": (
                            f"{option['cost_score']:.0f}"
                        ),
                        "Transit fit": (
                            f"{option['transit_score']:.0f}"
                        ),
                        "Risk fit": (
                            f"{option['risk_component']:.0f}"
                        ),
                        "Priority fit": (
                            f"{option['priority_score']:.0f}"
                        ),
                        "Score": (
                            f"{option['decision_score']:.2f}"
                        ),
                    }
                )

            st.dataframe(
                comparison_rows,
                hide_index=True,
                width="stretch",
            )

            st.caption(
                "Factor scores (0–100: higher is better) come "
                "from the decision engine's benchmarks; the "
                "decision score is their weighted combination. "
                "The configured policy weights are shown below."
            )

        # --------------------------------------------------
        # RECOMMENDATION RATIONALE
        #
        # Structured, deterministic explanation of the
        # recommendation: the configured policy weights,
        # each factor's raw fit and weighted contribution
        # for the recommendation and every alternative, the
        # factual trade-offs, and the basis of the
        # confidence label. Everything comes from the
        # service projection; nothing is recomputed here.
        # --------------------------------------------------

        rationale = assessment.get("rationale")

        if rationale:

            st.subheader("Recommendation Rationale")

            weights = rationale["weights"]

            st.caption(
                "Decision policy (from application "
                "configuration): "
                f"Cost {weights['cost']:.0%} · Transit "
                f"{weights['transit']:.0%} · Risk "
                f"{weights['risk']:.0%} · Priority "
                f"{weights['priority_alignment']:.0%}. "
                "The overall decision score is the weighted "
                "combination of the four factor scores."
            )

            factor_rows = []

            for factor in rationale["factor_breakdown"]:

                factor_row = {
                    "Factor": factor["factor"],
                    "Weight": f"{factor['weight']:.0%}",
                }

                for position, value in enumerate(
                    factor["values"]
                ):

                    option_prefix = (
                        "Recommended"
                        if position == 0
                        else f"Alternative {position}"
                    )

                    factor_row[
                        f"{option_prefix} score"
                    ] = f"{value['score']:.0f}"

                    factor_row[
                        f"{option_prefix} weighted"
                    ] = f"{value['contribution']:.2f}"

                factor_rows.append(factor_row)

            st.dataframe(
                factor_rows,
                hide_index=True,
                width="stretch",
            )

            st.caption(
                "Score is the raw factor fit (0–100, higher "
                "is better); weighted is score × policy "
                "weight. The weighted contributions of one "
                "option sum to its decision score."
            )

            for trade_off in rationale["trade_offs"]:

                st.write(
                    f"**Trade-off:** "
                    f"{trade_off['transport_mode']} "
                    f"({trade_off['option_id']}) scores higher "
                    "on "
                    f"{' and '.join(trade_off['stronger_factors'])} "
                    "but the recommended option wins on the "
                    "weighted overall score."
                )

            st.caption(
                f"Recommendation confidence: "
                f"{recovery['confidence']}. "
                f"{rationale['confidence_basis']}"
            )

        # --------------------------------------------------
        # SUSTAINABILITY IMPACT (INFORMATIONAL)
        #
        # Estimated transport emissions for the
        # recommendation and its feasible alternatives,
        # computed from persisted shipment data and the
        # configured prototype factors. Purely informational
        # decision support: it never changes the
        # recommendation, the rationale above, or any
        # workflow state (Checkpoint V boundary).
        # --------------------------------------------------

        st.subheader("Sustainability Impact")

        sustainability = services.get_sustainability_comparison(
            connection,
            selected_exception_id,
        )

        if sustainability is None:

            st.caption(
                "No deterministic recommendation exists, so "
                "there is no recovery option to assess."
            )

        else:

            estimates = sustainability.get("estimates", [])

            if (
                sustainability.get("status")
                == "available"
                and estimates
            ):

                sustainability_rows = []

                for position, estimate in enumerate(
                    estimates
                ):

                    if (
                        estimate.get("status")
                        == "available"
                    ):

                        sustainability_rows.append(
                            {
                                "Option": (
                                    "Recommended"
                                    if position == 0
                                    else "Alternative"
                                ),
                                "Mode": (
                                    estimate[
                                        "transport_mode"
                                    ]
                                ),
                                "Estimated CO₂e (kg)": (
                                    f"{estimate['estimated_co2e_kg']:,.2f}"
                                ),
                            }
                        )

                    else:

                        sustainability_rows.append(
                            {
                                "Option": (
                                    "Recommended"
                                    if position == 0
                                    else "Alternative"
                                ),
                                "Mode": (
                                    estimate[
                                        "transport_mode"
                                    ]
                                ),
                                "Estimated CO₂e (kg)": (
                                    "Not available"
                                ),
                            }
                        )

                st.dataframe(
                    sustainability_rows,
                    hide_index=True,
                    width="stretch",
                )

                lowest = sustainability.get(
                    "lowest_emission_option"
                )

                if (
                    lowest
                    and lowest["option_id"]
                    != recovery['option_id']
                ):

                    st.write(
                        f"**Sustainability trade-off:** the "
                        f"lowest-emission feasible alternative "
                        f"is {lowest['transport_mode']} at "
                        f"{lowest['estimated_co2e_kg']:,.2f} "
                        "kg CO₂e — the recommendation wins on "
                        "operational fit, not on estimated "
                        "emissions."
                    )

            else:

                st.info(
                    "Sustainability estimate unavailable — "
                    "the required shipment data is missing "
                    "or invalid."
                )

            st.caption(
                sustainability.get(
                    "data_quality_note",
                    "Estimated transport emissions; "
                    "prototype methodology.",
                )
            )

        # --------------------------------------------------
        # AI DECISION BRIEF (ADVISORY)
        #
        # Optional, planner-triggered interpretation of the
        # deterministic assessment above. The AI layer can
        # only explain established evidence — it can never
        # select, approve, execute or resolve anything, and
        # a failed or invalid brief leaves this section in
        # an honest unavailable state while the
        # deterministic recommendation remains authoritative.
        # --------------------------------------------------

        st.subheader("AI Decision Brief")

        brief_state = st.session_state.get(
            "decision_brief_state"
        )

        if (
            brief_state
            and brief_state.get("exception_id")
            != selected_exception_id
        ):
            brief_state = None

        if st.button(
            "Generate AI Decision Brief",
            key=f"ai_brief_{selected_exception_id}",
        ):

            st.session_state.decision_brief_state = {
                "exception_id": selected_exception_id,
                "brief": services.get_decision_brief(
                    connection,
                    selected_exception_id,
                ),
            }

            st.rerun()

        brief_state = st.session_state.get(
            "decision_brief_state"
        )

        if (
            brief_state
            and brief_state.get("exception_id")
            == selected_exception_id
        ):

            brief = brief_state["brief"]

            if brief["status"] == "available":

                st.caption(brief["advisory_label"])

                st.write(
                    f"**Situation**\n\n"
                    f"{brief['situation_summary']}"
                )

                st.write(
                    f"**Why this option**\n\n"
                    f"{brief['recommended_action']} "
                    f"{brief['rationale']}"
                )

                st.write(
                    f"**Trade-offs**\n\n"
                    f"{brief['tradeoffs']}"
                )

                if brief["verification_points"]:

                    st.write("**Verify before acting**")

                    for point in brief[
                        "verification_points"
                    ]:

                        st.write(f"- {point}")

                st.caption(brief["disclaimer"])

            else:

                st.info(brief["message"])

        else:

            st.caption(
                "Optional AI-assisted interpretation of the "
                "deterministic assessment above. Advisory "
                "only — the deterministic recommendation "
                "remains authoritative."
            )

        st.divider()

        # --------------------------------------------------
        # WORKFLOW ACTION
        # --------------------------------------------------

        st.header("Workflow Action")

        action = services.get_latest_action(
            connection,
            selected_exception_id,
        )

        if action:

            st.write(
                f"**Action:** {action['action_id']}"
            )

            st.write(
                f"**Status:** {action['status']}"
            )

            if action["approved_by"]:

                st.write(
                    f"**Approved By:** "
                    f"{action['approved_by']}"
                )

            if action["approved_at"]:

                st.write(
                    f"**Approved At:** "
                    f"{action['approved_at']}"
                )

            if action["executed_at"]:

                st.write(
                    f"**Executed At:** "
                    f"{action['executed_at']}"
                )

            # --------------------------------------------------
            # APPROVAL / REJECTION
            # --------------------------------------------------

            if action["status"] == PENDING_APPROVAL:

                st.info(
                    "Decision required: approve to enable "
                    "execution, or reject to close this "
                    "recovery option."
                )

                approver_name = st.text_input(
                    "Approver name",
                    key=f"approver_{action['action_id']}",
                )

                approval_col, rejection_col = st.columns(2)

                with approval_col:

                    if st.button(
                        "Approve Recovery",
                        type="primary",
                        key=f"approve_{action['action_id']}",
                    ):

                        if not approver_name.strip():

                            st.warning(
                                "Enter an approver name before "
                                "approving the recovery."
                            )

                        else:

                            try:

                                st.session_state.last_workflow_outcome = services.approve_recovery(
                                    connection,
                                    action["action_id"],
                                    approver_name.strip(),
                                )

                                st.rerun()

                            except RecoveryWorkflowError as error:

                                st.error(
                                    f"Approval failed: {error}"
                                )

                with rejection_col:

                    if st.button(
                        "Reject Recovery",
                        key=f"reject_{action['action_id']}",
                    ):

                        if not approver_name.strip():

                            st.warning(
                                "Enter the reviewer name before "
                                "rejecting the recovery."
                            )

                        else:

                            try:

                                st.session_state.last_workflow_outcome = services.reject_recovery(
                                    connection,
                                    action["action_id"],
                                    approver_name.strip(),
                                )

                                st.rerun()

                            except RecoveryWorkflowError as error:

                                st.error(
                                    f"Rejection failed: {error}"
                                )

            # --------------------------------------------------
            # EXECUTION
            # --------------------------------------------------

            elif action["status"] == APPROVED:

                st.info(
                    "This recovery action has been approved "
                    "and is ready for execution."
                )

                if st.button(
                    "Execute Recovery",
                    type="primary",
                    key=f"execute_{action['action_id']}",
                ):

                    try:

                        st.session_state.last_workflow_outcome = services.execute_approved_recovery(
                            connection,
                            action["action_id"],
                        )

                        # Tell the next Streamlit run to bring
                        # the outcome into view.
                        st.session_state.scroll_to_outcome = True

                        st.rerun()

                    except RecoveryWorkflowError as error:

                        st.session_state.last_workflow_outcome = {
                            "success": False,
                            "message": (
                                f"Recovery execution failed: "
                                f"{error}"
                            ),
                        }

                        st.session_state.scroll_to_outcome = True

                        st.rerun()

            # --------------------------------------------------
            # TERMINAL STATES
            # --------------------------------------------------

            elif action["status"] == EXECUTED:

                state = services.classify_investigation_state(
                    connection,
                    selected_exception_id,
                )

                if state and state["follow_up_required"]:

                    st.warning(
                        f"Executed — still open. "
                        f"{state['reason']}"
                    )

                else:

                    st.success(
                        "This recovery action has already "
                        "been executed."
                    )

            elif action["status"] == REJECTED:

                # The workflow engine stores the rejection
                # actor and timestamp in the action's
                # approval audit fields.
                st.warning(
                    "This recovery action was rejected "
                    f"by {action['approved_by']} "
                    f"at {action['approved_at']}."
                )

        else:

            st.info(
                "No workflow action currently exists for this exception."
            )


def render_operational_history(connection):
    """Chronological operational history for the selection."""

    selected_exception_id = st.session_state.selected_exception_id

    st.divider()

    st.header("Operational History")

    st.caption(
        "Chronological record built from real persisted "
        "events — detection, option evaluation, decisions, "
        "executions and recorded interventions."
    )

    history = services.get_exception_history(
        connection,
        selected_exception_id,
    )

    if history:

        history_rows = [
            {
                "When": (
                    entry["timestamp"]
                    if entry["timestamp"]
                    else "—"
                ),
                "Event": entry["event"],
                "Detail": entry["detail"],
                "Actor": entry["actor"],
            }
            for entry in history
        ]

        st.dataframe(
            history_rows,
            width="stretch",
            hide_index=True,
        )

    else:

        st.info(
            "No operational history is available for "
            "this exception."
        )


def main():
    """
    Orchestrate the Adensa operational UI.

    The render path is decomposed into focused presentation
    functions while preserving the original section order,
    dividers and single-connection lifecycle (open once at
    the start of the run, close in a finally).
    """

    _initialize_operational_session_state()

    connection = get_connection()

    try:

        _render_sidebar_sections(connection)

        render_title()

        render_manual_resolution_banner()

        st.divider()

        summary = services.get_control_tower_summary(
            connection,
        )

        render_control_tower(connection, summary)

        st.divider()
        render_latest_workflow_outcome()

        # The inbox leads the operational flow: the planner
        # picks the exception to work before scanning the
        # secondary follow-up/resolved queues.
        if not render_exception_inbox(connection):

            # No open exceptions: the render path stops here,
            # matching the original quiet-database behavior.

            return

        render_work_queues(connection, summary)

        render_exception_context(connection)

        render_exception_details(connection)

        st.divider()
        render_decision_support(connection)

        render_operational_history(connection)

        if st.session_state.scroll_to_outcome:

            st.session_state.scroll_to_outcome = False

            scroll_to_workflow_outcome()

    finally:

        connection.close()


if __name__ == "__main__":
    main()