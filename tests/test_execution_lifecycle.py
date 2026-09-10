from app.workflow_engine import (
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
    REJECTED,
    validate_transition,
)


def test_execution_lifecycle():
    """
    Validate the workflow rules governing recovery execution.

    This test does not modify the production database.
    """

    # --------------------------------------------------
    # APPROVED → EXECUTED
    # --------------------------------------------------

    validate_transition(
        APPROVED,
        EXECUTED,
    )

    print(
        "✓ Approved → Executed accepted."
    )

    # --------------------------------------------------
    # PENDING APPROVAL → EXECUTED
    # --------------------------------------------------

    try:

        validate_transition(
            PENDING_APPROVAL,
            EXECUTED,
        )

    except ValueError:

        print(
            "✓ Pending Approval → Executed rejected."
        )

    else:

        raise AssertionError(
            "Pending Approval → Executed "
            "was incorrectly accepted."
        )

    # --------------------------------------------------
    # REJECTED → EXECUTED
    # --------------------------------------------------

    try:

        validate_transition(
            REJECTED,
            EXECUTED,
        )

    except ValueError:

        print(
            "✓ Rejected → Executed rejected."
        )

    else:

        raise AssertionError(
            "Rejected → Executed "
            "was incorrectly accepted."
        )

    # --------------------------------------------------
    # EXECUTED → EXECUTED
    # --------------------------------------------------

    try:

        validate_transition(
            EXECUTED,
            EXECUTED,
        )

    except ValueError:

        print(
            "✓ Executed → Executed rejected."
        )

    else:

        raise AssertionError(
            "Executed → Executed "
            "was incorrectly accepted."
        )

    print(
        "Execution lifecycle validation complete."
    )

    print(
        "✓ No database records were modified."
    )


if __name__ == "__main__":

    test_execution_lifecycle()