import logging

from app.config import (
    DECISION_WEIGHTS,
    COST_BENCHMARK,
    TRANSIT_BENCHMARK,
    RISK_BENCHMARK,
)
from app.database import get_connection
from app.repositories import exceptions_repo
from app.repositories import recovery_options_repo

logger = logging.getLogger(__name__)


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
            "The recommendation balances recovery cost, "
            "transit time and operational risk."
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


# ==================================================
# DISPLAY RECOMMENDATION
# ==================================================

def display_recommendation(result):
    """Display a recommendation in the terminal."""

    recommendation = result["recommendation"]

    if recommendation is None:

        logger.info(
            f"\nException: {result['exception_id']}"
        )

        logger.info(
            "No feasible recovery recommendation."
        )

        return

    logger.info(
        f"\nException: {result['exception_id']}"
    )

    logger.info(
        f"Shipment: {result['shipment_id']}"
    )

    logger.info(
        f"Priority: {result['priority']}"
    )

    logger.info(
        f"Severity: {result['severity']}"
    )

    logger.info(
        f"Recommended mode: "
        f"{recommendation['transport_mode']}"
    )

    logger.info(
        f"Decision score: "
        f"{recommendation['decision_score']}/100"
    )

    logger.info(
        f"Confidence: "
        f"{recommendation['confidence']}"
    )

    logger.info(
        f"Cost: "
        f"€{recommendation['estimated_cost']:,.2f}"
    )

    logger.info(
        f"Transit: "
        f"{recommendation['estimated_transit_days']} days"
    )

    logger.info(
        f"Risk: "
        f"{recommendation['risk_score']}"
    )

    reason = (
        f"Recommend "
        f"{recommendation['transport_mode']} recovery "
        f"with an estimated cost of "
        f"€{recommendation['estimated_cost']:,.2f}, "
        f"transit time of "
        f"{recommendation['estimated_transit_days']} days "
        f"and operational risk score of "
        f"{recommendation['risk_score']}. "
        f"Decision score: "
        f"{recommendation['decision_score']}/100. "
        f"Confidence: "
        f"{recommendation['confidence']}. "
        f"{recommendation['reason']}"
    )

    logger.info(f"Reason: {reason}")

    alternatives = result["alternatives"]

    if not alternatives:
        logger.info("Alternatives: None feasible")
        return

    logger.info("Alternatives:")

    for option in alternatives:

        logger.info(
            f"  - {option['transport_mode']} | "
            f"Score: {option['decision_score']}/100 | "
            f"Cost: €{option['estimated_cost']:,.2f} | "
            f"Transit: "
            f"{option['estimated_transit_days']} days | "
            f"Risk: {option['risk_score']}"
        )


# ==================================================
# MAIN ANALYSIS
# ==================================================

def run_decision_engine(connection):
    """Evaluate all currently open exceptions."""

    cursor = connection.cursor()

    exceptions = cursor.execute(
        """
        SELECT exception_id
        FROM exceptions
        WHERE resolution_status = 'Open'
        ORDER BY exception_id
        """
    ).fetchall()

    recommendations = 0
    without_recommendation = 0

    for index, exception in enumerate(exceptions):

        result = get_recommendation(
            connection,
            exception["exception_id"],
        )

        if result["recommendation"] is None:
            without_recommendation += 1

        else:
            recommendations += 1

        # Display only the first ten cases during
        # terminal-based testing.
        if index < 10:
            display_recommendation(result)

    logger.info("\n" + "=" * 55)
    logger.info("Decision Engine Summary")
    logger.info("=" * 55)

    logger.info(
        f"Exceptions evaluated: "
        f"{len(exceptions)}"
    )

    logger.info(
        f"Recommendations available: "
        f"{recommendations}"
    )

    logger.info(
        f"Exceptions without feasible recommendation: "
        f"{without_recommendation}"
    )


# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    connection = get_connection()

    try:
        run_decision_engine(connection)

    finally:
        connection.close()