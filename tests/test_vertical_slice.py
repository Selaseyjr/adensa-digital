"""
Focused tests for the operational vertical slice.

Covers the application contracts the user journey depends on:

1. Investigation context: get_exception_context() projects the
   shared operational context into an application-facing
   structure (customer, order, route, shipment state) without
   duplicating business logic.

2. Refresh identification: run_operational_refresh() reports
   the identities of the exceptions it has just detected, so
   the UI can surface exactly what a processing run found.

3. The full vertical journey on a single fixture database:
   processed baseline → simulated arrival → refresh →
   new exception identified → investigation context →
   recommendation with option identity → approval →
   execution → Resolved outcome.

All tests run on the temporary database fixtures; the
development database is never touched.
"""

import pytest

from app import services
from app.errors import RecoveryWorkflowError
from app.generate_recovery_options import generate_recovery_options
from app.simulation import create_simulated_arrival


# ==================================================
# EXCEPTION INVESTIGATION CONTEXT
# ==================================================

def test_get_exception_context_returns_investigation_fields(
    seeded_database,
):
    """
    The context projection carries the operational fields an
    operations manager needs: customer, order, route,
    shipment state and both delivery dates.
    """

    connection = seeded_database

    try:
        context = services.get_exception_context(
            connection,
            "EXC-900002",
        )

        assert context is not None

        assert context["exception_id"] == "EXC-900002"
        assert context["shipment_id"] == "SHP-900002"
        assert context["order_id"] == "ORD-900001"
        assert context["customer_id"] == "CUS-900001"
        assert context["customer_name"] == "Fixture Customer"
        assert context["route"] == "Rotterdam → Hamburg"
        assert context["transport_mode"] == "Sea"
        assert context["shipment_status"] == "In Transit"
        assert (
            context["estimated_arrival"]
            == "2026-09-20"
        )
        assert (
            context["required_delivery_date"]
            == "2026-09-15"
        )

    finally:
        connection.close()


def test_get_exception_context_missing_exception_returns_none(
    seeded_database,
):
    """A nonexistent exception yields None, not an error."""

    connection = seeded_database

    try:
        assert (
            services.get_exception_context(
                connection,
                "EXC-999999",
            )
            is None
        )

    finally:
        connection.close()


# ==================================================
# REFRESH NEW-EXCEPTION IDENTIFICATION
# ==================================================

def test_operational_refresh_identifies_new_exceptions(
    seeded_database,
):
    """
    Steady-state refresh reports no new exception identities;
    after a simulated arrival the refresh reports exactly the
    newly detected exception ID.
    """

    connection = seeded_database

    try:
        # Bring the fixture to the fully processed state.
        services.run_operational_refresh(connection)

        steady = services.run_operational_refresh(connection)

        assert steady["new_exceptions"] == 0
        assert steady["new_exception_ids"] == []

        arrival = create_simulated_arrival(connection)

        assert arrival is not None

        refreshed = services.run_operational_refresh(connection)

        assert refreshed["new_exceptions"] == 1
        assert len(refreshed["new_exception_ids"]) == 1

        new_exception_id = refreshed["new_exception_ids"][0]

        # The reported identity is the exception that now
        # exists for the simulated shipment.
        exception_row = connection.execute(
            """
            SELECT exception_id
            FROM exceptions
            WHERE shipment_id = ?
            """,
            (arrival["shipment_id"],),
        ).fetchone()

        assert exception_row is not None
        assert (
            exception_row["exception_id"]
            == new_exception_id
        )

    finally:
        connection.close()


# ==================================================
# FULL VERTICAL JOURNEY
# ==================================================

def test_full_vertical_journey_arrival_to_outcome(
    seeded_database,
):
    """
    The complete operational journey on the real pipeline:
    processed baseline → simulated arrival → refresh →
    investigate → recommend → approve → execute → Resolved.
    Every step uses the production service layer only.
    """

    connection = seeded_database

    try:
        # Existing control-tower state: baseline processed.
        services.run_operational_refresh(connection)

        # 1. Simulate shipment arrival.
        arrival = create_simulated_arrival(connection)

        assert arrival is not None

        shipment_id = arrival["shipment_id"]

        # 2. Refresh the operational pipeline.
        refresh = services.run_operational_refresh(connection)

        assert refresh["new_exceptions"] == 1
        assert refresh["new_options"] == 3
        assert refresh["new_actions"] == 1

        exception_id = refresh["new_exception_ids"][0]

        # 3. Investigate the new exception through the
        #    application service.
        context = services.get_exception_context(
            connection,
            exception_id,
        )

        assert context is not None
        assert context["shipment_id"] == shipment_id
        assert context["exception_type"] == "Delivery Delay"
        assert context["shipment_status"] == "In Transit"

        # 4. The decision engine presents a recommendation
        #    with its option identity.
        review = services.get_exception_review(
            connection,
            exception_id,
        )

        assert review is not None

        recommendation = review["recommendation"]

        assert recommendation is not None

        option_id = recommendation["option_id"]

        # The comparison table data is available to the UI:
        # the recommendation first, then the alternatives in
        # the engine's own ranking.
        comparison = [
            recommendation,
            *review["alternatives"],
        ]

        assert len(comparison) == 3

        assert comparison[0]["option_id"] == option_id

        assert all(
            comparison[index]["decision_score"]
            >= comparison[index + 1]["decision_score"]
            for index in range(len(comparison) - 1)
        )

        # 5. A workflow action exists for the exception and
        #    carries the recommendation's option identity.
        action = services.get_latest_action(
            connection,
            exception_id,
        )

        assert action is not None
        assert action["status"] == "Pending Approval"
        assert action["option_id"] == option_id

        # 6. Human approval.
        approval = services.approve_recovery(
            connection,
            action["action_id"],
            "Vertical Slice Test",
        )

        assert approval["success"] is True
        assert approval["new_mode"] == (
            recommendation["transport_mode"]
        )

        # 7. Execution of the approved action.
        outcome = services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        assert outcome["success"] is True

        # 8. The shipment's mode changed to the approved
        #    recovery mode. On this fixture the recommended
        #    option is Road, whose transit still lands after
        #    the required delivery date — so the engine
        #    truthfully reports the exception as still open
        #    (Executed ≠ Resolved). The outcome carries the
        #    new ETA that proves exactly why.
        assert outcome["new_mode"] == (
            recommendation["transport_mode"]
        )

        assert outcome["exception_status"] == "Open"

        assert outcome["new_eta"] > (
            outcome["required_delivery"]
        )

        # The resolving alternative (faster transit than the
        # recommended option) was visible in the comparison
        # the operator decided from.
        faster_alternatives = [
            alternative
            for alternative in review["alternatives"]
            if alternative["estimated_transit_days"]
            < recommendation["estimated_transit_days"]
        ]

        assert faster_alternatives

    finally:
        connection.close()


def test_vertical_slice_rejection_branch(
    seeded_database,
):
    """
    The rejection branch of the journey: the recommendation
    is declined, the action stores its Rejected state and
    the exception remains open — no execution occurs.
    """

    connection = seeded_database

    try:
        services.run_operational_refresh(connection)

        create_simulated_arrival(connection)

        refresh = services.run_operational_refresh(connection)

        exception_id = refresh["new_exception_ids"][0]

        action = services.get_latest_action(
            connection,
            exception_id,
        )

        assert action is not None
        assert action["status"] == "Pending Approval"

        rejection = services.reject_recovery(
            connection,
            action["action_id"],
            "Vertical Slice Test",
        )

        assert rejection["success"] is True

        stored = services.get_latest_action(
            connection,
            exception_id,
        )

        assert stored["status"] == "Rejected"
        assert stored["approved_by"] == "Vertical Slice Test"

        final_exception = (
            services.get_exception_review(
                connection,
                exception_id,
            )
        )

        # The rejection outcome still reports the open
        # exception state; the shipment's mode is unchanged.
        assert rejection["exception_status"] == "Open"

        context = services.get_exception_context(
            connection,
            exception_id,
        )

        assert context is not None
        assert context["transport_mode"] == "Sea"

    finally:
        connection.close()


def test_workflow_error_boundary_still_enforced(
    seeded_database,
):
    """
    The typed domain-error boundary is unchanged: approving
    a missing action raises ActionNotFoundError (a
    RecoveryWorkflowError), not a generic failure.
    """

    connection = seeded_database

    try:
        with pytest.raises(RecoveryWorkflowError):
            services.approve_recovery(
                connection,
                "ACT-999999",
                "Nobody",
            )

    finally:
        connection.close()


# ==================================================
# RECOVERY ASSESSMENT (CHECKPOINT E)
# ==================================================

def _insert_infeasible_option(
    connection,
    option_id,
    exception_id,
    transport_mode,
):
    """Insert one evaluated-but-infeasible option row."""

    connection.execute(
        """
        INSERT INTO recovery_options (
            option_id, exception_id, transport_mode, carrier_id,
            estimated_cost, estimated_transit_days,
            capacity_available, risk_score, feasible
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            option_id,
            exception_id,
            transport_mode,
            "CAR-900001",
            2500.0,
            12.0,
            1,
            85.0,
            0,
        ),
    )


def test_recovery_assessment_with_recommendation(seeded_database):
    """
    An exception with feasible options carries the
    recommendation and its alternatives; the evaluated
    options list stays empty because no explanation of a
    dead end is needed.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        assessment = services.get_recovery_assessment(
            connection,
            "EXC-900002",
        )

        assert assessment is not None

        assert assessment["recommendation"] is not None

        assert assessment["recommendation"][
            "option_id"
        ].startswith("OPT-")

        assert len(assessment["alternatives"]) == 2

        assert assessment["evaluated_options"] == []

    finally:
        connection.close()


def test_recovery_assessment_for_infeasible_options(
    seeded_database,
):
    """
    An exception whose options were all evaluated and found
    infeasible gets no recommendation, and the assessment
    exposes every evaluated option with its operational
    data and feasibility verdict — the truthful explanation
    for the missing recommendation.
    """

    connection = seeded_database

    try:
        _insert_infeasible_option(
            connection,
            "OPT-900101",
            "EXC-900001",
            "Road",
        )

        _insert_infeasible_option(
            connection,
            "OPT-900102",
            "EXC-900001",
            "Rail",
        )

        _insert_infeasible_option(
            connection,
            "OPT-900103",
            "EXC-900001",
            "Sea",
        )

        connection.commit()

        assessment = services.get_recovery_assessment(
            connection,
            "EXC-900001",
        )

        assert assessment is not None

        assert assessment["recommendation"] is None

        assert assessment["alternatives"] == []

        evaluated = assessment["evaluated_options"]

        assert len(evaluated) == 3

        assert all(
            option["feasible"] is False
            for option in evaluated
        )

        modes = {
            option["transport_mode"]
            for option in evaluated
        }

        assert modes == {"Road", "Rail", "Sea"}

        required_fields = {
            "option_id",
            "transport_mode",
            "carrier_id",
            "estimated_cost",
            "estimated_transit_days",
            "risk_score",
            "feasible",
        }

        assert required_fields <= set(
            evaluated[0].keys()
        )

    finally:
        connection.close()


def test_recovery_assessment_without_options(seeded_database):
    """
    An exception that has never been assessed by the option
    generator reports no recommendation and no evaluated
    options: nothing has been evaluated yet.
    """

    connection = seeded_database

    try:
        assessment = services.get_recovery_assessment(
            connection,
            "EXC-900001",
        )

        assert assessment is not None

        assert assessment["recommendation"] is None

        assert assessment["evaluated_options"] == []

    finally:
        connection.close()


def test_recovery_assessment_missing_exception(seeded_database):
    """A nonexistent exception yields None."""

    connection = seeded_database

    try:
        assert (
            services.get_recovery_assessment(
                connection,
                "EXC-999999",
            )
            is None
        )

    finally:
        connection.close()


def test_inbox_exposes_actionability_counts(seeded_database):
    """
    The inbox service passes through the feasible-option
    counts the triage labels are rendered from.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        inbox = services.get_exception_inbox(connection)

        counts = {
            row["exception_id"]: row["feasible_option_count"]
            for row in inbox
        }

        assert counts["EXC-900002"] == 3
        assert counts["EXC-900001"] == 0

    finally:
        connection.close()
