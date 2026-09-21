"""
Sustainability impact layer (prototype).

Position in the architecture:

    Streamlit / API / CLI
         ↓
      services
         ↓
   sustainability (this module)   ← pure deterministic
         ↓                          estimation, no state
   repositories → SQLite           ← persisted physical data

What it estimates, and what it does not:

It computes **estimated transport CO₂e** for a recovery option
using the transparent formula

    estimated CO₂e (kg) = shipment tonnes
                        × route kilometres
                        × mode emissions factor

The inputs are persisted operational facts (shipment weight,
persisted route distance, transport mode) and configured
prototype assumptions (emissions factors in app.config). This
is decision-support estimation, NOT measured carbon accounting:
every result carries that qualification, and no result is ever
persisted — the calculation is deterministic, so recomputing it
is always equivalent to storing it.

The layer is purely informational: it never changes the
deterministic recommendation, factor scores, policy weights,
confidence, ordering or any workflow state (Checkpoint V scope
boundary; see ADR-010).
"""

from app.config import (
    EMISSIONS_METHODOLOGY_NOTE,
    EMISSIONS_UNIT,
    TRANSPORT_EMISSIONS_FACTORS,
)


# ==================================================
# ERRORS
# ==================================================

class SustainabilityInputError(ValueError):
    """
    The sustainability estimate cannot be produced from the
    supplied inputs (missing/invalid weight, invalid distance,
    unsupported transport mode). Raised instead of silently
    producing a misleading value such as zero emissions.
    """


# ==================================================
# UNIT CONVERSION
# ==================================================

KILOGRAMS_PER_TONNE = 1000.0


def kilograms_to_tonnes(weight_kg):
    """
    Convert a shipment weight in kilograms to tonnes.

    Shipments are recorded in kg (schema: shipments.weight_kg);
    tonne-kilometre emissions factors require tonnes, so the
    conversion is kg / 1000. Zero, negative or non-numeric
    weights are rejected rather than estimated.
    """

    if not isinstance(weight_kg, (int, float)):
        raise SustainabilityInputError(
            "shipment weight is missing or non-numeric"
        )

    if weight_kg <= 0:
        raise SustainabilityInputError(
            "shipment weight must be positive to estimate "
            "emissions"
        )

    return weight_kg / KILOGRAMS_PER_TONNE


# ==================================================
# CORE CALCULATION
# ==================================================

def calculate_transport_emissions(
    weight_kg,
    distance_km,
    transport_mode,
):
    """
    Estimate transport CO₂e for one movement.

    Pure and deterministic: same inputs always produce the
    same estimate. Raises SustainabilityInputError for a
    missing/invalid weight, a non-positive distance, or a
    transport mode without a configured factor — an
    unsupported mode must fail safely, never silently
    estimate zero emissions.
    """

    tonnes = kilograms_to_tonnes(weight_kg)

    if not isinstance(distance_km, (int, float)):
        raise SustainabilityInputError(
            "route distance is missing or non-numeric"
        )

    if distance_km <= 0:
        raise SustainabilityInputError(
            "route distance must be positive to estimate "
            "emissions"
        )

    factor = TRANSPORT_EMISSIONS_FACTORS.get(transport_mode)

    if factor is None:
        raise SustainabilityInputError(
            f"no configured emissions factor for transport "
            f"mode: {transport_mode}"
        )

    estimated_co2e_kg = round(
        tonnes * distance_km * factor,
        2,
    )

    return {
        "transport_mode": transport_mode,
        "shipment_weight_kg": round(weight_kg, 2),
        "shipment_weight_tonnes": round(tonnes, 4),
        "distance_km": round(distance_km, 2),
        "emissions_factor": factor,
        "estimated_co2e_kg": estimated_co2e_kg,
        "unit": EMISSIONS_UNIT,
        "methodology": EMISSIONS_METHODOLOGY_NOTE,
        "data_quality_note": (
            "Prototype sustainability estimate based on "
            "persisted shipment data and configured factors; "
            "distance is the persisted route distance, not "
            "live routing data."
        ),
    }


# ==================================================
# COMPARISON / TRADE-OFFS
# ==================================================

def build_sustainability_comparison(
    shipment_weight_kg,
    route_distance_km,
    options,
):
    """
    Estimate emissions for a recommendation and its feasible
    alternatives and expose the factual sustainability
    trade-offs.

    options: the scored decision-engine options (the
    recommendation first, then the ranked alternatives), each
    carrying transport_mode and option_id.

    Returns a structured projection:

    - estimates: one per option, in the given order; each
      estimate is either a full impact result or an honest
      unavailable record stating why;
    - trade_offs: per-alternative, purely factual comparisons
      against the recommendation (estimated emissions
      difference in kg CO₂e; Higher/Lower/Similar);
    - lowest_emission_option: the option with the smallest
      available estimate, or None.

    No value here influences the deterministic recommendation.
    """

    estimates = []
    available = []

    for option in options:

        try:

            estimate = calculate_transport_emissions(
                shipment_weight_kg,
                route_distance_km,
                option["transport_mode"],
            )

        except SustainabilityInputError as error:

            estimate = {
                "transport_mode": option["transport_mode"],
                "option_id": option.get("option_id"),
                "status": "unavailable",
                "reason": str(error),
            }

        else:

            estimate["status"] = "available"
            estimate["option_id"] = option.get("option_id")
            available.append(estimate)

        estimates.append(estimate)

    trade_offs = []

    recommendation = (
        estimates[0]
        if estimates and estimates[0]["status"] == "available"
        else None
    )

    if recommendation is not None:

        for alternative in estimates[1:]:

            if alternative["status"] != "available":
                continue

            difference = round(
                alternative["estimated_co2e_kg"]
                - recommendation["estimated_co2e_kg"],
                2,
            )

            if abs(difference) < 0.01:

                relation = "Similar"

            elif difference > 0:

                relation = "Higher"

            else:

                relation = "Lower"

            # Relation is expressed from the ALTERNATIVE's
            # perspective: a positive difference means the
            # alternative is estimated to emit more than the
            # recommendation.

            trade_offs.append(
                {
                    "option_id": alternative["option_id"],
                    "transport_mode": (
                        alternative["transport_mode"]
                    ),
                    "estimated_co2e_kg": (
                        alternative["estimated_co2e_kg"]
                    ),
                    "difference_kg": difference,
                    "relative_to_recommendation": relation,
                }
            )

    lowest = None

    if available:

        lowest = min(
            available,
            key=lambda estimate: estimate[
                "estimated_co2e_kg"
            ],
        )

    return {
        "status": (
            "available"
            if recommendation is not None
            else "unavailable"
        ),
        "unit": EMISSIONS_UNIT,
        "methodology": EMISSIONS_METHODOLOGY_NOTE,
        "data_quality_note": (
            "Prototype sustainability estimate based on "
            "persisted shipment data and configured factors; "
            "distance is the persisted route distance, not "
            "live routing data."
        ),
        "estimates": estimates,
        "trade_offs": trade_offs,
        "lowest_emission_option": (
            {
                "option_id": lowest["option_id"],
                "transport_mode": lowest["transport_mode"],
                "estimated_co2e_kg": (
                    lowest["estimated_co2e_kg"]
                ),
            }
            if lowest is not None
            else None
        ),
    }
