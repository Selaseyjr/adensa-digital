from app.config import (
    DECISION_WEIGHTS,
    COST_BENCHMARK,
    TRANSIT_BENCHMARK,
    RISK_BENCHMARK,
)
from app.repositories import exceptions_repo
from app.repositories import recovery_options_repo


# ==================================================
# SCORING FUNCTIONS
# ==================================================

def calculate_cost_score(cost):
    """Convert recovery cost into a normalized score."""

    if cost <= COST_BENCHMARK["excellent"]:
        return 100

    if cost <= COST_BENCHMARK["acceptable"]:
        return 100 - (
            (cost - COST_BENCHMARK["excellent"])
            / (
                COST_BENCHMARK["acceptable"]
                - COST_BENCHMARK["excellent"]
            )
        ) * 25

    if cost <= COST_BENCHMARK["expensive"]:
        return 75 - (
            (cost - COST_BENCHMARK["acceptable"])
            / (
                COST_BENCHMARK["expensive"]
                - COST_BENCHMARK["acceptable"]
            )
        ) * 40

    return 35


def calculate_transit_score(days):
    """Convert recovery transit time into a normalized score."""

    if days <= TRANSIT_BENCHMARK["excellent"]:
        return 100

    if days <= TRANSIT_BENCHMARK["acceptable"]:
        return 100 - (
            (days - TRANSIT_BENCHMARK["excellent"])
            / (
                TRANSIT_BENCHMARK["acceptable"]
                - TRANSIT_BENCHMARK["excellent"]
            )
        ) * 25

    if days <= TRANSIT_BENCHMARK["slow"]:
        return 75 - (
            (days - TRANSIT_BENCHMARK["acceptable"])
            / (
                TRANSIT_BENCHMARK["slow"]
                - TRANSIT_BENCHMARK["acceptable"]
            )
        ) * 40

    return 35


def calculate_risk_score(risk):
    """Convert operational risk into a normalized score."""

    if risk <= RISK_BENCHMARK["excellent"]:
        return 100

    if risk <= RISK_BENCHMARK["acceptable"]:
        return 100 - (
            (risk - RISK_BENCHMARK["excellent"])
            / (
                RISK_BENCHMARK["acceptable"]
                - RISK_BENCHMARK["excellent"]
            )
        ) * 25

    if risk <= RISK_BENCHMARK["high"]:
        return 75 - (
            (risk - RISK_BENCHMARK["acceptable"])
            / (
                RISK_BENCHMARK["high"]
                - RISK_BENCHMARK["acceptable"]
            )
        ) * 40

    return 35


def calculate_priority_alignment(priority, transport_mode):
    """Score how well a transport mode aligns with shipment priority."""

    if priority == "High":
        if transport_mode == "Air":
            return 100

        if transport_mode == "Road":
            return 90

        if transport_mode == "Rail":
            return 70

        return 40

    if priority == "Medium":
        if transport_mode == "Road":
            return 100

        if transport_mode == "Air":
            return 95

        if transport_mode == "Rail":
            return 80

        return 50

    if priority == "Low":
        if transport_mode == "Road":
            return 100

        if transport_mode == "Rail":
            return 90

        if transport_mode == "Air":
            return 80

        return 60

    return 50


# ==================================================
# OPTION SCORING
# ==================================================

def score_option(option, priority):
    """
    Score a recovery option using the configured
    cost, transit, risk and priority weights.
    """

    cost_score = calculate_cost_score(
        option["estimated_cost"]
    )

    transit_score = calculate_transit_score(
        option["estimated_transit_days"]
    )

    risk_score = calculate_risk_score(
        option["risk_score"]
    )

    priority_score = calculate_priority_alignment(
        priority,
        option["transport_mode"],
    )

    decision_score = (
        cost_score * DECISION_WEIGHTS["cost"]
        + transit_score * DECISION_WEIGHTS["transit"]
        + risk_score * DECISION_WEIGHTS["risk"]
        + priority_score * DECISION_WEIGHTS["priority_alignment"]
    )

    return {
        "option_id": option["option_id"],
        "transport_mode": option["transport_mode"],
        "carrier_id": option["carrier_id"],
        "estimated_cost": option["estimated_cost"],
        "estimated_transit_days": option["estimated_transit_days"],
        "risk_score": option["risk_score"],
        "cost_score": round(cost_score, 2),
        "transit_score": round(transit_score, 2),
        "risk_component": round(risk_score, 2),
        "priority_score": round(priority_score, 2),
        # Weighted contribution of each factor to the
        # decision score, exposed so the recommendation can
        # be explained without recomputing anything.
        "cost_contribution": round(
            cost_score * DECISION_WEIGHTS["cost"],
            2,
        ),
        "transit_contribution": round(
            transit_score * DECISION_WEIGHTS["transit"],
            2,
        ),
        "risk_contribution": round(
            risk_score * DECISION_WEIGHTS["risk"],
            2,
        ),
        "priority_contribution": round(
            priority_score
            * DECISION_WEIGHTS["priority_alignment"],
            2,
        ),
        "decision_score": round(decision_score, 2),
    }


# ==================================================
# RECOMMENDATION
# ==================================================

def get_recommendation(connection, exception_id):
    """
    Evaluate feasible recovery options for an exception
    and return the highest-scoring recommendation.
    """

    exception = exceptions_repo.get_exception_operational_context(
        connection,
        exception_id,
    )

    if exception is None:
        return None

    options = recovery_options_repo.get_feasible_options_for_exception(
        connection,
        exception_id,
    )

    if not options:
        return {
            "exception_id": exception_id,
            "shipment_id": exception["shipment_id"],
            "priority": exception["priority"],
            "severity": exception["severity"],
            "recommendation": None,
            "alternatives": [],
        }

    scored_options = [
        score_option(
            option,
            exception["priority"],
        )
        for option in options
    ]

    scored_options.sort(
        key=lambda option: option["decision_score"],
        reverse=True,
    )

    recommendation = scored_options[0]

    # --------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------

    if len(scored_options) == 1:

        confidence = "High"

        confidence_reason = (
            "This is the only feasible recovery option "
            "identified by the current rules."
        )

    else:

        score_gap = (
            recommendation["decision_score"]
            - scored_options[1]["decision_score"]
        )

        if score_gap >= 15:
            confidence = "High"

        elif score_gap >= 7:
            confidence = "Medium"

        else:
            confidence = "Low"

        confidence_reason = (
            "Based on the separation between this option's "
            f"score ({recommendation['decision_score']:.2f}) "
            "and the next-best alternative's score "
            f"({scored_options[1]['decision_score']:.2f}) "
            f"- a gap of {score_gap:.2f} points."
        )

    recommendation["confidence"] = confidence
    recommendation["reason"] = confidence_reason

    return {
        "exception_id": exception_id,
        "shipment_id": exception["shipment_id"],
        "priority": exception["priority"],
        "severity": exception["severity"],
        "recommendation": recommendation,
        "alternatives": scored_options[1:],
    }
