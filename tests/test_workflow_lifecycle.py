from app.workflow_engine import (
    validate_transition,
    PENDING_APPROVAL,
    APPROVED,
    REJECTED,
    EXECUTED,
)


def test_valid_transitions():
    valid_transitions = [
        (PENDING_APPROVAL, APPROVED),
        (PENDING_APPROVAL, REJECTED),
    ]

    for current_status, new_status in valid_transitions:
        validate_transition(current_status, new_status)


def test_invalid_transitions():
    invalid_transitions = [
        (PENDING_APPROVAL, EXECUTED),
        (REJECTED, EXECUTED),
        (EXECUTED, APPROVED),
        (APPROVED, APPROVED),
    ]

    for current_status, new_status in invalid_transitions:
        try:
            validate_transition(current_status, new_status)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Invalid transition was allowed: "
                f"{current_status} -> {new_status}"
            )


if __name__ == "__main__":
    test_valid_transitions()
    test_invalid_transitions()

    print("Workflow lifecycle validation complete.")
    print("✓ Valid transitions accepted.")
    print("✓ Invalid transitions rejected.")