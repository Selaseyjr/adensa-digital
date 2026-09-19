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


def main():

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

    # --------------------------------------------------
    # DATABASE CONNECTION
    # --------------------------------------------------

    connection = get_connection()

    try:

        # --------------------------------------------------
        # OPERATIONS SIDEBAR
        # --------------------------------------------------

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

            if st.session_state.last_manual_resolution:

                manual_resolution = (
                    st.session_state.last_manual_resolution
                )

                st.success(
                    f"{manual_resolution['intervention_id']} recorded · "
                    f"{manual_resolution['intervention_type']} · "
                    f"{manual_resolution['outcome']}"
                )

        # --------------------------------------------------
        # HEADER
        # --------------------------------------------------

        st.title("🌍 Adensa Digital")
        st.subheader("Supply Chain Exception & Recovery Platform")

        st.caption(
            "Detect → Analyze → Recommend → Approve → Execute → Resolve"
        )

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

        st.divider()

        # --------------------------------------------------
        # CONTROL-TOWER SUMMARY
        # --------------------------------------------------

        summary = services.get_control_tower_summary(
            connection,
        )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Open Exceptions",
                summary["open_exceptions"],
            )

        with col2:
            st.metric(
                "Actionable",
                summary["actionable_exceptions"],
            )

        with col3:
            st.metric(
                "Monitoring",
                summary["monitoring_exceptions"],
            )

        with col4:
            st.metric(
                "Pending Decisions",
                summary["pending_approvals"],
            )

        col5, col6, col7 = st.columns(3)

        with col5:
            st.metric(
                "Awaiting Execution",
                summary["awaiting_execution"],
            )

        with col6:
            st.metric(
                "Critical Open",
                summary["critical_exceptions"],
            )

        with col7:
            st.metric(
                "Recently Resolved",
                len(summary["recently_resolved"]),
            )

        st.divider()

        # --------------------------------------------------
        # LATEST WORKFLOW OUTCOME
        # --------------------------------------------------

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

        # --------------------------------------------------
        # RECENTLY RESOLVED
        # --------------------------------------------------

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
                "The most recent outcomes. Open an "
                "exception's Operational History for "
                "the full timeline."
            )

            st.divider()

        # --------------------------------------------------
        # EXCEPTION INBOX
        # --------------------------------------------------

        st.header("Exception Inbox")

        exceptions = services.get_exception_inbox(
            connection,
        )

        if not exceptions:

            st.success(
                "No open shipment exceptions currently require attention."
            )

            return

        # Triage labels: severity, exception type and the
        # actionability verdict from the existing option
        # data — so the operator can distinguish exceptions
        # requiring action from exceptions under monitoring.
        inbox_entries = [
            (
                row["exception_id"],
                (
                    f"{row['exception_id']} — "
                    f"{row['severity']} · "
                    f"{row['exception_type']} · "
                    + (
                        "Actionable"
                        if row["feasible_option_count"]
                        else "No feasible recovery"
                    )
                ),
            )
            for row in exceptions
        ]

        exception_options = [
            exception_id
            for exception_id, _ in inbox_entries
        ]

        exception_display_options = [
            label
            for _, label in inbox_entries
        ]

        label_by_id = dict(inbox_entries)

        display_to_id = {
            label: exception_id
            for exception_id, label in inbox_entries
        }

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

        selected_display = st.selectbox(
            "Select an exception to investigate",
            exception_display_options,
            index=exception_display_options.index(
                label_by_id[
                    st.session_state.selected_exception_id
                ]
            ),
        )

        selected_exception_id = display_to_id[
            selected_display
        ]

        st.session_state.selected_exception_id = (
            selected_exception_id
        )

        selected_exception = next(
            row
            for row in exceptions
            if row["exception_id"] == selected_exception_id
        )

        # --------------------------------------------------
        # EXCEPTION INVESTIGATION CONTEXT
        # --------------------------------------------------

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

        # --------------------------------------------------
        # EXCEPTION DETAILS
        # --------------------------------------------------

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

        st.divider()

        # --------------------------------------------------
        # DECISION ENGINE
        # --------------------------------------------------

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

                    st.success(
                        "This recovery action has already been executed."
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

            # --------------------------------------------------
            # OPERATIONAL HISTORY
            # --------------------------------------------------

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

        # --------------------------------------------------
        # POST-RERUN SCROLL
        # --------------------------------------------------

        if st.session_state.scroll_to_outcome:

            st.session_state.scroll_to_outcome = False

            scroll_to_workflow_outcome()

    finally:

        connection.close()


if __name__ == "__main__":
    main()