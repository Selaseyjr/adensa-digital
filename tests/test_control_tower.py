"""
Control-tower summary tests (Checkpoint J).

These tests verify the aggregation/projection contract of
services.get_control_tower_summary and the
get_recently_resolved_exceptions repository read: the
at-a-glance operational state and the recently resolved
outcomes the control-tower UI renders.

All tests run on isolated temporary/seeded databases; the
development database is never touched.
"""

import pytest

from app import services
from app.generate_recovery_options import generate_recovery_options
from app.repositories import exceptions_repo
from app.repositories import manual_interventions_repo


# ==================================================
# HELPERS
# ==================================================

def _generate_options(connection):
    """Run the real recovery-option generator."""

    generate_recovery_options(connection)


def _create_action(connection, exception_id="EXC-900002"):
    """
    Produce the workflow action for an exception through
    the real engines (options -> workflow action).
    """

    _generate_options(connection)

    from app.workflow_engine import generate_workflow_actions

    generate_workflow_actions(connection)


def _insert_infeasible_option(
    connection,
    option_id,
    exception_id,
    transport_mode,
):
    """
    Insert one evaluated-but-infeasible option row — the
    established Checkpoint E seeding pattern. The option
    data is what makes an exception "monitoring" (no
    feasible recovery) in the inbox.
    """

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


def _resolve_via_manual_path(
    connection,
    exception_id,
):
    """
    Resolve an exception through the real manual-resolution
    service path (Checkpoint F), producing the recorded
    intervention evidence and the resolution status change.
    The recorded_at timestamp is the service's own
    wall-clock stamp.
    """

    services.record_manual_resolution(
        connection,
        exception_id=exception_id,
        intervention_type="Carrier call",
        external_party="Fixture Carrier Desk",
        resolution_summary=(
            "Fixture: carrier agreed to expedite the delivery."
        ),
        recorded_by="Fixture Planner",
        outcome="Resolved",
        new_expected_delivery="2026-09-19",
    )


# ==================================================
# A/B. CONTROL-TOWER COUNTS & THE ACTIONABLE SPLIT
# ==================================================

def test_summary_quiet_database_returns_zeroes(seeded_database):
    """
    With no pipeline activity, every count is zero/empty
    and the projection raises nothing.
    """

    connection = seeded_database

    try:
        summary = services.get_control_tower_summary(connection)

        assert summary["open_exceptions"] == 2
        assert summary["actionable_exceptions"] == 0
        assert summary["monitoring_exceptions"] == 2
        assert summary["pending_approvals"] == 0
        assert summary["awaiting_execution"] == 0
        assert summary["critical_exceptions"] == 0
        assert summary["recently_resolved"] == []

    finally:
        connection.close()


def test_summary_counts_full_pipeline_state(seeded_database):
    """
    After the real pipeline runs, the projection reflects
    the actionable/monitoring split, the pending decision,
    and the critical count, without recomputing feasibility.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        summary = services.get_control_tower_summary(connection)

        # EXC-900002 (High) gained 3 feasible options ->
        # actionable; EXC-900001 (Low) gained none ->
        # monitoring.
        assert summary["open_exceptions"] == 2
        assert summary["actionable_exceptions"] == 1
        assert summary["monitoring_exceptions"] == 1
        assert summary["pending_approvals"] == 1
        assert summary["awaiting_execution"] == 0
        assert summary["critical_exceptions"] == 0

        # The actionable/monitoring split must be the inbox's
        # own feasible-option counts — the service adds no
        # feasibility knowledge of its own (B).
        inbox = services.get_exception_inbox(connection)
        actionable_from_inbox = sum(
            1
            for row in inbox
            if row["feasible_option_count"] > 0
        )
        monitoring_from_inbox = sum(
            1
            for row in inbox
            if row["feasible_option_count"] == 0
        )

        assert (
            summary["actionable_exceptions"]
            == actionable_from_inbox
        )
        assert (
            summary["monitoring_exceptions"]
            == monitoring_from_inbox
        )

    finally:
        connection.close()


def test_summary_counts_approved_action_as_awaiting_execution(
    seeded_database,
):
    """
    An approved action moves from pending decision to the
    awaiting-execution count.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        services.approve_recovery(
            connection,
            "ACT-000001",
            "CT Tester",
        )

        summary = services.get_control_tower_summary(connection)

        assert summary["pending_approvals"] == 0
        assert summary["awaiting_execution"] == 1

    finally:
        connection.close()


def test_summary_critical_exception_counted(seeded_database):
    """
    A critical open exception is counted in critical_exceptions
    (a severity reclassification of one fixture exception).
    """

    connection = seeded_database

    try:
        connection.execute(
            """
            UPDATE exceptions
            SET severity = 'Critical'
            WHERE exception_id = 'EXC-900001'
            """
        )
        connection.commit()

        summary = services.get_control_tower_summary(connection)

        assert summary["critical_exceptions"] == 1
        assert summary["open_exceptions"] == 2

    finally:
        connection.close()


# ==================================================
# C/D. RECENTLY RESOLVED & RESOLUTION PATHS
# ==================================================

def test_recently_resolved_newest_first_and_limit(
    seeded_database,
):
    """
    The repository read returns resolved exceptions newest
    first and respects the limit; open ones never appear.
    """

    connection = seeded_database

    try:
        exceptions_repo.mark_exception_resolved(
            connection,
            "EXC-900002",
            "2026-09-18 10:00:00",
        )
        exceptions_repo.mark_exception_resolved(
            connection,
            "EXC-900001",
            "2026-09-18 11:00:00",
        )

        rows = exceptions_repo.get_recently_resolved_exceptions(
            connection,
            10,
        )

        assert [
            row["exception_id"] for row in rows
        ] == ["EXC-900001", "EXC-900002"]

        limited = (
            exceptions_repo.get_recently_resolved_exceptions(
                connection,
                1,
            )
        )

        assert [
            row["exception_id"] for row in limited
        ] == ["EXC-900001"]

    finally:
        connection.close()


def test_recently_resolved_excludes_open_exceptions(
    seeded_database,
):
    """
    Only resolved exceptions are returned; an open
    exception (even with evaluated options) never appears.
    """

    connection = seeded_database

    try:
        _insert_infeasible_option(
            connection,
            "OPT-900101",
            "EXC-900002",
            "Air",
        )

        exceptions_repo.mark_exception_resolved(
            connection,
            "EXC-900001",
            "2026-09-18 09:00:00",
        )

        rows = exceptions_repo.get_recently_resolved_exceptions(
            connection,
            10,
        )

        assert [
            row["exception_id"] for row in rows
        ] == ["EXC-900001"]

    finally:
        connection.close()


def test_resolved_via_system_execution_reports_evidence(
    seeded_database,
):
    """
    A system-executed recovery that resolves the exception
    is reported with the system path — based on the
    recorded Executed action, not an inference.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        services.approve_recovery(
            connection,
            "ACT-000001",
            "CT Tester",
        )

        # Move the required delivery beyond the new ETA so
        # the execution resolves the exception (established
        # Resolved-branch pattern).
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
            "ACT-000001",
        )

        assert outcome["exception_status"] == "Resolved"

        summary = services.get_control_tower_summary(connection)

        assert summary["open_exceptions"] == 1

        resolved = summary["recently_resolved"]

        assert len(resolved) == 1
        assert resolved[0]["exception_id"] == "EXC-900002"
        assert resolved[0]["resolution_path"] == (
            "System-executed recovery"
        )

    finally:
        connection.close()


def test_resolved_via_manual_intervention_reports_evidence(
    seeded_database,
):
    """
    A manually resolved exception is reported with the
    manual path — based on the recorded intervention.
    """

    connection = seeded_database

    try:
        _resolve_via_manual_path(
            connection,
            "EXC-900001",
        )

        summary = services.get_control_tower_summary(connection)

        assert summary["open_exceptions"] == 1

        resolved = summary["recently_resolved"]

        assert len(resolved) == 1
        assert resolved[0]["exception_id"] == "EXC-900001"
        assert resolved[0]["resolved_at"]  # wall-clock stamp
        assert resolved[0]["resolution_path"] == (
            "Manually resolved"
        )

    finally:
        connection.close()


def test_resolved_without_evidence_reports_neutral_path(
    seeded_database,
):
    """
    A resolution with neither an executed action nor a
    recorded intervention is reported with the neutral
    "Resolved" path — the service never fabricates one.
    """

    connection = seeded_database

    try:
        exceptions_repo.mark_exception_resolved(
            connection,
            "EXC-900001",
            "2026-09-18 08:00:00",
        )

        summary = services.get_control_tower_summary(connection)

        resolved = summary["recently_resolved"]

        assert len(resolved) == 1
        assert resolved[0]["exception_id"] == "EXC-900001"
        assert resolved[0]["resolution_path"] == "Resolved"

    finally:
        connection.close()


def test_manual_intervention_row_without_resolution_not_listed(
    seeded_database,
):
    """
    Recording a Still-Open intervention never lists the
    exception as resolved: only the recorded outcome
    (through the guarded status update) changes resolution
    state.
    """

    connection = seeded_database

    try:
        services.record_manual_resolution(
            connection,
            exception_id="EXC-900001",
            intervention_type="Carrier call",
            external_party="Fixture Carrier Desk",
            resolution_summary=(
                "Fixture: monitored, no resolution yet."
            ),
            recorded_by="Fixture Planner",
            outcome="Still Open",
        )

        summary = services.get_control_tower_summary(connection)

        assert summary["open_exceptions"] == 2
        assert summary["recently_resolved"] == []

    finally:
        connection.close()
