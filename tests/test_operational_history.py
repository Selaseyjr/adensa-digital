"""
Focused tests for the operational history (Checkpoint G).

The history service composes a chronological exception
story from real persisted records — detection, option
evaluation, decisions, executions, recorded interventions
and the current outcome. These tests verify the observable
composition contract:

- every entry is grounded in persisted data (no fabricated
  history);
- entries carry the timestamp actually stored for that
  step, or None where the domain persists none;
- ordering is chronological and stable;
- the system-driven and human-driven resolution paths both
  appear truthfully.

All tests run on the temporary database fixtures; the
development database is never touched.
"""

import pytest

from app import services
from app.generate_recovery_options import generate_recovery_options
from app.repositories import recovery_actions_repo
from app.workflow_engine import generate_workflow_actions


# ==================================================
# HELPERS
# ==================================================

def _create_action(
    connection,
    exception_id="EXC-900002",
):
    """
    Create the workflow action for an exception through the
    real engines, returning the action row.
    """

    generate_recovery_options(connection)
    generate_workflow_actions(connection)

    action = recovery_actions_repo.get_latest_action_for_exception(
        connection,
        exception_id,
    )

    assert action is not None

    return action


def _approve(connection, action):
    """Approve an action through the service."""

    return services.approve_recovery(
        connection,
        action["action_id"],
        "History Test",
    )


def _reject(connection, action):
    """Reject an action through the service."""

    return services.reject_recovery(
        connection,
        action["action_id"],
        "History Test",
    )


def _record_manual_resolution(
    connection,
    exception_id="EXC-900001",
    outcome="Still Open",
    **overrides,
):
    """Record one manual resolution with defaults."""

    parameters = {
        "intervention_type": "Carrier call",
        "external_party": "CAR-900001 dispatch",
        "resolution_summary": (
            "Carrier agreed to expedited direct delivery"
        ),
        "recorded_by": "Planner",
        "outcome": outcome,
        "new_expected_delivery": "2026-09-18",
        "notes": "Agreed by phone at 14:00",
    }

    parameters.update(overrides)

    return services.record_manual_resolution(
        connection,
        exception_id,
        parameters["intervention_type"],
        parameters["external_party"],
        parameters["resolution_summary"],
        parameters["recorded_by"],
        parameters["outcome"],
        new_expected_delivery=parameters[
            "new_expected_delivery"
        ],
        notes=parameters["notes"],
    )


def _insert_infeasible_option(
    connection,
    option_id,
    exception_id,
    transport_mode,
):
    """
    Seed one evaluated-but-infeasible option, matching the
    established Checkpoint E test pattern (the generator
    never produces options for EXC-900001).
    """

    connection.execute(
        """
        INSERT INTO recovery_options (
            option_id,
            exception_id,
            transport_mode,
            carrier_id,
            estimated_cost,
            estimated_transit_days,
            capacity_available,
            risk_score,
            feasible
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            option_id,
            exception_id,
            transport_mode,
            "CAR-900001",
            2500.0,
            10.0,
            20.0,
            90.0,
        ),
    )


def _events(history):
    """The event sequence of a composed history."""

    return [entry["event"] for entry in history]


# ==================================================
# COMPOSITION FROM PERSISTED DATA
# ==================================================

def test_history_missing_exception_returns_none(seeded_database):
    """
    A nonexistent exception has no history: the service
    returns None rather than an empty story.
    """

    connection = seeded_database

    try:
        assert (
            services.get_exception_history(
                connection,
                "EXC-DOES-NOT-EXIST",
            )
            is None
        )

    finally:
        connection.close()


def test_history_fresh_exception_has_detection_and_open_outcome(
    seeded_database,
):
    """
    An exception with no recovery data still has a truthful
    history: detected, then still open. No fabricated
    option, decision or intervention events appear.
    """

    connection = seeded_database

    try:
        history = services.get_exception_history(
            connection,
            "EXC-900001",
        )

        assert history is not None
        assert len(history) == 2

        assert _events(history) == [
            "Exception detected",
            "Exception still open",
        ]

        detection = history[0]

        assert detection["timestamp"] == "2026-09-10 12:00:00"
        assert detection["actor"] == (
            "Adensa operational pipeline"
        )
        assert "EXC-900001" not in detection["detail"]
        assert detection["detail"].startswith("Low severity")

        outcome = history[1]

        assert outcome["timestamp"] is None

    finally:
        connection.close()


def test_history_options_evaluated_entry_when_options_exist(
    seeded_database,
):
    """
    Once options have been generated the evaluation entry
    appears with truthful counts and no fabricated
    timestamp (options carry none in the domain model).
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        evaluation = [
            entry
            for entry in history
            if entry["event"] == "Recovery options evaluated"
        ]

        assert len(evaluation) == 1

        evaluation = evaluation[0]

        assert evaluation["timestamp"] is None
        assert "3 options assessed" in evaluation["detail"]
        assert "3 feasible" in evaluation["detail"]

    finally:
        connection.close()


def test_history_no_evaluation_entry_without_options(
    seeded_database,
):
    """
    Before any option generation the history must not claim
    options were evaluated.
    """

    connection = seeded_database

    try:
        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        assert (
            "Recovery options evaluated"
            not in _events(history)
        )

    finally:
        connection.close()


# ==================================================
# SYSTEM-DRIVEN PATH
# ==================================================

def test_history_pending_approval_shows_recommendation_only(
    seeded_database,
):
    """
    A pending action contributes a recommendation event but
    no approval, rejection or execution events.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        events = _events(history)

        assert "Recommendation generated" in events
        assert "Recovery approved" not in events
        assert "Recovery rejected" not in events
        assert "Recovery executed" not in events

        recommendation = history[
            events.index("Recommendation generated")
        ]

        assert (
            recommendation["detail"]
            .startswith(action["action_id"])
        )
        assert (
            recommendation["actor"]
            == "Adensa decision engine"
        )

    finally:
        connection.close()


def test_history_approved_recovery(seeded_database):
    """
    Approval contributes the human decision event with the
    stored actor and timestamp.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _approve(connection, action)

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        events = _events(history)

        assert "Recovery approved" in events
        assert "Recovery executed" not in events

        approval = history[events.index("Recovery approved")]

        assert approval["actor"] == "History Test"
        assert approval["timestamp"] is not None

    finally:
        connection.close()


def test_history_rejected_recovery(seeded_database):
    """
    Rejection contributes the rejection event — not an
    approval — with the rejecting actor.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _reject(connection, action)

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        events = _events(history)

        assert "Recovery rejected" in events
        assert "Recovery approved" not in events
        assert "Recovery executed" not in events

        rejection = history[events.index("Recovery rejected")]

        assert rejection["actor"] == "History Test"
        assert rejection["timestamp"] is not None

    finally:
        connection.close()


def test_history_executed_recovery_still_open(seeded_database):
    """
    An executed recovery that leaves the shipment late
    contributes the execution event and the exception
    remains open in the outcome entry.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _approve(connection, action)

        outcome = services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        assert outcome["success"] is True

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        events = _events(history)

        assert "Recovery executed" in events

        execution = history[events.index("Recovery executed")]

        assert execution["timestamp"] is not None
        assert execution["actor"] == "History Test"

        assert _events(history)[-1] == "Exception still open"

    finally:
        connection.close()


def test_history_executed_recovery_resolved(seeded_database):
    """
    An executed recovery that meets the delivery commitment
    resolves the exception; the resolution event carries the
    engine-stamped resolved_at timestamp.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _approve(connection, action)

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

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        events = _events(history)

        assert "Recovery executed" in events
        assert events[-1] == "Exception resolved"

        resolution = history[-1]

        assert resolution["timestamp"] is not None

    finally:
        connection.close()


# ==================================================
# HUMAN-DRIVEN PATH
# ==================================================

def test_history_manual_intervention_still_open(seeded_database):
    """
    A recorded Still Open intervention appears in the
    history and does not resolve the exception.
    """

    connection = seeded_database

    try:
        _record_manual_resolution(
            connection,
            outcome="Still Open",
        )

        history = services.get_exception_history(
            connection,
            "EXC-900001",
        )

        events = _events(history)

        assert "Manual intervention recorded" in events
        assert "Exception resolved through manual " \
            "intervention" not in events
        assert events[-1] == "Exception still open"

        intervention = history[
            events.index("Manual intervention recorded")
        ]

        assert intervention["actor"] == "Planner"
        assert (
            intervention["detail"]
            .startswith("INT-000001")
        )
        assert intervention["timestamp"] is not None

    finally:
        connection.close()


def test_history_manual_intervention_resolved(seeded_database):
    """
    A recorded Resolved intervention appears together with
    the resolution event, whose timestamp is the engine-
    stamped resolved_at.
    """

    connection = seeded_database

    try:
        _record_manual_resolution(
            connection,
            outcome="Resolved",
        )

        history = services.get_exception_history(
            connection,
            "EXC-900001",
        )

        events = _events(history)

        assert "Exception resolved through manual " \
            "intervention" in events
        assert events[-1] == "Exception resolved"

        resolution = history[-1]

        assert resolution["timestamp"] is not None

    finally:
        connection.close()


def test_history_system_and_manual_records_coexist(
    seeded_database,
):
    """
    Where the domain model permits both record types for
    one exception (a rejected action leaves it open for a
    manual resolution), the history tells the full story
    chronologically.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _reject(connection, action)

        # A rejected action frees the exception for a
        # manual resolution: the intervention targets the
        # same exception.
        _record_manual_resolution(
            connection,
            exception_id="EXC-900002",
            outcome="Resolved",
        )

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        events = _events(history)

        assert "Recommendation generated" in events
        assert "Recovery rejected" in events
        assert "Manual intervention recorded" in events
        assert "Exception resolved through manual " \
            "intervention" in events
        assert events[-1] == "Exception resolved"

    finally:
        connection.close()


# ==================================================
# ORDERING AND INTEGRITY
# ==================================================

def test_history_is_chronologically_ordered(seeded_database):
    """
    Timestamped entries sort chronologically; undated
    entries keep their narrative position among neighbours
    sharing the next timestamp.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _approve(connection, action)

        services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        timestamps = [
            entry["timestamp"]
            for entry in history
            if entry["timestamp"] is not None
        ]

        assert timestamps == sorted(timestamps)

        # The story reads in lifecycle order.
        events = _events(history)

        assert events.index("Exception detected") < events.index(
            "Recommendation generated"
        )
        assert events.index(
            "Recommendation generated"
        ) < events.index("Recovery approved")
        assert events.index(
            "Recovery approved"
        ) < events.index("Recovery executed")

    finally:
        connection.close()


def test_history_entries_are_grounded_in_persisted_data(
    seeded_database,
):
    """
    Every timestamped history entry matches a timestamp
    actually stored in the domain tables — nothing is
    invented for presentation.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _approve(connection, action)
        _record_manual_resolution(
            connection,
            outcome="Resolved",
        )

        history = services.get_exception_history(
            connection,
            "EXC-900001",
        )

        stored = {
            row[0]
            for row in connection.execute(
                """
                SELECT detected_at FROM exceptions
                WHERE exception_id = 'EXC-900001'
                UNION
                SELECT approved_at FROM recovery_actions
                WHERE exception_id = 'EXC-900001'
                  AND approved_at IS NOT NULL
                UNION
                SELECT recorded_at FROM manual_interventions
                WHERE exception_id = 'EXC-900001'
                UNION
                SELECT resolved_at FROM exceptions
                WHERE exception_id = 'EXC-900001'
                  AND resolved_at IS NOT NULL
                """
            )
        }

        for entry in history:

            if entry["timestamp"] is not None:

                assert entry["timestamp"] in stored

    finally:
        connection.close()


def test_history_repeated_manual_interventions_ordered(
    seeded_database,
):
    """
    Multiple interventions for one exception appear in
    recording order with increasing intervention IDs.
    """

    connection = seeded_database

    try:
        _record_manual_resolution(
            connection,
            outcome="Still Open",
        )

        _record_manual_resolution(
            connection,
            intervention_type="Carrier email",
            external_party="CAR-900001 planning",
            resolution_summary="Revised pickup confirmed",
            recorded_by="Senior Planner",
            outcome="Still Open",
        )

        history = services.get_exception_history(
            connection,
            "EXC-900001",
        )

        interventions = [
            entry["detail"].split(" — ")[0]
            for entry in history
            if entry["event"]
            == "Manual intervention recorded"
        ]

        assert interventions == [
            "INT-000001",
            "INT-000002",
        ]

    finally:
        connection.close()


# ==================================================
# REGRESSION GUARDS
# ==================================================

def test_history_does_not_disturb_checkpoint_e_assessment(
    seeded_database,
):
    """
    The Checkpoint E recovery assessment contract is
    unchanged: a no-recommendation exception still exposes
    its evaluated-but-infeasible options.
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

        assert assessment["recommendation"] is None
        assert len(assessment["evaluated_options"]) == 3
        assert all(
            not option["feasible"]
            for option in assessment["evaluated_options"]
        )

    finally:
        connection.close()


def test_history_does_not_disturb_manual_resolution_flow(
    seeded_database,
):
    """
    The Checkpoint F manual-resolution flow is unchanged:
    eligibility, persistence and outcome rules behave as
    before the history service existed.
    """

    connection = seeded_database

    try:
        # A pending system action still blocks manual
        # resolution.
        action = _create_action(connection)

        with pytest.raises(Exception):
            _record_manual_resolution(
                connection,
                exception_id=action["exception_id"],
            )

        # And a resolved intervention still resolves the
        # exception through the service.
        _record_manual_resolution(
            connection,
            outcome="Resolved",
        )

        exception = connection.execute(
            """
            SELECT resolution_status
            FROM exceptions
            WHERE exception_id = 'EXC-900001'
            """
        ).fetchone()

        assert exception["resolution_status"] == "Resolved"

    finally:
        connection.close()


# ==================================================
# CHECKPOINT R — TRACEABILITY & STILL-OPEN EVIDENCE
# ==================================================

def test_history_outcome_entries_carry_persisted_evidence(
    seeded_database,
):
    """
    The outcome entry states the recorded estimated arrival
    against the required delivery date — the persisted
    evidence for the resolution verdict — rather than a
    generic status line.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _approve(connection, action)

        services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        outcome = history[-1]

        # Executed but the shipment still misses the required
        # delivery date: the outcome says so explicitly, with
        # both persisted dates (the recovery's new arrival
        # 2026-09-17 against the required 2026-09-15).
        assert outcome["event"] == "Exception still open"
        assert "2026-09-17" in outcome["detail"]
        assert "2026-09-15" in outcome["detail"]
        assert "still misses required delivery" in (
            outcome["detail"]
        )

        # The resolved case carries the same evidence shape:
        # extend the required delivery beyond the recorded
        # arrival and re-examine (no second execution — the
        # persisted resolution fields drive the entry).
        connection.execute(
            """
            UPDATE orders
            SET required_delivery_date = '2026-09-25'
            WHERE order_id = 'ORD-900001'
            """
        )
        connection.commit()

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        outcome = history[-1]

        # The exception is STILL open in the database (a
        # resolved transition only happens through a real
        # execution), so the entry remains the still-open
        # outcome — now with arrival meeting the required
        # date. This is the truthful evidence shape: the
        # status comes from the recorded state, not from a
        # date comparison in the history layer.
        assert outcome["event"] == "Exception still open"
        assert "2026-09-17" in outcome["detail"]
        assert "2026-09-25" in outcome["detail"]

    finally:
        connection.close()


def test_history_still_open_entry_never_precedes_execution(
    seeded_database,
):
    """
    Ordering guarantee for the executed-but-still-open
    story: detection, recommendation, approval, execution,
    then the still-open outcome — the current state is
    always the last entry, never implying resolution.
    """

    connection = seeded_database

    try:
        action = _create_action(connection)
        _approve(connection, action)

        services.execute_approved_recovery(
            connection,
            action["action_id"],
        )

        history = services.get_exception_history(
            connection,
            "EXC-900002",
        )

        events = _events(history)

        assert events == [
            "Exception detected",
            "Recovery options evaluated",
            "Recommendation generated",
            "Recovery approved",
            "Recovery executed",
            "Exception still open",
        ]

        # No resolution is implied anywhere in the timeline.
        assert "Exception resolved" not in events

    finally:
        connection.close()
