"""
Data access for the recovery_actions table.

All SQL is moved verbatim from the modules that previously
owned it (workflow engine, execution engine and the workflow
context of the UI).

Every function accepts an existing sqlite connection and
never commits: transaction boundaries stay with the caller.
"""

# ==================================================
# ACTION ID GENERATION
# ==================================================

def get_next_action_number(connection):
    """
    Determine the next recovery-action number from the
    existing database records.

    This prevents action IDs from restarting at ACT-000001
    when new workflow actions are generated later.
    """

    cursor = connection.cursor()

    actions = cursor.execute(
        """
        SELECT action_id
        FROM recovery_actions
        WHERE action_id LIKE 'ACT-%'
        """
    ).fetchall()

    numbers = []

    for action in actions:

        action_id = action["action_id"]

        try:
            number = int(
                action_id.replace("ACT-", "")
            )

            numbers.append(number)

        except ValueError:
            continue

    if not numbers:
        return 1

    return max(numbers) + 1


# ==================================================
# QUERIES
# ==================================================

def get_active_action_for_exception(
    connection,
    exception_id,
):
    """
    Return the active recovery action for an exception
    (Pending Approval, Approved or Executed), or None.

    Moved verbatim from the workflow engine idempotency
    check in create_recovery_action.
    """

    cursor = connection.cursor()

    existing_action = cursor.execute(
        """
        SELECT
            action_id,
            status
        FROM recovery_actions
        WHERE exception_id = ?
          AND status IN (
              'Pending Approval',
              'Approved',
              'Executed'
          )
        LIMIT 1
        """,
        (exception_id,),
    ).fetchone()

    return existing_action


def get_action_by_id(
    connection,
    action_id,
):
    """
    Return a single recovery action by action_id, or None
    when the action does not exist.

    Moved verbatim from the execution engine.
    """

    cursor = connection.cursor()

    action = cursor.execute(
        """
        SELECT
            action_id,
            exception_id,
            option_id,
            status
        FROM recovery_actions
        WHERE action_id = ?
        """,
        (action_id,),
    ).fetchone()

    return action


def get_action_status_and_id(
    connection,
    action_id,
):
    """
    Return action_id and status for an action, or None.

    Moved verbatim from the workflow engine
    approve/reject lookup.
    """

    cursor = connection.cursor()

    action = cursor.execute(
        """
        SELECT
            action_id,
            status
        FROM recovery_actions
        WHERE action_id = ?
        """,
        (action_id,),
    ).fetchone()

    return action


def get_latest_action_for_exception(
    connection,
    exception_id,
):
    """
    Return the most recent recovery action for an
    exception, or None.

    Moved verbatim from the UI workflow-action query
    in app/main.py.
    """

    cursor = connection.cursor()

    action = cursor.execute(
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
        (exception_id,),
    ).fetchone()

    return action


# ==================================================
# WRITES
# ==================================================

def insert_recovery_action(
    connection,
    action_id,
    exception_id,
    option_id,
    action_type,
    description,
    status,
):
    """
    Insert a recovery action.

    Moved verbatim from the workflow engine
    create_recovery_action.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO recovery_actions (
            action_id,
            exception_id,
            option_id,
            action_type,
            description,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            action_id,
            exception_id,
            option_id,
            action_type,
            description,
            status,
        ),
    )


def update_action_status(
    connection,
    action_id,
    new_status,
    actor,
    timestamp,
    expected_current_status,
):
    """
    Update a recovery action's status with approval audit
    fields (also used for rejection, matching the current
    schema which has no separate rejection fields).

    Moved verbatim from the workflow engine
    approve_action / reject_action.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE recovery_actions
        SET
            status = ?,
            approved_by = ?,
            approved_at = ?
        WHERE action_id = ?
          AND status = ?
        """,
        (
            new_status,
            actor,
            timestamp,
            action_id,
            expected_current_status,
        ),
    )

    return cursor.rowcount


def mark_action_executed(
    connection,
    action_id,
    executed_at,
    expected_current_status,
):
    """
    Mark a recovery action as Executed.

    Moved verbatim from the execution engine
    execute_recovery_action.
    """

    cursor = connection.cursor()

    action_update = cursor.execute(
        """
        UPDATE recovery_actions
        SET
            status = ?,
            executed_at = ?
        WHERE action_id = ?
          AND status = ?
        """,
        (
            "Executed",
            executed_at,
            action_id,
            expected_current_status,
        ),
    )

    return action_update.rowcount


def list_actions(
    connection,
    limit=5,
):
    """
    Return the first recovery actions ordered by action_id.

    Moved verbatim from the workflow engine
    show_sample_actions.
    """

    cursor = connection.cursor()

    actions = cursor.execute(
        """
        SELECT
            action_id,
            exception_id,
            option_id,
            action_type,
            description,
            status,
            approved_by,
            approved_at
        FROM recovery_actions
        ORDER BY action_id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return actions


def count_actions_by_status(
    connection,
    status,
):
    """
    Count recovery actions with a given status.

    Moved verbatim from the UI KPI query
    in app/main.py.
    """

    cursor = connection.cursor()

    count = cursor.execute(
        """
        SELECT COUNT(*)
        FROM recovery_actions
        WHERE status = ?
        """,
        (status,),
    ).fetchone()[0]

    return count


def get_status_counts(connection):
    """
    Return the recovery-action status distribution
    grouped by status, ordered by count descending.

    Moved verbatim from the workflow engine
    show_workflow_summary.
    """

    cursor = connection.cursor()

    statuses = cursor.execute(
        """
        SELECT
            status,
            COUNT(*) AS count
        FROM recovery_actions
        GROUP BY status
        ORDER BY count DESC
        """
    ).fetchall()

    return statuses
