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


# ==================================================
# E. KPI POPULATION SEMANTICS (Checkpoint P)
# ==================================================

def test_actionable_and_monitoring_partition_the_inbox_surface(
    seeded_database,
):
    """
    Actionable and Monitoring are bounded inbox work-queue
    surface metrics: they partition the visible inbox rows
    (actionable + monitoring = inbox row count), whatever
    the open population behind the cap is. They must not be
    presented as a full-population split.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        # Push the open population past the inbox cap with
        # non-actionable (monitoring) rows, while only the
        # fixture exception is actionable — so the surface
        # counts and the full-population split diverge.
        rows = []

        for index in range(1, 121):

            rows.append(
                (
                    f"EXC-920{index:03d}",
                    "SHP-900001",
                    "Delivery Delay",
                    "Low",
                    "2026-09-01 12:00:00",
                    f"Surface semantics fixture {index}",
                    100,
                    "Open",
                    None,
                ),
            )

        exceptions_repo.insert_exceptions(connection, rows)
        connection.commit()

        summary = services.get_control_tower_summary(connection)
        inbox = services.get_exception_inbox(connection)

        # Both counts describe the same bounded surface.
        assert summary["actionable_exceptions"] == 1
        assert summary["monitoring_exceptions"] == (
            len(inbox) - 1
        )
        assert (
            summary["actionable_exceptions"]
            + summary["monitoring_exceptions"]
            == len(inbox)
        )

        # ...and the split never claims the full population:
        # open_exceptions deliberately exceeds the surface
        # the two counts describe.
        assert summary["open_exceptions"] == 122
        assert summary["open_exceptions"] > len(inbox)

        # The cap truncates the open population: the inbox
        # holds 100 rows (1 actionable + 99 monitoring),
        # while 121 open exceptions actually have no
        # feasible recovery. The surface count must stay a
        # surface count — never silently become the true
        # full-population number.
        assert len(inbox) == 100
        assert summary["actionable_exceptions"] == 1
        assert summary["monitoring_exceptions"] == 99

        true_monitoring = connection.execute(
            """
            SELECT COUNT(*) FROM exceptions e
            WHERE e.resolution_status = 'Open'
              AND NOT EXISTS (
                  SELECT 1 FROM recovery_options ro
                  WHERE ro.exception_id = e.exception_id
                    AND ro.feasible = 1
              )
            """
        ).fetchone()[0]

        assert true_monitoring == 121
        assert summary["monitoring_exceptions"] != true_monitoring

    finally:
        connection.close()


def test_other_control_tower_counts_are_full_population(
    seeded_database,
):
    """
    Open Exceptions, Pending Decisions, Awaiting Execution
    and Critical Open are full-population counts: they are
    independent of the inbox cap and count the entire open
    population / all actions of the given status.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        # Open exceptions far beyond any inbox surface.
        rows = []

        for index in range(1, 61):

            rows.append(
                (
                    f"EXC-930{index:03d}",
                    "SHP-900001",
                    "Delivery Delay",
                    "Critical",
                    "2026-09-01 12:00:00",
                    f"Full-population fixture {index}",
                    100,
                    "Open",
                    None,
                ),
            )

        exceptions_repo.insert_exceptions(connection, rows)
        connection.commit()

        summary = services.get_control_tower_summary(connection)

        true_open = connection.execute(
            "SELECT COUNT(*) FROM exceptions "
            "WHERE resolution_status = 'Open'"
        ).fetchone()[0]
        true_critical = connection.execute(
            "SELECT COUNT(*) FROM exceptions "
            "WHERE resolution_status = 'Open' "
            "AND severity = 'Critical'"
        ).fetchone()[0]
        true_pending = connection.execute(
            "SELECT COUNT(*) FROM recovery_actions "
            "WHERE status = 'Pending Approval'"
        ).fetchone()[0]

        assert summary["open_exceptions"] == true_open
        assert summary["critical_exceptions"] == true_critical
        assert summary["critical_exceptions"] >= 60
        assert summary["pending_approvals"] == true_pending == 1

    finally:
        connection.close()


# ==================================================
# F. FOLLOW-UP SEMANTICS (Checkpoint S)
# ==================================================

def test_follow_up_classification_states_are_distinguishable(
    seeded_database,
):
    """
    The investigation-state classification distinguishes
    Decision required, Awaiting execution, Executed — still
    open and Resolved, using only persisted evidence.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        pending = services.classify_investigation_state(
            connection,
            "EXC-900002",
        )
        assert pending["state"] == "Decision required"
        assert pending["follow_up_required"] is False

        services.approve_recovery(
            connection,
            "ACT-000001",
            "CT Tester",
        )

        approved = services.classify_investigation_state(
            connection,
            "EXC-900002",
        )
        assert approved["state"] == "Awaiting execution"
        assert approved["follow_up_required"] is False

        # Execute the recovery: the fixture's recorded dates
        # leave the exception open, so this becomes the
        # follow-up case.
        outcome = services.execute_approved_recovery(
            connection,
            "ACT-000001",
        )
        assert outcome["exception_status"] == "Open"

        executed = services.classify_investigation_state(
            connection,
            "EXC-900002",
        )
        assert executed["state"] == "Executed — still open"
        assert executed["follow_up_required"] is True

        # Resolve through the manual path (allowed once no
        # action is pending/approved) and re-classify.
        _resolve_via_manual_path(connection, "EXC-900002")

        resolved = services.classify_investigation_state(
            connection,
            "EXC-900002",
        )
        assert resolved["state"] == "Resolved"
        assert resolved["follow_up_required"] is False

    finally:
        connection.close()


def test_follow_up_reason_quotes_persisted_evidence(
    seeded_database,
):
    """
    The follow-up reason is the factual operational evidence
    — recorded estimated arrival versus required delivery —
    not a vague verdict.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        services.approve_recovery(
            connection,
            "ACT-000001",
            "CT Tester",
        )
        services.execute_approved_recovery(
            connection,
            "ACT-000001",
        )

        state = services.classify_investigation_state(
            connection,
            "EXC-900002",
        )

        # The fixture's persisted dates: the recovery's
        # recorded arrival 2026-09-17 against the required
        # delivery 2026-09-15.
        assert "2026-09-17" in state["reason"]
        assert "2026-09-15" in state["reason"]
        assert "remains later than required delivery" in (
            state["reason"]
        )
        assert "remains open after recovery execution" in (
            state["reason"]
        )

    finally:
        connection.close()


def test_control_tower_reports_follow_up_population(
    seeded_database,
):
    """
    The control tower reports follow-up as a full-population
    count (matching the Open Exceptions population rule) and
    the follow-up queue as a bounded view, while the P
    partition semantics of Actionable/Monitoring stay
    intact.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        services.approve_recovery(
            connection,
            "ACT-000001",
            "CT Tester",
        )

        # Before execution: no follow-up anywhere.
        summary = services.get_control_tower_summary(connection)
        assert summary["follow_up_required"] == 0
        assert summary["follow_up_queue"] == []

        services.execute_approved_recovery(
            connection,
            "ACT-000001",
        )

        summary = services.get_control_tower_summary(connection)

        assert summary["follow_up_required"] == 1

        queue = summary["follow_up_queue"]
        assert len(queue) == 1
        assert queue[0]["exception_id"] == "EXC-900002"
        assert "2026-09-17" in queue[0]["reason"]
        assert "2026-09-15" in queue[0]["reason"]
        assert queue[0]["action_id"] == "ACT-000001"

        # The follow-up count is full-population: push the
        # open population far past the inbox cap and confirm
        # the count is unaffected.
        rows = []

        for index in range(1, 121):

            rows.append(
                (
                    f"EXC-940{index:03d}",
                    "SHP-900001",
                    "Delivery Delay",
                    "Low",
                    "2026-09-01 12:00:00",
                    f"Follow-up population fixture {index}",
                    100,
                    "Open",
                    None,
                ),
            )

        exceptions_repo.insert_exceptions(connection, rows)
        connection.commit()

        summary = services.get_control_tower_summary(connection)

        assert summary["follow_up_required"] == 1
        assert summary["open_exceptions"] == 122

        # The P partition of the visible surface is unchanged.
        inbox = services.get_exception_inbox(connection)
        assert (
            summary["actionable_exceptions"]
            + summary["monitoring_exceptions"]
            == len(inbox)
        )

    finally:
        connection.close()


def test_resolved_exception_is_not_follow_up_required(
    seeded_database,
):
    """
    A resolved exception never appears in the follow-up
    population or queue — follow-up is defined only for the
    open population.
    """

    connection = seeded_database

    try:
        _create_action(connection)

        services.approve_recovery(
            connection,
            "ACT-000001",
            "CT Tester",
        )
        services.execute_approved_recovery(
            connection,
            "ACT-000001",
        )

        # Resolve through the manual path.
        _resolve_via_manual_path(connection, "EXC-900002")

        summary = services.get_control_tower_summary(connection)

        assert summary["follow_up_required"] == 0
        assert summary["follow_up_queue"] == []

        assert any(
            row["exception_id"] == "EXC-900002"
            for row in summary["recently_resolved"]
        )

    finally:
        connection.close()


def test_follow_up_exception_surfaces_in_inbox_triage(
    seeded_database,
):
    """
    An executed-but-still-open exception is marked as
    follow-up required in the inbox triage data, and the
    newest actionable work still precedes it (existing
    actionable-first ordering is preserved).
    """

    connection = seeded_database

    try:
        _create_action(connection)

        services.approve_recovery(
            connection,
            "ACT-000001",
            "CT Tester",
        )
        services.execute_approved_recovery(
            connection,
            "ACT-000001",
        )

        # A fresh actionable exception detected after the
        # execution — newest actionable work.
        exceptions_repo.insert_exceptions(
            connection,
            [
                (
                    "EXC-900006",
                    "SHP-900002",
                    "Delivery Delay",
                    "High",
                    "2026-09-12 12:00:00",
                    "Newer actionable exception",
                    1500,
                    "Open",
                    None,
                ),
            ],
        )
        _generate_options(connection)

        inbox = services.get_exception_inbox(connection)

        by_id = {
            row["exception_id"]: row for row in inbox
        }

        assert (
            by_id["EXC-900002"]["executed_still_open"] == 1
        )

        ids = [row["exception_id"] for row in inbox]

        # Actionable-first preserved: the newer actionable
        # exception outranks the executed-still-open one.
        assert ids.index("EXC-900006") < ids.index(
            "EXC-900002"
        )

    finally:
        connection.close()
