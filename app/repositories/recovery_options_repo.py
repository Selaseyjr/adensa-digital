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


def get_options_for_exception(
    connection,
    exception_id,
):
    """
    Return ALL recovery options for an exception, feasible
    and infeasible, ordered by option_id.

    Used for the recovery assessment: when no feasible
    option exists, the evaluated-but-infeasible options
    explain why no recommendation is available. Mirrors the
    feasible-options read above without its feasibility
    filter.
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
        ORDER BY option_id
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


def get_exception_ids_with_options(connection):
    """
    Return the set of exception IDs that already carry
    recovery options.

    Entity-level idempotency read for the recovery-option
    generator: exceptions in this set are skipped so the
    generator can run repeatedly on a populated database
    without duplicating options.
    """

    cursor = connection.cursor()

    rows = cursor.execute(
        """
        SELECT DISTINCT exception_id
        FROM recovery_options
        """
    ).fetchall()

    return {row["exception_id"] for row in rows}
