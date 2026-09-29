"""
Sustainability comparison service group (P12.3 decomposition).

Estimated transport emissions for an exception's recovery
options — informational decision support only.
"""

from app.repositories import shipments_repo

from app.sustainability import build_sustainability_comparison

from app.services.context import get_exception_context
from app.services.review import get_recovery_assessment


def get_sustainability_comparison(
    connection,
    exception_id,
):
    """
    Estimated transport emissions for an exception's
    deterministic recommendation and its feasible
    alternatives.

    Purely informational decision support (Checkpoint V): the
    calculation uses the persisted shipment weight and route
    distance plus the configured prototype emissions factors,
    and it never influences the recommendation, the scores,
    the confidence or any workflow state.

    Returns None when the exception or the deterministic
    recommendation does not exist (nothing to compare),
    otherwise the structured comparison projection from the
    sustainability module — including honest per-option
    unavailable records when an estimate cannot be produced.
    """

    exception_context = get_exception_context(
        connection,
        exception_id,
    )

    if exception_context is None:
        return None

    assessment = get_recovery_assessment(
        connection,
        exception_id,
    )

    if (
        assessment is None
        or assessment.get("recommendation") is None
    ):
        return None

    inputs = shipments_repo.get_shipment_emissions_inputs(
        connection,
        exception_context["shipment_id"],
    )

    if inputs is None:
        return {
            "status": "unavailable",
            "reason": "Shipment record not found.",
        }

    return build_sustainability_comparison(
        inputs["weight_kg"],
        inputs["distance_km"],
        [
            assessment["recommendation"],
            *assessment["alternatives"],
        ],
    )
