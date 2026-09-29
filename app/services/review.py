"""
Exception review / decision support service group (P12.3 decomposition).

The decision-engine review projection and the planner-
oriented recommendation rationale (weights, factor
breakdown, trade-offs, confidence basis).
"""

from app.config import DECISION_WEIGHTS
from app.decision_engine import get_recommendation
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo


def get_exception_review(
    connection,
    exception_id,
):
    """
    Build the decision-engine review for an exception.

    The returned dictionary contains the engine's
    recommendation structure unchanged, including the
    selected option_id when a feasible recommendation
    exists.
    """

    return get_recommendation(
        connection,
        exception_id,
    )


def get_latest_action(
    connection,
    exception_id,
):
    """
    Return the most recent recovery action for an
    exception, or None.

    The action is returned as a plain dictionary so no
    client depends on the persistence layer's row type
    (the versioned application-boundary contract,
    ADR-011).
    """

    action = recovery_actions_repo.get_latest_action_for_exception(
        connection,
        exception_id,
    )

    return dict(action) if action is not None else None


# Factor columns used in the rationale projection, in a
# fixed, planner-readable order. Each entry pairs the UI
# label with the decision-engine factor-score key, its
# configured weight key and the engine's weighted-
# contribution key.

RATIONALE_FACTORS = (
    ("Cost fit", "cost_score", "cost", "cost_contribution"),
    (
        "Transit fit",
        "transit_score",
        "transit",
        "transit_contribution",
    ),
    (
        "Risk fit",
        "risk_component",
        "risk",
        "risk_contribution",
    ),
    (
        "Priority fit",
        "priority_score",
        "priority_alignment",
        "priority_contribution",
    ),
)


def get_recommendation_rationale(review):
    """
    Build a structured, presentation-oriented rationale for
    an existing decision-engine review.

    This is a projection layer only: every value is taken
    from the engine's own output (factor scores, weighted
    contributions, decision scores, confidence) or from the
    authoritative decision configuration (DECISION_WEIGHTS).
    No factor is recomputed and no business rule is
    re-applied here.

    The projection exists so the planner can answer "why
    this option, and what trade-offs did it make?" without
    reverse-engineering the score:

    - factor_breakdown: one row per factor comparing the
      recommendation with each alternative (raw score,
      weight, weighted contribution);
    - trade_offs: per-alternative, factor-level statements
      of where an alternative beats the recommendation;
    - weights: the configured policy itself, straight from
      app.config (never duplicated in the UI);
    - confidence_basis: the factual basis of the confidence
      label (score separation) so it is not mistaken for a
      statistical probability.
    """

    recommendation = review.get("recommendation")

    if recommendation is None:

        return None

    weights = DECISION_WEIGHTS
    alternatives = review.get("alternatives") or []

    # One row per factor per compared option: the
    # recommendation first, then every alternative, all in
    # the engine's own ranking order.

    compared = [recommendation, *alternatives]

    factor_breakdown = []

    for factor_label, score_key, weight_key, contribution_key in (
        RATIONALE_FACTORS
    ):

        weight = weights[weight_key]

        factor_breakdown.append(
            {
                "factor": factor_label,
                "weight": weight,
                "values": [
                    {
                        "option_id": option["option_id"],
                        "transport_mode": (
                            option["transport_mode"]
                        ),
                        "score": option[score_key],
                        "contribution": option[
                            contribution_key
                        ],
                    }
                    for option in compared
                ],
            }
        )

    # Trade-offs: where an alternative is genuinely stronger
    # than the recommendation on an individual factor, say
    # so factually. The recommendation can still win because
    # the weighted total favours it.

    trade_offs = []

    for option in alternatives:

        stronger_factors = []

        for factor_label, score_key, _weight_key, _contribution_key in (
            RATIONALE_FACTORS
        ):

            if option[score_key] > recommendation[score_key]:

                stronger_factors.append(factor_label)

        if stronger_factors:

            trade_offs.append(
                {
                    "option_id": option["option_id"],
                    "transport_mode": option["transport_mode"],
                    "stronger_factors": stronger_factors,
                }
            )

    # Confidence semantics: the engine derives the label
    # from the separation between the recommendation's score
    # and the next-best alternative (sole feasible option is
    # reported High). Expose that basis explicitly so the
    # label is not misread as a probability of success.

    if not alternatives:

        confidence_basis = (
            "High confidence reflects a single feasible "
            "recovery option, not a probability of success."
        )

    else:

        next_best_score = max(
            option["decision_score"]
            for option in alternatives
        )

        score_gap = (
            recommendation["decision_score"]
            - next_best_score
        )

        confidence_basis = (
            "Derived from the separation between the "
            "recommended option's score and the next-best "
            f"alternative ({score_gap:.2f} points). It is "
            "not a probability of success."
        )

    return {
        "weights": {
            "cost": weights["cost"],
            "transit": weights["transit"],
            "risk": weights["risk"],
            "priority_alignment": (
                weights["priority_alignment"]
            ),
        },
        "factor_breakdown": factor_breakdown,
        "trade_offs": trade_offs,
        "confidence_basis": confidence_basis,
    }


def get_recovery_assessment(
    connection,
    exception_id,
):
    """
    Return the recovery assessment for an exception: the
    decision-engine review plus, when no recommendation
    exists, the evaluated options that explain why.

    When the engine has a feasible option to recommend,
    the assessment carries the recommendation and its
    alternatives exactly as the review does, plus a
    structured rationale (weights, per-factor breakdown,
    trade-offs, confidence basis) projected from the
    engine's own output. When it has none, the previously
    generated options - feasible and infeasible - are
    included as evaluated_options, each with its own
    operational data (mode, carrier, cost, transit, risk)
    and its feasibility verdict. The engines
    do not persist a granular rejection reason, so none is
    invented here: the verdict and the option's operational
    data are the strongest truthful information available.

    Returns None when the exception does not exist.
    """

    review = get_recommendation(
        connection,
        exception_id,
    )

    if review is None:
        return None

    if review["recommendation"] is not None:

        return {
            "recommendation": review["recommendation"],
            "alternatives": review["alternatives"],
            "evaluated_options": [],
            "rationale": get_recommendation_rationale(
                review,
            ),
        }

    return {
        "recommendation": None,
        "alternatives": [],
        "rationale": None,
        "evaluated_options": [
            {
                "option_id": option["option_id"],
                "transport_mode": option["transport_mode"],
                "carrier_id": option["carrier_id"],
                "estimated_cost": option["estimated_cost"],
                "estimated_transit_days": option[
                    "estimated_transit_days"
                ],
                "risk_score": option["risk_score"],
                "feasible": bool(option["feasible"]),
            }
            for option in (
                recovery_options_repo.get_options_for_exception(
                    connection,
                    exception_id,
                )
            )
        ],
    }
