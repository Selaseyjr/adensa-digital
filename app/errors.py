"""
Typed domain errors for the Adensa Digital recovery workflow.

RecoveryWorkflowError marks failures that belong to the
application's business rules — invalid workflow transitions,
missing records, closed-exception guards, optimistic-lock
conflicts, and idempotency violations raised by the workflow
and execution engines.

It subclasses ValueError so every existing caller and test
that catches ValueError continues to work unchanged, while the
application service layer can now distinguish genuine domain
failures from programming or infrastructure errors.
"""


class RecoveryWorkflowError(ValueError):
    """
    A recovery-workflow business-rule violation.

    Raised by the workflow and execution engines when an
    operation cannot be performed because the domain state
    does not permit it.
    """


class ActionNotFoundError(RecoveryWorkflowError):
    """
    The addressed recovery action does not exist.
    """


class InvalidTransitionError(RecoveryWorkflowError):
    """
    The requested workflow transition is not permitted
    from the action's current state.
    """


class ManualInterventionNotAllowedError(RecoveryWorkflowError):
    """
    Manual resolution is not permitted for the exception in
    its current state — for example when a system-generated
    recovery action is already pending approval or approved,
    or the exception no longer exists in an open state.
    """
