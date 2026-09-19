"""
Data access for the manual_interventions table.

The manual_interventions table records human resolutions
performed outside Adensa (carrier calls, supplier or
customer coordination, externally negotiated transport
arrangements) against an exception. These records are
deliberately distinct from the system-generated recovery
workflow: recovery_options are system-evaluated
possibilities and recovery_actions are system-generated
actions, while a manual intervention documents a resolution
that a human negotiated and executed externally.

Every function accepts an existing sqlite connection and
never commits: transaction boundaries stay with the caller.
"""

# ==================================================
# INTERVENTION ID GENERATION
# ==================================================

def get_next_intervention_number(connection):
    """
    Determine the next manual-intervention number from the
    existing database records.

    This keeps intervention IDs deterministic and unique,
    mirroring the exception, option and action numbering
    approach, so recorded interventions continue the
    sequence on a populated database without primary-key
    collisions.
    """

    cursor = connection.cursor()

    interventions = cursor.execute(
        """
        SELECT intervention_id
        FROM manual_interventions
        WHERE intervention_id LIKE 'INT-%'
        """
    ).fetchall()

    numbers = []

    for intervention in interventions:

        intervention_id = intervention["intervention_id"]

        try:
            number = int(
                intervention_id.replace("INT-", "")
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

def get_interventions_for_exception(
    connection,
    exception_id,
):
    """
    Return the recorded manual interventions for an
    exception, newest first.
    """

    cursor = connection.cursor()

    interventions = cursor.execute(
        """
        SELECT
            intervention_id,
            exception_id,
            intervention_type,
            external_party,
            resolution_summary,
            new_expected_delivery,
            outcome,
            notes,
            recorded_by,
            recorded_at
        FROM manual_interventions
        WHERE exception_id = ?
        ORDER BY intervention_id DESC
        """,
        (exception_id,),
    ).fetchall()

    return interventions


# ==================================================
# WRITES
# ==================================================

def insert_manual_intervention(
    connection,
    intervention_record,
):
    """
    Insert one manual-intervention record and return the
    number of rows inserted.

    No commit happens here: the caller owns the transaction
    so the intervention record and the exception status
    update are created atomically.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO manual_interventions (
            intervention_id,
            exception_id,
            intervention_type,
            external_party,
            resolution_summary,
            new_expected_delivery,
            outcome,
            notes,
            recorded_by,
            recorded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        intervention_record,
    )

    return cursor.rowcount
