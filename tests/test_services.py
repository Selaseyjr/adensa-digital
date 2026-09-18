"""
Focused tests for the application service layer.

These tests verify application contracts — orchestration and
outcome construction — not engine business rules. The
engines' rules are exercised by the existing engine and
lifecycle tests. All tests run on the seeded_database
fixture; the development database is never touched.
"""

import pytest

from app import services
from app.errors import RecoveryWorkflowError
from app.generate_recovery_options import generate_recovery_options
from app.repositories import recovery_actions_repo


# ==================================================
# HELPERS
# ==================================================

def _generate_options(connection):
    """Run the real recovery-option generator on the fixture."""

    generate_recovery_options(connection)


def _create_action(
    connection,
    exception_id="EXC-900002",
):
    """
    Create the workflow action for an exception through the
    real workflow engine, returning the action row.
    """

    _generate_options(connection)

    from app.workflow_engine import generate_workflow_actions

    summary = generate_workflow_actions(connection)

    action = recovery_actions_repo.get_latest_action_for_exception(
        connection,
        exception_id,
    )

    assert action is not None

    return action


def _approve(
    connection,
    action,
):
    """Approve an action through the service."""

    return services.approve_recovery(
        connection,
        action["action_id"],
        "Service Test",
    )


# ==================================================
# RECOMMENDATION / REVIEW
# ==================================================

def test_get_exception_review_returns_recommendation(seeded_database):
    """
    The service returns the engine's recommendation for the
    feasible exception, carrying a real option_id.
    """

    connection = seeded_database

    try:
        _generate_options(connection)

        result = services.get_exception_review(
            connection,
            "EXC-900002",
        )

        assert result["recommendation"] is not None
        assert result["recommendation"]["option_id"].startswith("OPT-")
        assert result["recommendation"]["transport_mode"] == "Road"

    finally:
        connection.close()


def test_get_exception_review_without_recommendation(seeded_database):
    """
    The zero-option exception yields a result with
    recommendation None.
    """

    connection = seeded_database

    try:
        _generate_options(connection)

        result = services.get_exception_review(
            connection,
            "EXC-900001",
        )

        assert result["recommendation"] is None
        assert result["alternatives"] == []

    finally:
        connection.close()


def test_get_latest_action(seeded_database):
    """
    The service surfaces the latest action for an
    exception and None when none exists.
    """

    connection = seeded_database

    try:
        assert services.get_latest_action(
            connection,
            "EXC-900002",
        ) is None

        action = _create_action(connection)

        assert services.get_latest_action(
            connection,
            "EXC-900002",
        )["action_id"] == action["action_id"]

    finally:
        connection.close()


# ==================================================
# DASHBOARD
# ==================================================

def test_get_dashboard_metrics(seeded_database):
    """
    The dashboard metrics aggregate the repository counts
    for the seeded dataset.
    """

    connection = seeded_database

    try:
        metrics = services.get_dashboard_metrics(connection)

        assert metrics["open_exceptions"] == 2
        assert metrics["critical_exceptions"] == 0
        assert metrics["pending_approvals"] == 0

        _create_action(connection)

        metrics = services.get_dashboard_metrics(connection)

        assert metrics["pending_approvals"] == 1

    finally:
        connection.close()


def test_get_exception_inbox(seeded_database):
    """
    The inbox service returns the seeded open exceptions in
    severity order.
    """

    connection = seeded_database

    try:
        inbox = services.get_exception_inbox(connection)

        assert [
            row["exception_id"] for row in inbox
        ] == ["EXC-900002", "EXC-900001"]

    finally:
        connection.close()


# ==================================================
# APPROVE / REJECT / EXECUTE
# ==================================================

def test_approve_recovery_preserves_identity_chain(seeded_database):
    """
    Approval returns the approval outcome with the
    action's option identity intact.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)

        outcome = _approve(
            connection,
            action,
        )

        assert outcome["success"] is True
        assert outcome["action_id"] == action["action_id"]
        assert outcome["new_mode"] == "Road"
        assert outcome["exception_status"] == "Open"

        stored = services.get_latest_action(connection, "EXC-900002")

        assert stored["status"] == "Approved"
        assert stored["option_id"] == action["option_id"]

    finally:
        connection.close()


def test_reject_recovery_preserves_workflow_behavior(seeded_database):
    """
    Rejection returns the rejection outcome and stores the
    Rejected status.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)

        outcome = services.reject_recovery(
            connection,
            action["action_id"],
            "Service Test",
        )

        assert outcome["success"] is True
        assert outcome["carrier_id"] == "No execution"
        assert outcome["new_eta"] == "No execution"
        assert outcome["new_mode"] == "Sea"

        stored = services.get_latest_action(connection, "EXC-900002")

        assert stored["status"] == "Rejected"

    finally:
        connection.close()


def test_execute_approved_recovery_still_open(seeded_database):
    """
    Execution through the service produces the outcome the
    UI previously constructed; the seeded timing yields the
    Still Open branch (Executed ≠ Resolved).
    """

    connection = seeded_database

    try:
        action = _create_action(connection)

        _approve(
            connection,
            action,
        )

        outcome = services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        assert outcome["success"] is True
        assert outcome["previous_mode"] == "Sea"
        assert outcome["new_mode"] == "Road"
        assert outcome["carrier_id"] == "CAR-900001"
        assert outcome["new_eta"] == "2026-09-17"
        assert outcome["exception_status"] == "Open"
        assert outcome["recovery_event"].startswith("EVT-REC-")
        assert outcome["required_delivery"] == "2026-09-15"

        assert services.get_latest_action(
            connection,
            "EXC-900002",
        )["status"] == "Executed"

    finally:
        connection.close()


def test_execute_approved_recovery_resolved_branch(seeded_database):
    """
    When the required delivery date is far enough out, the
    same service call produces the Resolved branch.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)

        _approve(
            connection,
            action,
        )

        # Move the required delivery date beyond the new ETA
        # (2026-09-17) so the shipment meets the commitment.
        connection.execute(
            """
            UPDATE orders
            SET required_delivery_date = '2026-09-20'
            WHERE order_id = 'ORD-900001'
            """
        )

        connection.commit()

        outcome = services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        assert outcome["success"] is True
        assert outcome["exception_status"] == "Resolved"

        stored = exceptions_row = connection.execute(
            """
            SELECT resolution_status
            FROM exceptions
            WHERE exception_id = 'EXC-900002'
            """
        ).fetchone()

        assert stored["resolution_status"] == "Resolved"

    finally:
        connection.close()


def test_execute_approved_recovery_failure_outcome(seeded_database):
    """
    A failing execution returns the failure outcome instead
    of raising, mirroring the previous UI behavior.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)

        _approve(
            connection,
            action,
        )

        # The exception must be open for execution; closing
        # it first forces the engine's open-exception guard
        # to raise, which the service converts to the
        # failure outcome.
        connection.execute(
            """
            UPDATE exceptions
            SET resolution_status = 'Resolved'
            WHERE exception_id = 'EXC-900002'
            """
        )

        connection.commit()

        outcome = services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        assert outcome["success"] is False
        assert "Recovery execution failed:" in outcome["message"]

    finally:
        connection.close()


# ==================================================
# MISSING ACTION CONTRACT
# ==================================================

def test_approve_recovery_missing_action_raises(seeded_database):
    """
    Approving an unknown action raises the workflow
    engine's not-found error; no outcome is produced.
    """

    connection = seeded_database

    try:
        with pytest.raises(ValueError):
            services.approve_recovery(
                connection,
                "ACT-999999",
                "Service Test",
            )

    finally:
        connection.close()


def test_reject_recovery_missing_action_raises(seeded_database):
    """
    Rejecting an unknown action raises the workflow
    engine's not-found error; no outcome is produced.
    """

    connection = seeded_database

    try:
        with pytest.raises(ValueError):
            services.reject_recovery(
                connection,
                "ACT-999999",
                "Service Test",
            )

    finally:
        connection.close()


# ==================================================
# TYPED DOMAIN ERROR BOUNDARY
# ==================================================

def test_recovery_workflow_error_is_valueerror():
    """
    RecoveryWorkflowError must remain a ValueError subclass:
    every existing caller and test that catches ValueError
    keeps working unchanged.
    """

    assert issubclass(RecoveryWorkflowError, ValueError)


def test_execute_service_propagates_non_domain_errors(
    seeded_database,
    monkeypatch,
):
    """
    A programming or infrastructure error inside the execution
    engine must NOT be converted into a failure outcome: the
    service catches only RecoveryWorkflowError, so non-domain
    exceptions propagate to the presentation layer.
    """

    connection = seeded_database

    def _simulate_programming_failure(connection, action_id):
        raise RuntimeError("Simulated programming failure")

    try:
        _generate_options(connection)

        action = _create_action(connection)
        _approve(connection, action)

        monkeypatch.setattr(
            services,
            "execute_recovery_action",
            _simulate_programming_failure,
        )

        with pytest.raises(RuntimeError) as excinfo:
            services.execute_approved_recovery(
                connection,
                action["action_id"],
            )

        assert "Simulated programming failure" in str(excinfo.value)

    finally:
        connection.close()
