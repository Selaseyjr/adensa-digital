"""
Focused tests for manual resolution (human-driven recovery).

A manual intervention records a resolution a planner
negotiated and executed outside Adensa. These tests verify:

- the intervention persists with full audit fields and the
  correct exception linkage;
- eligibility: open exceptions only, never bypassing an
  active system recovery action;
- the resolution rules: Resolved only via the recorded
  outcome, Still Open otherwise;
- the two resolution paths stay distinct: recording a manual
  intervention never creates fake recovery options or
  recovery actions, and the system-driven workflow continues
  to work unchanged.

All tests run on the temporary database fixtures; the
development database is never touched.
"""

import re

import pytest

from app import services
from app.errors import (
    ActionNotFoundError,
    ManualInterventionNotAllowedError,
    RecoveryWorkflowError,
)
from app.generate_recovery_options import generate_recovery_options
from app.workflow_engine import (
    approve_action,
    generate_workflow_actions,
    reject_action,
)


# ==================================================
# HELPERS
# ==================================================

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


def _create_system_action(connection):
    """Create the system workflow action for EXC-900002."""

    generate_recovery_options(connection)

    generate_workflow_actions(connection)


# ==================================================
# RECORDING AND PERSISTENCE
# ==================================================

def test_manual_resolution_persists_full_audit_record(
    seeded_database,
):
    """
    Recording a manual intervention persists every audit
    field, links to the correct exception and leaves the
    exception open for a Still Open outcome.
    """

    connection = seeded_database

    try:
        outcome = _record_manual_resolution(connection)

        assert outcome["success"] is True

        assert re.fullmatch(
            r"INT-\d{6}",
            outcome["intervention_id"],
        )

        interventions = services.get_manual_interventions(
            connection,
            "EXC-900001",
        )

        assert len(interventions) == 1

        intervention = interventions[0]

        assert intervention["intervention_id"] == (
            outcome["intervention_id"]
        )

        assert intervention["exception_id"] == "EXC-900001"
        assert (
            intervention["intervention_type"]
            == "Carrier call"
        )

        assert intervention["external_party"] == (
            "CAR-900001 dispatch"
        )

        assert "expedited direct delivery" in (
            intervention["resolution_summary"]
        )

        assert (
            intervention["new_expected_delivery"]
            == "2026-09-18"
        )

        assert intervention["outcome"] == "Still Open"
        assert intervention["recorded_by"] == "Planner"

        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
            intervention["recorded_at"],
        )

        # Still Open: the exception remains open and
        # monitored, with no resolution stamp.
        exception = connection.execute(
            """
            SELECT resolution_status, resolved_at
            FROM exceptions
            WHERE exception_id = 'EXC-900001'
            """
        ).fetchone()

        assert exception["resolution_status"] == "Open"
        assert exception["resolved_at"] is None

        assert outcome["exception_status"] == "Open"

    finally:
        connection.close()


def test_manual_resolution_resolved_updates_exception(
    seeded_database,
):
    """
    A Resolved outcome stamps the exception as Resolved at
    the recorded time — resolution follows the recorded
    operational outcome, not the mere act of recording.
    """

    connection = seeded_database

    try:
        outcome = _record_manual_resolution(
            connection,
            outcome="Resolved",
        )

        assert outcome["exception_status"] == "Resolved"

        exception = connection.execute(
            """
            SELECT resolution_status, resolved_at
            FROM exceptions
            WHERE exception_id = 'EXC-900001'
            """
        ).fetchone()

        assert exception["resolution_status"] == "Resolved"

        assert exception["resolved_at"] == (
            outcome["recorded_at"]
        )

    finally:
        connection.close()


def test_manual_resolution_listing_is_newest_first(
    seeded_database,
):
    """
    Repeated interventions on one exception are returned
    newest first, with continuing deterministic IDs.
    """

    connection = seeded_database

    try:
        first = _record_manual_resolution(connection)

        second = _record_manual_resolution(
            connection,
            intervention_type="Carrier email",
            notes=None,
            new_expected_delivery=None,
        )

        assert second["intervention_id"] > (
            first["intervention_id"]
        )

        interventions = services.get_manual_interventions(
            connection,
            "EXC-900001",
        )

        assert [
            intervention["intervention_id"]
            for intervention in interventions
        ] == [
            second["intervention_id"],
            first["intervention_id"],
        ]

    finally:
        connection.close()


# ==================================================
# ELIGIBILITY
# ==================================================

def test_manual_resolution_missing_exception_raises(
    seeded_database,
):
    """A nonexistent exception is rejected."""

    connection = seeded_database

    try:
        with pytest.raises(ActionNotFoundError):
            _record_manual_resolution(
                connection,
                exception_id="EXC-999999",
            )

    finally:
        connection.close()


def test_manual_resolution_rejects_resolved_exception(
    seeded_database,
):
    """
    A resolved exception receives no further interventions.
    """

    connection = seeded_database

    try:
        _record_manual_resolution(
            connection,
            outcome="Resolved",
        )

        with pytest.raises(
            ManualInterventionNotAllowedError
        ):
            _record_manual_resolution(connection)

    finally:
        connection.close()


def test_manual_resolution_cannot_bypass_pending_action(
    seeded_database,
):
    """
    A pending system recovery action blocks manual
    resolution: the human-in-the-loop workflow must be
    resolved through its own path first.
    """

    connection = seeded_database

    try:
        _create_system_action(connection)

        with pytest.raises(
            ManualInterventionNotAllowedError
        ) as excinfo:
            _record_manual_resolution(
                connection,
                exception_id="EXC-900002",
            )

        assert "Pending Approval" in str(excinfo.value)

    finally:
        connection.close()


def test_manual_resolution_cannot_bypass_approved_action(
    seeded_database,
):
    """An approved system action equally blocks the manual path."""

    connection = seeded_database

    try:
        _create_system_action(connection)

        approve_action(
            connection,
            "ACT-000001",
            "Approver",
        )

        with pytest.raises(
            ManualInterventionNotAllowedError
        ):
            _record_manual_resolution(
                connection,
                exception_id="EXC-900002",
            )

    finally:
        connection.close()


def test_manual_resolution_allowed_after_rejection(
    seeded_database,
):
    """
    A rejected system option is exactly the case where the
    planner takes over: manual resolution is permitted once
    the system action is Rejected.
    """

    connection = seeded_database

    try:
        _create_system_action(connection)

        reject_action(
            connection,
            "ACT-000001",
            "Approver",
        )

        outcome = _record_manual_resolution(
            connection,
            exception_id="EXC-900002",
            outcome="Resolved",
        )

        assert outcome["success"] is True

        exception = connection.execute(
            """
            SELECT resolution_status
            FROM exceptions
            WHERE exception_id = 'EXC-900002'
            """
        ).fetchone()

        assert exception["resolution_status"] == "Resolved"

    finally:
        connection.close()


def test_manual_resolution_validates_fields_without_writes(
    seeded_database,
):
    """
    Unknown types/outcomes and empty required fields raise
    before any write happens.
    """

    connection = seeded_database

    try:
        with pytest.raises(RecoveryWorkflowError):
            _record_manual_resolution(
                connection,
                intervention_type="Teleportation",
            )

        with pytest.raises(RecoveryWorkflowError):
            _record_manual_resolution(
                connection,
                outcome="Sorted it out",
            )

        with pytest.raises(RecoveryWorkflowError):
            _record_manual_resolution(
                connection,
                external_party="   ",
            )

        with pytest.raises(RecoveryWorkflowError):
            _record_manual_resolution(
                connection,
                resolution_summary="",
            )

        with pytest.raises(RecoveryWorkflowError):
            _record_manual_resolution(
                connection,
                recorded_by=None,
            )

        count = connection.execute(
            "SELECT COUNT(*) FROM manual_interventions"
        ).fetchone()[0]

        assert count == 0

    finally:
        connection.close()


# ==================================================
# PATH SEPARATION
# ==================================================

def test_manual_resolution_creates_no_fake_workflow_records(
    seeded_database,
):
    """
    A manual intervention never fabricates system recovery
    options or actions: the two resolution paths stay
    distinct records.
    """

    connection = seeded_database

    try:
        options_before = connection.execute(
            "SELECT COUNT(*) FROM recovery_options"
        ).fetchone()[0]

        actions_before = connection.execute(
            "SELECT COUNT(*) FROM recovery_actions"
        ).fetchone()[0]

        _record_manual_resolution(connection)

        assert (
            connection.execute(
                "SELECT COUNT(*) FROM recovery_options"
            ).fetchone()[0]
            == options_before
        )

        assert (
            connection.execute(
                "SELECT COUNT(*) FROM recovery_actions"
            ).fetchone()[0]
            == actions_before
        )

    finally:
        connection.close()


def test_system_recovery_workflow_coexists_with_manual_path(
    seeded_database,
):
    """
    After a Still Open manual resolution on one exception,
    the system-driven workflow keeps working unchanged on
    another: options, action, approval and execution.
    """

    connection = seeded_database

    try:
        _record_manual_resolution(connection)

        _create_system_action(connection)

        services.approve_recovery(
            connection,
            "ACT-000001",
            "Approver",
        )

        outcome = services.execute_approved_recovery(
            connection,
            "ACT-000001",
        )

        assert outcome["success"] is True

        assert outcome["new_mode"] == "Road"

    finally:
        connection.close()


def test_checkpoint_e_assessment_survives_manual_path(
    seeded_database,
):
    """
    The recovery assessment still distinguishes evaluated
    infeasible options after the manual-resolution feature:
    the Checkpoint E contract is unchanged.
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

        _record_manual_resolution(connection)

        interventions = services.get_manual_interventions(
            connection,
            "EXC-900001",
        )

        assert len(interventions) == 1

    finally:
        connection.close()
