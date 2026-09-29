"""
Decision brief service group (P12.3 decomposition).

Composes the structured evidence an advisory AI provider
receives and produces the planner-facing AI decision brief.
"""

from app.ai_support import (
    AiProviderError,
    BriefValidationError,
    unavailable_brief,
    validate_decision_brief,
)

from app.services.context import get_exception_context
from app.services.history import get_exception_history
from app.services.review import get_recovery_assessment

from app.services.sustainability import (
    get_sustainability_comparison,
)


def build_decision_brief_evidence(
    connection,
    exception_id,
):
    """
    Compose the structured evidence an advisory AI provider
    receives: exception facts, the deterministic assessment
    (recommendation, alternatives, rationale) and the
    persisted operational history.

    Every value is established operational data read through
    the existing service functions — nothing is invented for
    the AI layer, and the AI layer receives nothing the
    planner cannot already see in the investigation view.
    Returns None when the exception does not exist.
    """

    exception = get_exception_context(
        connection,
        exception_id,
    )

    if exception is None:
        return None

    assessment = get_recovery_assessment(
        connection,
        exception_id,
    )

    history = get_exception_history(
        connection,
        exception_id,
    ) or []

    return {
        "exception": exception,
        "recommendation": (
            assessment["recommendation"]
            if assessment
            else None
        ),
        "alternatives": (
            assessment["alternatives"]
            if assessment
            else []
        ),
        "rationale": (
            assessment.get("rationale")
            if assessment
            else None
        ),
        "sustainability": get_sustainability_comparison(
            connection,
            exception_id,
        ),
        "history": history,
    }


def get_decision_brief(
    connection,
    exception_id,
    provider=None,
):
    """
    Produce the planner-facing AI decision brief for one
    exception.

    Advisory layer only. The provider receives the structured
    deterministic evidence and must return contract-valid
    output; it can never change operational state because it
    never touches the engines, the repositories or the
    connection, and the brief is never persisted. A brief that
    mentions identifiers absent from the evidence, claims an
    approved/executed/resolved action, or violates the output
    contract is rejected, and the caller receives the honest
    unavailable state instead of unverified text.

    Failure behaviour is total: missing evidence, a provider
    error or an invalid brief all return the structured
    unavailable state and never raise — investigation, the
    deterministic recommendation, and every workflow action
    keep working exactly as before.

    provider: injectable for testing. Defaults to the module
    default (resolved at call time so tests can replace it).
    No provider call happens unless the caller asks for a
    brief: the control tower, inbox and investigation views
    never trigger one automatically.
    """

    evidence = build_decision_brief_evidence(
        connection,
        exception_id,
    )

    if evidence is None:
        return unavailable_brief(
            "Exception not found — no decision brief "
            "available."
        )

    recommendation = evidence["recommendation"]

    if recommendation is None:
        return unavailable_brief(
            "No deterministic recommendation exists for this "
            "exception, so there is no decision to explain. "
            "The exception remains open for manual "
            "intervention."
        )

    if provider is None:
        # Resolved at call time through the package facade so
        # the historical patch seam keeps working: tests patch
        # services.DEFAULT_PROVIDER at the package namespace,
        # exactly as they did against the pre-split module.
        from app import services

        provider = services.DEFAULT_PROVIDER

    try:

        raw_brief = provider(evidence)

        return validate_decision_brief(
            raw_brief,
            evidence,
        )

    except (
        AiProviderError,
        BriefValidationError,
    ) as error:

        return unavailable_brief(
            f"AI decision brief unavailable ({error}). "
            "Deterministic recommendation remains available."
        )
