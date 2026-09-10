from app.database import get_connection
from app.workflow_engine import (
    validate_transition,
    PENDING_APPROVAL,
    APPROVED,
    REJECTED,
    EXECUTED,
)


def test_workflow_idempotency():
    """
    Validate that workflow state rules prevent the same
    action from being approved more than once.

    This test does not modify the production database.
    """

    # --------------------------------------------------
    # TEST APPROVAL
    # --------------------------------------------------

    validate_transition(
        PENDING_APPROVAL,
        APPROVED,
    )

    print("✓ First approval transition accepted.")

    # --------------------------------------------------
    # TEST DUPLICATE APPROVAL
    # --------------------------------------------------

    try:

        validate_transition(
            APPROVED,
            APPROVED,
        )

    except ValueError:

        print(
            "✓ Duplicate approval transition rejected."
        )

    else:

        raise AssertionError(
            "Duplicate approval transition was "
            "incorrectly accepted."
        )

    # --------------------------------------------------
    # TEST OTHER DUPLICATE / INVALID OPERATIONS
    # --------------------------------------------------

    invalid_transitions = [
        (
            REJECTED,
            APPROVED,
            "Rejected → Approved",
        ),
        (
            EXECUTED,
            APPROVED,
            "Executed → Approved",
        ),
        (
            APPROVED,
            APPROVED,
            "Approved → Approved",
        ),
    ]

    for current_status, new_status, description in invalid_transitions:

        try:

            validate_transition(
                current_status,
                new_status,
            )

        except ValueError:

            print(
                f"✓ {description} rejected."
            )

        else:

            raise AssertionError(
                f"Invalid transition was accepted: "
                f"{description}"
            )

    print(
        "Workflow idempotency validation complete."
    )
    print(
        "✓ No database records were modified."
    )


if __name__ == "__main__":

    test_workflow_idempotency()