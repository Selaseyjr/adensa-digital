import streamlit as st

from app.database import get_connection
from app.decision_engine import get_recommendation
from app.workflow_engine import (
    approve_action,
    reject_action,
    PENDING_APPROVAL,
    APPROVED,
    REJECTED,
    EXECUTED,
)
from app.execution_engine import execute_recovery_action


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

    # --------------------------------------------------
    # DATABASE CONNECTION
    # --------------------------------------------------

    connection = get_connection()

    try:

        cursor = connection.cursor()

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

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM exceptions
            WHERE resolution_status = 'Open'
            """
        )

        open_exceptions = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM exceptions
            WHERE resolution_status = 'Open'
            AND severity = 'Critical'
            """
        )

        critical_exceptions = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM recovery_actions
            WHERE status = 'Pending Approval'
            """
        )

        pending_approvals = cursor.fetchone()[0]

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
                o.required_delivery_date
            FROM exceptions e
            JOIN shipments s
                ON e.shipment_id = s.shipment_id
            JOIN orders o
                ON s.order_id = o.order_id
            WHERE e.resolution_status = 'Open'
            ORDER BY
                CASE e.severity
                    WHEN 'Critical' THEN 1
                    WHEN 'High' THEN 2
                    WHEN 'Medium' THEN 3
                    WHEN 'Low' THEN 4
                    ELSE 5
                END,
                e.detected_at
            LIMIT 100
            """
        )

        exceptions = cursor.fetchall()

        if not exceptions:

            st.success(
                "No open shipment exceptions currently require attention."
            )

            return

        exception_options = [
            row["exception_id"]
            for row in exceptions
        ]

        # Preserve the currently selected exception when possible.
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

        recommendation_result = get_recommendation(
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

                st.subheader("Alternative Recovery Options")

                for alternative in alternatives:

                    with st.expander(
                        f"{alternative['transport_mode']} "
                        f"— Score "
                        f"{alternative['decision_score']:.2f}"
                    ):

                        st.write(
                            f"**Carrier:** "
                            f"{alternative['carrier_id']}"
                        )

                        st.write(
                            f"**Estimated Cost:** "
                            f"€{alternative['estimated_cost']:,.2f}"
                        )

                        st.write(
                            f"**Transit:** "
                            f"{alternative['estimated_transit_days']:.0f} days"
                        )

                        st.write(
                            f"**Risk:** "
                            f"{alternative['risk_score']:.0f}"
                        )

                        st.write(
                            f"**Decision Score:** "
                            f"{alternative['decision_score']:.2f}"
                        )

            st.divider()

            # --------------------------------------------------
            # WORKFLOW ACTION
            # --------------------------------------------------

            st.header("Workflow Action")

            cursor.execute(
                """
                SELECT
                    action_id,
                    option_id,
                    action_type,
                    status,
                    approved_by,
                    approved_at,
                    executed_at
                FROM recovery_actions
                WHERE exception_id = ?
                ORDER BY action_id DESC
                LIMIT 1
                """,
                (selected_exception_id,),
            )

            action = cursor.fetchone()

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

                                    approve_action(
                                        connection,
                                        action["action_id"],
                                        approver_name.strip(),
                                    )

                                    st.session_state.last_workflow_outcome = {
                                        "success": True,
                                        "message": (
                                            f"Recovery action "
                                            f"{action['action_id']} "
                                            f"approved successfully."
                                        ),
                                        "action_id": action["action_id"],
                                        "shipment_id": selected_exception[
                                            "shipment_id"
                                        ],
                                        "previous_mode": selected_exception[
                                            "transport_mode"
                                        ],
                                        "new_mode": recovery[
                                            "transport_mode"
                                        ],
                                        "carrier_id": recovery[
                                            "carrier_id"
                                        ],
                                        "new_eta": "Pending execution",
                                        "recovery_event": "Pending execution",
                                        "required_delivery": selected_exception[
                                            "required_delivery_date"
                                        ],
                                        "exception_status": "Open",
                                    }

                                    st.rerun()

                                except Exception as error:

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

                                    reject_action(
                                        connection,
                                        action["action_id"],
                                        approver_name.strip(),
                                    )

                                    st.session_state.last_workflow_outcome = {
                                        "success": True,
                                        "message": (
                                            f"Recovery action "
                                            f"{action['action_id']} "
                                            f"rejected."
                                        ),
                                        "action_id": action["action_id"],
                                        "shipment_id": selected_exception[
                                            "shipment_id"
                                        ],
                                        "previous_mode": selected_exception[
                                            "transport_mode"
                                        ],
                                        "new_mode": selected_exception[
                                            "transport_mode"
                                        ],
                                        "carrier_id": "No execution",
                                        "new_eta": "No execution",
                                        "recovery_event": "None",
                                        "required_delivery": selected_exception[
                                            "required_delivery_date"
                                        ],
                                        "exception_status": "Open",
                                    }

                                    st.rerun()

                                except Exception as error:

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

                            # Capture the current shipment state
                            # before execution.
                            cursor.execute(
                                """
                                SELECT
                                    transport_mode,
                                    carrier_id
                                FROM shipments
                                WHERE shipment_id = ?
                                """,
                                (
                                    selected_exception["shipment_id"],
                                ),
                            )

                            previous_shipment = cursor.fetchone()

                            previous_mode = (
                                previous_shipment["transport_mode"]
                            )

                            result = execute_recovery_action(
                                connection,
                                action["action_id"],
                            )

                            # Read the updated shipment.
                            cursor.execute(
                                """
                                SELECT
                                    transport_mode,
                                    carrier_id,
                                    estimated_arrival
                                FROM shipments
                                WHERE shipment_id = ?
                                """,
                                (
                                    selected_exception["shipment_id"],
                                ),
                            )

                            updated_shipment = cursor.fetchone()

                            # Read the recovery event.
                            cursor.execute(
                                """
                                SELECT event_id
                                FROM shipment_events
                                WHERE shipment_id = ?
                                AND event_type = 'Recovery Executed'
                                ORDER BY event_timestamp DESC
                                LIMIT 1
                                """,
                                (
                                    selected_exception["shipment_id"],
                                ),
                            )

                            recovery_event = cursor.fetchone()

                            # Read final exception status.
                            cursor.execute(
                                """
                                SELECT resolution_status
                                FROM exceptions
                                WHERE exception_id = ?
                                """,
                                (
                                    selected_exception_id,
                                ),
                            )

                            final_exception = cursor.fetchone()

                            exception_status = (
                                final_exception[
                                    "resolution_status"
                                ]
                            )

                            st.session_state.last_workflow_outcome = {
                                "success": True,
                                "message": (
                                    f"Recovery executed successfully "
                                    f"for "
                                    f"{selected_exception['shipment_id']}."
                                ),
                                "action_id": action["action_id"],
                                "shipment_id": selected_exception[
                                    "shipment_id"
                                ],
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
                                "required_delivery": selected_exception[
                                    "required_delivery_date"
                                ],
                                "exception_status": exception_status,
                            }

                            # Tell the next Streamlit run to bring
                            # the outcome into view.
                            st.session_state.scroll_to_outcome = True

                            st.rerun()

                        except Exception as error:

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

                    st.warning(
                        "This recovery action was rejected."
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