"""
Data access for the recovery_options table.

All SQL is moved verbatim from the modules that previously
owned it (recovery-workflow context only; the recovery-option
generator keeps its own INSERT).

Every function accepts an existing sqlite connection and
never commits: transaction boundaries stay with the caller.
"""

# ==================================================
# OPTION ID GENERATION
# ==================================================

def get_next_option_number(connection):
    """
    Determine the next recovery-option number from the
    existing database records.

    This keeps option IDs deterministic and unique,
    mirroring the action-ID approach in the workflow
    engine, so every recovery option carries a stable
    identity that decisions, actions and execution can
    reference.
    """

    cursor = connection.cursor()

    options = cursor.execute(
        """
        SELECT option_id
        FROM recovery_options
        WHERE option_id LIKE 'OPT-%'
        """
    ).fetchall()

    numbers = []

    for option in options:

        option_id = option["option_id"]

        try:
            number = int(
                option_id.replace("OPT-", "")
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

def get_feasible_options_for_exception(
    connection,
    exception_id,
):
    """
    Return all feasible recovery options for an exception.

    Moved verbatim from the decision engine.
    """

    cursor = connection.cursor()

    options = cursor.execute(
        """
        SELECT
            option_id,
            exception_id,
            transport_mode,
            carrier_id,
            estimated_cost,
            estimated_transit_days,
            risk_score,
            feasible
        FROM recovery_options
        WHERE exception_id = ?
          AND feasible = 1
        """,
        (exception_id,),
    ).fetchall()

    return options


def get_option_by_id(
    connection,
    option_id,
):
    """
    Return a single recovery option by its option_id,
    or None when the option does not exist.

    Moved verbatim from the execution engine.
    """

    cursor = connection.cursor()

    option = cursor.execute(
        """
        SELECT
            option_id,
            exception_id,
            transport_mode,
            carrier_id,
            estimated_cost,
            estimated_transit_days,
            risk_score
        FROM recovery_options
        WHERE option_id = ?
        """,
        (option_id,),
    ).fetchone()

    return option
