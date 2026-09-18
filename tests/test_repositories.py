"""
Focused tests for the recovery repository layer.

These tests verify data access only. Business rules remain
owned by the engines and are exercised by the engine and
lifecycle tests. The seeded_database fixture provides an
isolated temporary database; the development database is
never touched.
"""

from app.generate_recovery_options import generate_recovery_options
from app.repositories import exceptions_repo
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo
from app.repositories import shipments_repo


# ==================================================
# RECOVERY OPTIONS REPOSITORY
# ==================================================

def test_get_feasible_options_for_exception(seeded_database):
    """
    The repository returns the feasible options of an
    exception with their columns intact.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        modes = {option["transport_mode"] for option in options}

        assert modes == {"Air", "Road", "Rail"}
        assert all(option["feasible"] == 1 for option in options)

        for option in options:
            assert option["exception_id"] == "EXC-900002"
            assert option["option_id"].startswith("OPT-")

    finally:
        connection.close()


def test_get_feasible_options_excludes_low_severity_exception(seeded_database):
    """
    The Low-severity exception has no recovery options, so
    the repository returns an empty list for it.
    """

    connection = seeded_database

    try:
        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900001",
        )

        assert options == []

    finally:
        connection.close()


def test_get_option_by_id(seeded_database):
    """
    A specific option is retrievable by option_id and
    belongs to the expected exception.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        assert len(options) == 3

        first_option = options[0]

        option = recovery_options_repo.get_option_by_id(
            connection,
            first_option["option_id"],
        )

        assert option is not None
        assert option["option_id"] == first_option["option_id"]
        assert option["exception_id"] == "EXC-900002"
        assert option["transport_mode"] == first_option["transport_mode"]

    finally:
        connection.close()


def test_get_option_by_id_returns_none_for_missing_option(seeded_database):
    """
    An unknown option_id yields None instead of an error.
    """

    connection = seeded_database

    try:
        option = recovery_options_repo.get_option_by_id(
            connection,
            "OPT-999999",
        )

        assert option is None

    finally:
        connection.close()


def test_get_next_option_number(seeded_database):
    """
    The next option number continues after existing
    OPT-% identifiers.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        existing_numbers = [
            int(option["option_id"].replace("OPT-", ""))
            for option in options
        ]

        next_number = recovery_options_repo.get_next_option_number(
            connection
        )

        assert next_number == max(existing_numbers) + 1

    finally:
        connection.close()


# ==================================================
# RECOVERY ACTIONS REPOSITORY
# ==================================================

def _insert_test_action(
    connection,
    action_id,
    option_id=None,
    status="Pending Approval",
):
    """Insert one action row for repository-level tests."""

    recovery_actions_repo.insert_recovery_action(
        connection,
        action_id=action_id,
        exception_id="EXC-900002",
        option_id=option_id,
        action_type="Recovery",
        description="Repository test action.",
        status=status,
    )


def test_insert_and_get_action_by_id(seeded_database):
    """
    A created action is retrievable by action_id with its
    option_id association intact.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        option_id = options[0]["option_id"]

        _insert_test_action(
            connection,
            "ACT-900001",
            option_id=option_id,
        )

        connection.commit()

        action = recovery_actions_repo.get_action_by_id(
            connection,
            "ACT-900001",
        )

        assert action is not None
        assert action["exception_id"] == "EXC-900002"
        assert action["option_id"] == option_id
        assert action["status"] == "Pending Approval"

    finally:
        connection.close()


def test_get_active_action_for_exception(seeded_database):
    """
    The idempotency lookup finds an active action for its
    exception.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        _insert_test_action(
            connection,
            "ACT-900002",
            option_id=options[0]["option_id"],
        )

        connection.commit()

        active = recovery_actions_repo.get_active_action_for_exception(
            connection,
            "EXC-900002",
        )

        assert active is not None
        assert active["action_id"] == "ACT-900002"

        active = recovery_actions_repo.get_active_action_for_exception(
            connection,
            "EXC-900001",
        )

        assert active is None

    finally:
        connection.close()


def test_get_latest_action_for_exception(seeded_database):
    """
    The UI-style latest lookup returns the highest
    action_id for an exception.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        option_id = options[0]["option_id"]

        _insert_test_action(
            connection,
            "ACT-900003",
            option_id=option_id,
        )
        _insert_test_action(
            connection,
            "ACT-900004",
            option_id=option_id,
        )

        connection.commit()

        latest = recovery_actions_repo.get_latest_action_for_exception(
            connection,
            "EXC-900002",
        )

        assert latest is not None
        assert latest["action_id"] == "ACT-900004"
        assert latest["action_type"] == "Recovery"

    finally:
        connection.close()


def test_update_action_status_transition(seeded_database):
    """
    The approval-style status update writes the actor and
    timestamp and only applies to the expected previous
    status.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        _insert_test_action(
            connection,
            "ACT-900005",
            option_id=options[0]["option_id"],
        )

        connection.commit()

        rows_updated = recovery_actions_repo.update_action_status(
            connection,
            action_id="ACT-900005",
            new_status="Approved",
            actor="Repo Test",
            timestamp="2026-09-10 12:00:00",
            expected_current_status="Pending Approval",
        )

        connection.commit()

        assert rows_updated == 1

        action = recovery_actions_repo.get_action_by_id(
            connection,
            "ACT-900005",
        )

        assert action["status"] == "Approved"

        detail = connection.execute(
            """
            SELECT approved_by, approved_at
            FROM recovery_actions
            WHERE action_id = 'ACT-900005'
            """
        ).fetchone()

        assert detail["approved_by"] == "Repo Test"
        assert detail["approved_at"] == "2026-09-10 12:00:00"

        stale = recovery_actions_repo.update_action_status(
            connection,
            action_id="ACT-900005",
            new_status="Approved",
            actor="Repo Test",
            timestamp="2026-09-10 12:00:00",
            expected_current_status="Pending Approval",
        )

        assert stale == 0

    finally:
        connection.close()


def test_mark_action_executed(seeded_database):
    """
    The execution-style update sets Executed with a
    timestamp and only applies from the expected
    previous status.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        option_id = options[0]["option_id"]

        _insert_test_action(
            connection,
            "ACT-900006",
            option_id=option_id,
        )

        connection.commit()

        rows_updated = recovery_actions_repo.mark_action_executed(
            connection,
            action_id="ACT-900006",
            executed_at="2026-09-13 12:00:00",
            expected_current_status="Approved",
        )

        assert rows_updated == 0

        recovery_actions_repo.update_action_status(
            connection,
            action_id="ACT-900006",
            new_status="Approved",
            actor="Repo Test",
            timestamp="2026-09-10 12:00:00",
            expected_current_status="Pending Approval",
        )

        connection.commit()

        rows_updated = recovery_actions_repo.mark_action_executed(
            connection,
            action_id="ACT-900006",
            executed_at="2026-09-13 12:00:00",
            expected_current_status="Approved",
        )

        assert rows_updated == 1

        action = recovery_actions_repo.get_action_by_id(
            connection,
            "ACT-900006",
        )

        assert action["status"] == "Executed"

        detail = connection.execute(
            """
            SELECT executed_at
            FROM recovery_actions
            WHERE action_id = 'ACT-900006'
            """
        ).fetchone()

        assert detail["executed_at"] == "2026-09-13 12:00:00"

    finally:
        connection.close()


def test_count_actions_by_status(seeded_database):
    """
    The KPI count reflects inserted action statuses.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        option_id = options[0]["option_id"]

        before = recovery_actions_repo.count_actions_by_status(
            connection,
            status="Pending Approval",
        )

        _insert_test_action(
            connection,
            "ACT-900007",
            option_id=option_id,
        )

        connection.commit()

        after = recovery_actions_repo.count_actions_by_status(
            connection,
            status="Pending Approval",
        )

        assert after == before + 1

    finally:
        connection.close()


# ==================================================
# EXCEPTIONS REPOSITORY
# ==================================================

def test_count_exceptions(seeded_database):
    """
    The repository counts all exception records and the
    count follows inserts.
    """

    connection = seeded_database

    try:
        before = exceptions_repo.count_exceptions(connection)

        assert before == 2

        exceptions_repo.insert_exceptions(
            connection,
            [
                (
                    "EXC-900101",
                    "SHP-900001",
                    "Delivery Delay",
                    "Medium",
                    "2026-09-10 12:00:00",
                    "Test exception",
                    100,
                    "Open",
                    None,
                ),
            ],
        )

        connection.commit()

        assert exceptions_repo.count_exceptions(connection) == before + 1

    finally:
        connection.close()


def test_count_open_exceptions(seeded_database):
    """
    Both seeded exceptions are open, so the count is two
    and excludes resolved records.
    """

    connection = seeded_database

    try:
        assert exceptions_repo.count_open_exceptions(connection) == 2

        exceptions_repo.insert_exceptions(
            connection,
            [
                (
                    "EXC-900102",
                    "SHP-900001",
                    "Delivery Delay",
                    "Medium",
                    "2026-09-10 12:00:00",
                    "Resolved test exception",
                    100,
                    "Resolved",
                    "2026-09-11 12:00:00",
                ),
            ],
        )

        connection.commit()

        assert exceptions_repo.count_open_exceptions(connection) == 2

    finally:
        connection.close()


def test_count_open_critical_exceptions(seeded_database):
    """
    The severity filter returns only open Critical
    exceptions.
    """

    connection = seeded_database

    try:
        assert exceptions_repo.count_open_critical_exceptions(
            connection
        ) == 0

        exceptions_repo.insert_exceptions(
            connection,
            [
                (
                    "EXC-900103",
                    "SHP-900002",
                    "Delivery Delay",
                    "Critical",
                    "2026-09-10 12:00:00",
                    "Critical test exception",
                    9000,
                    "Open",
                    None,
                ),
            ],
        )

        connection.commit()

        assert exceptions_repo.count_open_critical_exceptions(
            connection
        ) == 1

    finally:
        connection.close()


def test_get_open_exceptions_inbox(seeded_database):
    """
    The inbox returns open exceptions with shipment and
    order context, ordered by severity rank, and excludes
    resolved records.
    """

    connection = seeded_database

    try:
        inbox = exceptions_repo.get_open_exceptions_inbox(
            connection
        )

        assert [
            row["exception_id"] for row in inbox
        ] == ["EXC-900002", "EXC-900001"]

        high = inbox[0]

        assert high["transport_mode"] == "Sea"
        assert high["priority"] == "Medium"
        assert high["required_delivery_date"] == "2026-09-15"

        exceptions_repo.insert_exceptions(
            connection,
            [
                (
                    "EXC-900104",
                    "SHP-900001",
                    "Delivery Delay",
                    "Medium",
                    "2026-09-10 12:00:00",
                    "Resolved test exception",
                    100,
                    "Resolved",
                    "2026-09-11 12:00:00",
                ),
            ],
        )

        connection.commit()

        inbox = exceptions_repo.get_open_exceptions_inbox(
            connection
        )

        assert [
            row["exception_id"] for row in inbox
        ] == ["EXC-900002", "EXC-900001"]

    finally:
        connection.close()


def test_get_exception_resolution_status(seeded_database):
    """
    The status lookup returns the current resolution
    status and None for a missing exception.
    """

    connection = seeded_database

    try:
        row = exceptions_repo.get_exception_resolution_status(
            connection,
            "EXC-900002",
        )

        assert row["resolution_status"] == "Open"

        row = exceptions_repo.get_exception_resolution_status(
            connection,
            "EXC-999999",
        )

        assert row is None

    finally:
        connection.close()


# ==================================================
# SHIPMENTS REPOSITORY
# ==================================================

def test_get_shipments_with_required_delivery(seeded_database):
    """
    The detection read returns shipments ordered by ID
    with the joined required delivery date.
    """

    connection = seeded_database

    try:
        shipments = shipments_repo.get_shipments_with_required_delivery(
            connection
        )

        assert [
            row["shipment_id"] for row in shipments
        ] == ["SHP-900001", "SHP-900002"]

        assert shipments[0]["required_delivery_date"] == "2026-09-15"
        assert shipments[0]["estimated_arrival"] == "2026-09-13"
        assert shipments[1]["estimated_arrival"] == "2026-09-20"

    finally:
        connection.close()


def test_get_shipment_transport_mode_and_carrier(seeded_database):
    """
    The transport-mode lookup returns the shipment's mode
    and carrier, and None for a missing shipment.
    """

    connection = seeded_database

    try:
        row = shipments_repo.get_shipment_transport_mode_and_carrier(
            connection,
            "SHP-900001",
        )

        assert row["transport_mode"] == "Road"
        assert row["carrier_id"] == "CAR-900001"

        row = shipments_repo.get_shipment_transport_mode_and_carrier(
            connection,
            "SHP-999999",
        )

        assert row is None

    finally:
        connection.close()


def test_get_shipment_delivery_state(seeded_database):
    """
    The delivery-state lookup returns mode, carrier and
    estimated arrival, and None for a missing shipment.
    """

    connection = seeded_database

    try:
        row = shipments_repo.get_shipment_delivery_state(
            connection,
            "SHP-900002",
        )

        assert row["transport_mode"] == "Sea"
        assert row["carrier_id"] == "CAR-900001"
        assert row["estimated_arrival"] == "2026-09-20"

        row = shipments_repo.get_shipment_delivery_state(
            connection,
            "SHP-999999",
        )

        assert row is None

    finally:
        connection.close()


def test_get_latest_recovery_event_id(seeded_database):
    """
    The recovery-event lookup returns the newest recovery
    event for a shipment and None when none exists.
    """

    connection = seeded_database

    try:
        assert shipments_repo.get_latest_recovery_event_id(
            connection,
            "SHP-900002",
        ) is None

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO shipment_events (
                event_id,
                shipment_id,
                event_type,
                event_timestamp,
                location,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "EVT-TEST-000001",
                "SHP-900002",
                "Recovery Executed",
                "2026-09-13 12:00:00",
                "Network",
                "Test recovery event",
            ),
        )

        cursor.execute(
            """
            INSERT INTO shipment_events (
                event_id,
                shipment_id,
                event_type,
                event_timestamp,
                location,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "EVT-TEST-000002",
                "SHP-900002",
                "Recovery Executed",
                "2026-09-14 12:00:00",
                "Network",
                "Newer test recovery event",
            ),
        )

        connection.commit()

        row = shipments_repo.get_latest_recovery_event_id(
            connection,
            "SHP-900002",
        )

        assert row["event_id"] == "EVT-TEST-000002"

    finally:
        connection.close()


# ==================================================
# EXCEPTION OPERATIONAL CONTEXT (SHARED BY ENGINES)
# ==================================================

def test_get_exception_operational_context(seeded_database):
    """
    The shared context read returns the exception with its
    shipment and order fields under the approved contract.
    """

    connection = seeded_database

    try:
        context = exceptions_repo.get_exception_operational_context(
            connection,
            "EXC-900002",
        )

        assert context is not None
        assert context["exception_id"] == "EXC-900002"
        assert context["shipment_id"] == "SHP-900002"
        assert context["priority"] == "Medium"
        assert context["resolution_status"] == "Open"
        assert context["planned_departure"] == "2026-09-12"
        assert context["required_delivery_date"] == "2026-09-15"
        assert context["shipment_status"] == "In Transit"
        assert context["transport_mode"] == "Sea"
        assert context["order_id"] == "ORD-900001"

    finally:
        connection.close()


def test_get_exception_operational_context_missing(seeded_database):
    """
    An unknown exception ID yields None; the engines keep
    their own missing-record handling.
    """

    connection = seeded_database

    try:
        context = exceptions_repo.get_exception_operational_context(
            connection,
            "EXC-999999",
        )

        assert context is None

    finally:
        connection.close()


def test_get_open_exception_contexts(seeded_database):
    """
    The open-context collection returns open exceptions in
    exception_id order and excludes resolved records.
    """

    connection = seeded_database

    try:
        contexts = exceptions_repo.get_open_exception_contexts(
            connection
        )

        # ORDER BY e.exception_id: lexicographic order.
        assert [
            row["exception_id"] for row in contexts
        ] == ["EXC-900001", "EXC-900002"]

        high = contexts[1]

        assert high["transport_mode"] == "Sea"
        assert high["required_delivery_date"] == "2026-09-15"

        exceptions_repo.insert_exceptions(
            connection,
            [
                (
                    "EXC-900105",
                    "SHP-900001",
                    "Delivery Delay",
                    "Medium",
                    "2026-09-10 12:00:00",
                    "Resolved context test exception",
                    100,
                    "Resolved",
                    "2026-09-11 12:00:00",
                ),
            ],
        )

        connection.commit()

        contexts = exceptions_repo.get_open_exception_contexts(
            connection
        )

        assert [
            row["exception_id"] for row in contexts
        ] == ["EXC-900001", "EXC-900002"]

    finally:
        connection.close()


# ==================================================
# CLI-SUPPORT READS
# ==================================================

def test_get_open_exception_ids(seeded_database):
    """
    The open-exception iteration returns open exception IDs in
    exception_id order and excludes resolved exceptions.
    """

    connection = seeded_database

    try:
        ids = [
            row["exception_id"]
            for row in exceptions_repo.get_open_exception_ids(
                connection
            )
        ]

        assert ids == ["EXC-900001", "EXC-900002"]

        connection.execute(
            """
            UPDATE exceptions
            SET resolution_status = 'Resolved'
            WHERE exception_id = 'EXC-900002'
            """
        )
        connection.commit()

        ids = [
            row["exception_id"]
            for row in exceptions_repo.get_open_exception_ids(
                connection
            )
        ]

        assert ids == ["EXC-900001"]

    finally:
        connection.close()


def test_get_execution_result(seeded_database):
    """
    The execution-result read joins action, exception and
    shipment state; a missing action yields None.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        options = recovery_options_repo.get_feasible_options_for_exception(
            connection,
            "EXC-900002",
        )

        _insert_test_action(
            connection,
            "ACT-900002",
            option_id=options[0]["option_id"],
        )

        connection.commit()

        result = recovery_actions_repo.get_execution_result(
            connection,
            "ACT-900002",
        )

        assert result is not None
        assert result["action_id"] == "ACT-900002"
        assert result["exception_id"] == "EXC-900002"
        assert result["shipment_id"] == "SHP-900002"
        assert result["action_status"] == "Pending Approval"

        missing = recovery_actions_repo.get_execution_result(
            connection,
            "ACT-DOES-NOT-EXIST",
        )

        assert missing is None

    finally:
        connection.close()


# ==================================================
# ENTITY-LEVEL IDEMPOTENCY READS
# ==================================================

def test_get_shipment_ids_with_exceptions(seeded_database):
    """
    The idempotency read returns exactly the shipment IDs
    already represented by an exception.
    """

    connection = seeded_database

    try:
        shipment_ids = exceptions_repo.get_shipment_ids_with_exceptions(
            connection
        )

        assert shipment_ids == {"SHP-900001", "SHP-900002"}

    finally:
        connection.close()


def test_get_next_exception_number_on_empty_database(temp_database):
    """
    On an empty database the next exception number is 1:
    fresh bootstrap keeps the existing numbering behavior.
    """

    connection = temp_database

    try:
        assert exceptions_repo.get_next_exception_number(
            connection
        ) == 1

    finally:
        connection.close()


def test_get_next_exception_number_continues_on_populated(
    seeded_database,
):
    """
    On a populated database the next exception number
    continues after the highest existing EXC-% identifier,
    avoiding primary-key collisions.
    """

    connection = seeded_database

    try:
        assert exceptions_repo.get_next_exception_number(
            connection
        ) == 900003

    finally:
        connection.close()


def test_get_exception_ids_with_options(seeded_database):
    """
    The idempotency read is empty before generation and
    contains exactly the exceptions that carry options
    after it — the Low-severity exception stays excluded.
    """

    connection = seeded_database

    try:
        assert recovery_options_repo.get_exception_ids_with_options(
            connection
        ) == set()

        generate_recovery_options(connection)

        assert recovery_options_repo.get_exception_ids_with_options(
            connection
        ) == {"EXC-900002"}

    finally:
        connection.close()


# ==================================================
# GENERATOR ENTITY-LEVEL IDEMPOTENCY
# ==================================================

def test_generate_recovery_options_is_repeatable(seeded_database):
    """
    Running the generator twice creates no duplicate
    options: the second run skips every exception that
    already carries options.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        count_after_first = connection.execute(
            "SELECT COUNT(*) FROM recovery_options"
        ).fetchone()[0]

        assert count_after_first == 3

        generate_recovery_options(connection)

        count_after_second = connection.execute(
            "SELECT COUNT(*) FROM recovery_options"
        ).fetchone()[0]

        assert count_after_second == count_after_first

    finally:
        connection.close()


def test_generate_recovery_options_processes_new_exceptions(
    seeded_database,
):
    """
    On a populated database the generator leaves existing
    options untouched and processes only genuinely new
    open exceptions.
    """

    connection = seeded_database

    try:
        generate_recovery_options(connection)

        assert connection.execute(
            "SELECT COUNT(*) FROM recovery_options"
        ).fetchone()[0] == 3

        # A new shipment with a new High-severity open
        # exception arrives after the first generation run.
        connection.execute(
            """
            INSERT INTO shipments (
                shipment_id, order_id, carrier_id, origin,
                destination, transport_mode, quantity, weight_kg,
                volume_m3, priority, planned_departure,
                actual_departure, planned_arrival,
                estimated_arrival, actual_arrival, status,
                shipping_cost, distance_km, current_location,
                last_updated
            )
            VALUES (
                'SHP-900003', 'ORD-900001', 'CAR-900001',
                'Rotterdam', 'Hamburg', 'Sea', 80, 800, 4,
                'Medium', '2026-09-12', '2026-09-12',
                '2026-09-14', '2026-09-20', NULL, 'In Transit',
                400, 1500, 'At sea', '2026-09-10 12:00:00'
            )
            """
        )

        connection.execute(
            """
            INSERT INTO exceptions (
                exception_id, shipment_id, exception_type,
                severity, detected_at, description,
                estimated_impact, resolution_status, resolved_at
            )
            VALUES (
                'EXC-900003', 'SHP-900003', 'Delivery Delay',
                'High', '2026-09-10 12:00:00',
                'New fixture exception: six days late', 6000,
                'Open', NULL
            )
            """
        )

        connection.commit()

        generate_recovery_options(connection)

        existing_options = (
            recovery_options_repo.get_feasible_options_for_exception(
                connection,
                "EXC-900002",
            )
        )

        new_options = (
            recovery_options_repo.get_feasible_options_for_exception(
                connection,
                "EXC-900003",
            )
        )

        assert len(existing_options) == 3
        assert len(new_options) == 3
        assert all(
            option["exception_id"] == "EXC-900003"
            for option in new_options
        )

    finally:
        connection.close()
