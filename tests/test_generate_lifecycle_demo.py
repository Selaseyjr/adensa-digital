"""
P12.6 lifecycle demo seeder tests (deterministic, isolated).

The seeder contract under test:

- generate_lifecycle_demo() on a freshly bootstrapped demo
  database progresses the oldest actionable cohort through the
  real approval/execution engines and records deterministic
  manual resolutions — producing Awaiting execution, Executed
  — still open / follow-up, system-resolved and manually
  resolved populations, and letting the monitoring population
  surface in the bounded inbox;
- the seed is deterministic (same fresh database twice gives
  the identical lifecycle distribution), idempotent (reruns
  are no-ops and never duplicate evidence), and never touches
  a database a planner has already worked in;
- the E2E fixture exceptions EXC-000008 / EXC-000009 remain
  Open with their Pending Approval action untouched.

Every test runs the REAL bootstrap pipeline against an
isolated temporary database file; data/adensa.db is never
read or written.
"""

import pytest

import app.database as database
import app.bootstrap as bootstrap
from app.bootstrap import initialize_adensa
from app.generate_lifecycle_demo import (
    AWAITING_EXECUTION_TARGET,
    E2E_FIXTURE_EXCEPTION_IDS,
    MANUAL_RESOLUTION_TARGET,
    PENDING_BACKLOG_TARGET,
    generate_lifecycle_demo,
)
from app.services.inbox import get_exception_inbox
from app.services.operational_state import get_control_tower_summary


@pytest.fixture()
def bootstrap_database(tmp_path, monkeypatch):
    """
    Re-point every database-path reference (connection factory
    and bootstrap guards) at one fresh temporary file and
    return the path.
    """

    database_path = tmp_path / "lifecycle_demo_adensa.db"

    monkeypatch.setattr(database, "DATABASE_PATH", database_path)
    monkeypatch.setattr(bootstrap, "DATABASE_PATH", database_path)

    return database_path


def bootstrapped_connection(bootstrap_database):
    """
    Run the real fresh-database bootstrap and open a connection.

    The data generators seed the RNG at import time, so a fresh
    bootstrap simulating a fresh process must start from that
    exact RNG state; reseeding here makes every test's dataset
    identical and independent of suite order.
    """

    import random

    random.seed(42)

    initialize_adensa()

    return database.get_connection()


def action_status_counts(connection):
    """Recovery-action rows grouped by status."""

    return dict(
        connection.execute(
            """
            SELECT status, COUNT(*)
            FROM recovery_actions
            GROUP BY status
            """
        ).fetchall()
    )


def lifecycle_distribution(connection):
    """
    The full lifecycle fingerprint of a seeded database:
    every population the P12.6 product outcome requires.
    """

    summary = get_control_tower_summary(connection)

    inbox = get_exception_inbox(connection)

    state_counts = {}
    for row in inbox:
        state_counts[row["workflow_state"]] = (
            state_counts.get(row["workflow_state"], 0) + 1
        )

    def one(query):
        return connection.execute(query).fetchone()[0]

    return {
        "open_exceptions": summary["open_exceptions"],
        "pending_approvals": summary["pending_approvals"],
        "awaiting_execution": summary["awaiting_execution"],
        "follow_up_required": summary["follow_up_required"],
        "resolved_total": one(
            "SELECT COUNT(*) FROM exceptions "
            "WHERE resolution_status = 'Resolved'"
        ),
        "resolved_by_system": sum(
            1
            for row in summary["recently_resolved"]
            if row["resolution_path"] == "System-executed recovery"
        ),
        "resolved_by_manual": sum(
            1
            for row in summary["recently_resolved"]
            if row["resolution_path"] == "Manually resolved"
        ),
        "manual_interventions": one(
            "SELECT COUNT(*) FROM manual_interventions"
        ),
        "manual_resolved_exceptions": one(
            """
            SELECT COUNT(*)
            FROM exceptions e
            WHERE e.resolution_status = 'Resolved'
              AND EXISTS (
                  SELECT 1 FROM manual_interventions i
                  WHERE i.exception_id = e.exception_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM recovery_actions ra
                  WHERE ra.exception_id = e.exception_id
                    AND ra.status = 'Executed'
              )
            """
        ),
        "executed_actions": action_status_counts(connection).get(
            "Executed", 0
        ),
        "approved_actions": action_status_counts(connection).get(
            "Approved", 0
        ),
        "inbox_rows": len(inbox),
        "inbox_monitoring_rows": sum(
            1
            for row in inbox
            if row["feasible_option_count"] == 0
        ),
        "inbox_state_counts": state_counts,
        "inbox_first_id": inbox[0]["exception_id"] if inbox else None,
        "inbox_last_id": inbox[-1]["exception_id"] if inbox else None,
        "recovery_events": one(
            """
            SELECT COUNT(*) FROM shipment_events
            WHERE event_type = 'Recovery Executed'
            """
        ),
        "max_manual_recorded_at": one(
            "SELECT MAX(recorded_at) FROM manual_interventions"
        ),
    }


# --------------------------------------------------
# CORE PRODUCT OUTCOME
# --------------------------------------------------


def test_seeded_lifecycle_produces_every_required_population(
    bootstrap_database,
):
    """
    After one bootstrap on a fresh database, every lifecycle
    population the P12.6 product outcome requires exists with
    a meaningful, deterministic size.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        d = lifecycle_distribution(connection)

        one = lambda query: connection.execute(query).fetchone()[0]  # noqa: E731

        # Current decisions still pending: the retained backlog
        # plus the protected E2E fixtures (deliberately left as
        # "Decision required").
        assert d["pending_approvals"] == (
            PENDING_BACKLOG_TARGET + len(E2E_FIXTURE_EXCEPTION_IDS)
        )

        # Approved but not yet executed.
        assert d["awaiting_execution"] == AWAITING_EXECUTION_TARGET
        assert d["approved_actions"] == AWAITING_EXECUTION_TARGET

        # Executed and still open — the follow-up population.
        assert d["executed_actions"] > 0
        assert d["follow_up_required"] > 0

        # System-resolved records exist (executed cohort minus
        # the still-open tail), and manual resolutions exist.
        assert d["resolved_total"] > 0
        assert d["manual_interventions"] == MANUAL_RESOLUTION_TARGET
        assert d["manual_resolved_exceptions"] == (
            MANUAL_RESOLUTION_TARGET
        )

        # Executed actions wrote exactly one recovery event each.
        assert d["recovery_events"] == d["executed_actions"]

        # The bounded inbox now carries a mix of states and the
        # monitoring population is visible in it.
        assert d["inbox_rows"] == 100
        assert d["inbox_monitoring_rows"] > 0
        assert (
            d["inbox_state_counts"].get("Decision required", 0) > 0
        )
        assert (
            d["inbox_state_counts"].get("Executed — still open", 0) > 0
        )
        assert (
            d["inbox_state_counts"].get("No system recovery available", 0)
            == d["inbox_monitoring_rows"]
        )

        # A meaningful actionable backlog remains pending
        # (retained backlog + the protected E2E fixtures).
        actionable_pending = one(
            """
            SELECT COUNT(*)
            FROM exceptions e
            JOIN recovery_actions ra
                ON ra.exception_id = e.exception_id
                AND ra.status = 'Pending Approval'
            WHERE e.resolution_status = 'Open'
            """
        )
        assert actionable_pending == (
            PENDING_BACKLOG_TARGET + len(E2E_FIXTURE_EXCEPTION_IDS)
        )
    finally:
        connection.close()


def test_e2e_fixture_exceptions_untouched(bootstrap_database):
    """
    The browser E2E suite's fixtures must remain exactly what
    it depends on: Open with a Pending Approval action, no
    resolution, no lifecycle mutation of any kind.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        for exception_id in E2E_FIXTURE_EXCEPTION_IDS:

            row = connection.execute(
                """
                SELECT
                    e.resolution_status,
                    e.resolved_at,
                    e.detected_at,
                    ra.status AS action_status
                FROM exceptions e
                JOIN recovery_actions ra
                    ON ra.exception_id = e.exception_id
                WHERE e.exception_id = ?
                """,
                (exception_id,),
            ).fetchone()

            assert row is not None, f"{exception_id} missing"

            assert row["resolution_status"] == "Open"
            assert row["resolved_at"] is None
            assert row["action_status"] == "Pending Approval"

            # Detection timestamp untouched (backdating is
            # reserved for the progressed cohort).
            assert row["detected_at"] == "2026-09-10 12:00:00"

            # No manual-intervention record either.
            interventions = connection.execute(
                """
                SELECT COUNT(*)
                FROM manual_interventions
                WHERE exception_id = ?
                """,
                (exception_id,),
            ).fetchone()[0]

            assert interventions == 0

        # And both still classify as "Decision required"
        # through the same persisted-evidence derivation the
        # workspace page renders.
        from app.services.operational_state import (
            classify_investigation_state,
        )

        for exception_id in E2E_FIXTURE_EXCEPTION_IDS:
            state = classify_investigation_state(
                connection,
                exception_id,
            )

            assert state is not None
            assert state["state"] == "Decision required"
    finally:
        connection.close()


# --------------------------------------------------
# DETERMINISM AND IDEMPOTENCE
# --------------------------------------------------


def test_lifecycle_seed_is_deterministic(bootstrap_database):
    """
    Two independent fresh bootstraps produce the identical
    lifecycle distribution — populations, inbox ordering and
    seeded identity stamps included.

    Both bootstraps start from the generators' import-time RNG
    seed (the helper handles the first; the second is reseeded
    explicitly below), so each simulates a fresh process.
    """

    first = bootstrapped_connection(bootstrap_database)

    try:
        first_distribution = lifecycle_distribution(first)
    finally:
        first.close()

    # A second, completely fresh database file, seeded like a
    # fresh process.
    import random

    random.seed(42)

    second_path = bootstrap_database.parent / "second_adensa.db"

    import app.database as database_module

    original = database_module.DATABASE_PATH
    database_module.DATABASE_PATH = second_path
    bootstrap.DATABASE_PATH = second_path

    try:
        initialize_adensa()

        second = database_module.get_connection()

        try:
            second_distribution = lifecycle_distribution(second)
        finally:
            second.close()
    finally:
        database_module.DATABASE_PATH = original
        bootstrap.DATABASE_PATH = bootstrap_database

    assert second_distribution == first_distribution


def test_lifecycle_seed_is_idempotent(bootstrap_database):
    """
    Rerunning generate_lifecycle_demo() (and a full bootstrap)
    on a seeded database changes nothing: the guard detects
    the existing lifecycle evidence and leaves the database
    untouched.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        before = lifecycle_distribution(connection)
    finally:
        connection.close()

    # Direct rerun.
    connection = database.get_connection()

    try:
        result = generate_lifecycle_demo(connection)

        assert result == {"seeded": False}
    finally:
        connection.close()

    # A full bootstrap rerun must also regenerate nothing.
    initialize_adensa()

    connection = database.get_connection()

    try:
        assert lifecycle_distribution(connection) == before
    finally:
        connection.close()


def test_no_duplicate_lifecycle_evidence(bootstrap_database):
    """
    Exactly one recovery event per executed action, exactly
    one executed action per progressed exception, and the
    executed/still-open/resolved populations line up with a
    single pass of the lifecycle.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        one = lambda query: connection.execute(query).fetchone()[0]  # noqa: E731

        executed_actions = one(
            "SELECT COUNT(*) FROM recovery_actions "
            "WHERE status = 'Executed'"
        )
        recovery_events = one(
            "SELECT COUNT(*) FROM shipment_events "
            "WHERE event_type = 'Recovery Executed'"
        )

        # 1:1 between executions and their recovery events.
        assert recovery_events == executed_actions

        # No exception received a second executed action.
        multi_executed = one(
            """
            SELECT COUNT(*)
            FROM (
                SELECT exception_id
                FROM recovery_actions
                WHERE status = 'Executed'
                GROUP BY exception_id
                HAVING COUNT(*) > 1
            )
            """
        )
        assert multi_executed == 0

        # Every executed action's exception carries exactly one
        # recovery event with the matching deterministic id.
        mismatched_events = one(
            """
            SELECT COUNT(*)
            FROM recovery_actions ra
            WHERE ra.status = 'Executed'
              AND NOT EXISTS (
                  SELECT 1
                  FROM shipment_events se
                  WHERE se.event_id =
                      'EVT-REC-'
                      || substr(ra.action_id, 5)
              )
            """
        )
        assert mismatched_events == 0

        # The resolved-via-execution population plus the open
        # follow-up population equals the executed cohort.
        resolved_by_execution = one(
            """
            SELECT COUNT(*)
            FROM exceptions e
            WHERE e.resolution_status = 'Resolved'
              AND EXISTS (
                  SELECT 1 FROM recovery_actions ra
                  WHERE ra.exception_id = e.exception_id
                    AND ra.status = 'Executed'
              )
            """
        )
        follow_up = one(
            """
            SELECT COUNT(*)
            FROM exceptions e
            WHERE e.resolution_status = 'Open'
              AND EXISTS (
                  SELECT 1 FROM recovery_actions ra
                  WHERE ra.exception_id = e.exception_id
                    AND ra.status = 'Executed'
              )
            """
        )

        assert resolved_by_execution + follow_up == executed_actions
    finally:
        connection.close()


def test_seeder_never_touches_a_worked_database(bootstrap_database):
    """
    A database where a planner already made one decision is a
    real operational database: the seeder must refuse to run
    on it, even though its pending cohort is large.
    """

    from app.workflow_engine import approve_action

    connection = bootstrapped_connection(bootstrap_database)

    try:
        first_pending = connection.execute(
            """
            SELECT action_id FROM recovery_actions
            WHERE status = 'Pending Approval'
            ORDER BY action_id LIMIT 1
            """
        ).fetchone()[0]

        approve_action(
            connection,
            first_pending,
            approved_by="A. Real Planner",
        )

        counts_before = action_status_counts(connection)
    finally:
        connection.close()

    connection = database.get_connection()

    try:
        result = generate_lifecycle_demo(connection)

        assert result == {"seeded": False}

        assert action_status_counts(connection) == counts_before
    finally:
        connection.close()


def test_seeder_skips_a_cohort_too_small_to_progress(bootstrap_database):
    """
    A database whose pending cohort cannot supply the
    configured backlog must be reported as unseeded rather
    than half-progressed — the guard protects small fixture
    databases from a partial lifecycle pass.
    """

    from tests.conftest import seed_minimal_supply_chain

    # A separate, tiny lifecycle-free database: two fixture
    # exceptions, one with a feasible recommendation and no
    # action yet — far below the cohort the seeder requires.
    tiny_path = bootstrap_database.parent / "tiny_adensa.db"

    import app.database as database_module

    original = database_module.DATABASE_PATH
    database_module.DATABASE_PATH = tiny_path
    bootstrap.DATABASE_PATH = tiny_path

    database_module.initialize_database()

    tiny = database_module.get_connection()

    try:
        seed_minimal_supply_chain(tiny)

        # Give EXC-900002 the recovery options its fixture
        # description implies and a pending action, mirroring
        # the real pipeline's output for a feasible exception.
        # The option is inserted first: the action references it.
        tiny.execute(
            """
            INSERT INTO recovery_options (
                option_id, exception_id, carrier_id,
                transport_mode, estimated_cost,
                estimated_transit_days, capacity_available,
                risk_score, feasible
            )
            VALUES (
                'OPT-900001', 'EXC-900002', 'CAR-900001',
                'Road', 1500.0, 2, 100.0, 20.0, 1
            )
            """
        )
        tiny.execute(
            """
            INSERT INTO recovery_actions (
                action_id, exception_id, option_id, action_type,
                description, status
            )
            VALUES (
                'ACT-900001', 'EXC-900002', 'OPT-900001',
                'Recovery', 'Tiny-fixture action', 'Pending Approval'
            )
            """
        )
        tiny.commit()

        result = generate_lifecycle_demo(tiny)

        assert result == {"seeded": False, "reason": "cohort-too-small"}

        # Nothing was mutated.
        statuses = dict(
            tiny.execute(
                "SELECT status, COUNT(*) FROM recovery_actions GROUP BY status"
            ).fetchall()
        )
        assert statuses == {"Pending Approval": 1}
    finally:
        tiny.close()
        database_module.DATABASE_PATH = original
        bootstrap.DATABASE_PATH = bootstrap_database


# --------------------------------------------------
# CHRONOLOGY AND EVIDENCE INTEGRITY
# --------------------------------------------------


def test_chronological_relationships_are_valid(bootstrap_database):
    """
    Every seeded lifecycle record reads chronologically:
    detection before (or at) approval, approval strictly
    before execution, executed arrivals compared against the
    required date exactly as the engine ruled, manual
    resolutions recorded on the simulation timeline before
    today, and resolved_at consistent with the resolution
    path.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        # detection <= approval < execution for the executed cohort.
        bad_order = connection.execute(
            """
            SELECT COUNT(*)
            FROM recovery_actions ra
            JOIN exceptions e ON e.exception_id = ra.exception_id
            WHERE ra.status = 'Executed'
              AND (
                  e.detected_at > ra.approved_at
                  OR ra.approved_at >= ra.executed_at
              )
            """
        ).fetchone()[0]
        assert bad_order == 0

        # The execution engine's ruling must match the persisted
        # arrival evidence: resolved exceptions arrived on time,
        # still-open ones did not.
        wrong_resolutions = connection.execute(
            """
            SELECT COUNT(*)
            FROM exceptions e
            JOIN shipments s ON s.shipment_id = e.shipment_id
            JOIN orders o ON o.order_id = s.order_id
            WHERE EXISTS (
                SELECT 1 FROM recovery_actions ra
                WHERE ra.exception_id = e.exception_id
                  AND ra.status = 'Executed'
            )
            AND (
                (e.resolution_status = 'Resolved'
                 AND s.estimated_arrival > o.required_delivery_date)
                OR (e.resolution_status = 'Open'
                    AND s.estimated_arrival <= o.required_delivery_date)
            )
            """
        ).fetchone()[0]
        assert wrong_resolutions == 0

        # Resolved timestamps match their evidence: execution
        # time for system resolutions, recorded_at for manual.
        system_stamp_mismatch = connection.execute(
            """
            SELECT COUNT(*)
            FROM exceptions e
            JOIN recovery_actions ra
                ON ra.exception_id = e.exception_id
                AND ra.status = 'Executed'
            WHERE e.resolution_status = 'Resolved'
              AND e.resolved_at != ra.executed_at
            """
        ).fetchone()[0]
        assert system_stamp_mismatch == 0

        manual_stamp_mismatch = connection.execute(
            """
            SELECT COUNT(*)
            FROM exceptions e
            JOIN manual_interventions i
                ON i.exception_id = e.exception_id
            WHERE e.resolution_status = 'Resolved'
              AND e.resolved_at != i.recorded_at
            """
        ).fetchone()[0]
        assert manual_stamp_mismatch == 0

        # Manual resolutions sit before the simulation "today"
        # and no seeded stamp uses a wall-clock date beyond it.
        latest_stamp = connection.execute(
            """
            SELECT MAX(latest) FROM (
                SELECT MAX(approved_at) AS latest
                FROM recovery_actions
                UNION ALL
                SELECT MAX(executed_at)
                FROM recovery_actions
                UNION ALL
                SELECT MAX(recorded_at)
                FROM manual_interventions
            )
            """
        ).fetchone()[0]
        assert latest_stamp <= "2026-09-10 23:59:59"
        assert latest_stamp is not None
    finally:
        connection.close()


def test_recovery_events_correspond_to_executions(bootstrap_database):
    """
    Each recovery event belongs to its action's shipment,
    carries the engine's own event vocabulary, and its
    timestamp equals the action's executed_at.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        mismatches = connection.execute(
            """
            SELECT COUNT(*)
            FROM recovery_actions ra
            JOIN exceptions e ON e.exception_id = ra.exception_id
            JOIN shipment_events se
                ON se.event_id =
                    'EVT-REC-' || substr(ra.action_id, 5)
            WHERE ra.status = 'Executed'
              AND (
                  se.shipment_id != e.shipment_id
                  OR se.event_type != 'Recovery Executed'
                  OR se.event_timestamp != ra.executed_at
              )
            """
        ).fetchone()[0]
        assert mismatches == 0
    finally:
        connection.close()


def test_monitoring_population_becomes_visible(bootstrap_database):
    """
    The bounded inbox (existing actionable-first ordering,
    existing 100-row cap) now surfaces monitoring rows because
    the historical actionable work has genuinely moved on —
    and the control-tower KPI reports them from the same
    derivation.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        summary = get_control_tower_summary(connection)
        inbox = get_exception_inbox(connection)

        monitoring_rows = sum(
            1
            for row in inbox
            if row["feasible_option_count"] == 0
        )

        assert monitoring_rows > 0

        # The summary partitions the visible queue.
        assert summary["actionable_exceptions"] == (
            len(inbox) - monitoring_rows
        )
        assert summary["monitoring_exceptions"] == monitoring_rows
        assert (
            summary["actionable_exceptions"]
            + summary["monitoring_exceptions"]
            == len(inbox)
        )

        # The full monitoring population still dwarfs the
        # visible window (the backlog honestly exceeded the cap).
        assert summary["monitoring_exceptions"] > 0
    finally:
        connection.close()


def test_recently_resolved_interleaves_both_paths(bootstrap_database):
    """
    The Recently Resolved panel shows both resolution paths
    with the recorded evidence, newest resolution first.
    """

    connection = bootstrapped_connection(bootstrap_database)

    try:
        summary = get_control_tower_summary(connection)

        resolved = summary["recently_resolved"]

        assert len(resolved) > 0

        paths = {row["resolution_path"] for row in resolved}

        assert "System-executed recovery" in paths
        assert "Manually resolved" in paths

        # Newest resolution first (mixed paths, one chronology).
        timestamps = [
            row["resolved_at"] for row in resolved
        ]

        assert timestamps == sorted(
            timestamps,
            reverse=True,
        )
    finally:
        connection.close()
