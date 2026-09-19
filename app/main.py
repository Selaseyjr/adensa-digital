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

        # --------------------------------------------------
        # HEADER
        # --------------------------------------------------

        st.title("🌍 Adensa Digital")
        st.subheader("Supply Chain Exception & Recovery Platform")

        st.caption(
            "Detect → Analyze → Recommend → Approve → Execute → Resolve"
        )

        st.divider()

        # --------------------------------------------------
        # KPI DATA
        # --------------------------------------------------

        metrics = services.get_dashboard_metrics(
            connection,
        )

        open_exceptions = metrics["open_exceptions"]

        critical_exceptions = metrics["critical_exceptions"]

        pending_approvals = metrics["pending_approvals"]

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Open Exceptions",
                open_exceptions,
            )

        with col2:
            st.metric(
                "Critical Exceptions",
                critical_exceptions,
            )

        with col3:
            st.metric(
                "Pending Approvals",
                pending_approvals,
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

        selected_exception_id = st.selectbox(
            "Select an exception to investigate",
            exception_options,
            index=exception_options.index(
                st.session_state.selected_exception_id
            ),
        )

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

        recommendation_result = services.get_exception_review(
            connection,
            selected_exception_id,
        )

        if (
            recommendation_result is None
            or recommendation_result.get("recommendation") is None
        ):

            st.warning(
                "No feasible recovery recommendation "
                "is currently available for this exception."
            )

        else:

            recovery = recommendation_result["recommendation"]

            alternatives = recommendation_result.get(
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
                    use_container_width=True,
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
        # POST-RERUN SCROLL
        # --------------------------------------------------

        if st.session_state.scroll_to_outcome:

            st.session_state.scroll_to_outcome = False

            scroll_to_workflow_outcome()

    finally:

        connection.close()


if __name__ == "__main__":
    main()