"""
Checkpoint V — sustainability-aware decision-support tests.

The sustainability layer is informational decision support:
estimated transport CO₂e for the deterministic recommendation
and its feasible alternatives, computed from persisted shipment
data and configured prototype factors.

These tests protect:

- the transparent calculation and its unit conversion;
- safe failure for unsupported modes and invalid weights
  (never a silent zero-emissions estimate);
- the factual trade-off comparison across feasible options;
- the Checkpoint V scope boundary: sustainability never
  changes the recommendation, scores, confidence or workflow
  state.

All tests use isolated temporary databases; the development
database is never touched.
"""

import pytest

from app.config import (
    EMISSIONS_UNIT,
    TRANSPORT_EMISSIONS_FACTORS,
)
from app.generate_recovery_options import generate_recovery_options
from app.sustainability import (
    SustainabilityInputError,
    build_sustainability_comparison,
    calculate_transport_emissions,
    kilograms_to_tonnes,
)
from app.services import (
    build_decision_brief_evidence,
    get_decision_brief,
    get_recovery_assessment,
    get_sustainability_comparison,
)
from app.workflow_engine import (
    PENDING_APPROVAL,
    generate_workflow_actions,
)


@pytest.fixture()
def actionable_database(seeded_database):
    """Isolated DB with deterministic recovery options generated."""

    generate_recovery_options(seeded_database)

    return seeded_database


# ==================================================
# CALCULATION
# ==================================================

def test_calculation_matches_transparent_formula():
    """
    tonnes × kilometres × factor = estimated kg CO₂e.

    100 kg = 0.1 t; 0.1 × 1000 km × 0.60 (Air) = 60 kg CO₂e.
    """

    result = calculate_transport_emissions(
        100,
        1000,
        "Air",
    )

    assert result["estimated_co2e_kg"] == 60.0
    assert result["unit"] == EMISSIONS_UNIT == "kg CO₂e"
    assert result["emissions_factor"] == 0.60
    assert result["shipment_weight_tonnes"] == 0.1


def test_unit_conversion_kg_to_tonnes():

    assert kilograms_to_tonnes(1000) == 1.0
    assert kilograms_to_tonnes(480.77) == pytest.approx(
        0.48077
    )


def test_every_supported_mode_has_a_configured_factor():
    """
    Exactly the transport modes Adensa supports (the option
    generator's TRANSPORT_PROFILES set) carry an explicit
    configured factor.
    """

    assert set(TRANSPORT_EMISSIONS_FACTORS.keys()) == {
        "Air",
        "Road",
        "Rail",
        "Sea",
    }

    assert all(
        isinstance(factor, (int, float)) and factor > 0
        for factor in TRANSPORT_EMISSIONS_FACTORS.values()
    )


def test_unsupported_mode_fails_safely():
    """
    An unsupported mode must raise, never silently estimate
    zero emissions.
    """

    with pytest.raises(SustainabilityInputError):
        calculate_transport_emissions(
            100,
            1000,
            "Hyperloop",
        )


@pytest.mark.parametrize(
    "weight",
    [None, 0, -5, "heavy"],
)
def test_invalid_weight_fails_safely(weight):

    with pytest.raises(SustainabilityInputError):
        calculate_transport_emissions(
            weight,
            1000,
            "Road",
        )


@pytest.mark.parametrize(
    "distance",
    [None, 0, -120],
)
def test_invalid_distance_fails_safely(distance):

    with pytest.raises(SustainabilityInputError):
        calculate_transport_emissions(
            100,
            distance,
            "Road",
        )


def test_result_is_deterministic():

    first = calculate_transport_emissions(
        123.45,
        9876.0,
        "Rail",
    )

    second = calculate_transport_emissions(
        123.45,
        9876.0,
        "Rail",
    )

    assert first == second


# ==================================================
# COMPARISON / TRADE-OFFS
# ==================================================

def test_comparison_estimates_all_feasible_options():
    """
    Each feasible option receives its estimate in the given
    order (recommendation first), with the lowest-emission
    option identified factually.
    """

    comparison = build_sustainability_comparison(
        200,
        1000,
        [
            {"option_id": "OPT-A", "transport_mode": "Air"},
            {"option_id": "OPT-B", "transport_mode": "Road"},
            {"option_id": "OPT-C", "transport_mode": "Sea"},
        ],
    )

    assert comparison["status"] == "available"

    modes = [
        estimate["transport_mode"]
        for estimate in comparison["estimates"]
    ]

    assert modes == ["Air", "Road", "Sea"]

    # 0.2 t × 1000 km: Air 120.0, Road 20.0, Sea 3.0.
    values = [
        estimate["estimated_co2e_kg"]
        for estimate in comparison["estimates"]
    ]

    assert values == [120.0, 20.0, 3.0]

    assert comparison["lowest_emission_option"] == {
        "option_id": "OPT-C",
        "transport_mode": "Sea",
        "estimated_co2e_kg": 3.0,
    }


def test_trade_offs_are_factual_not_moralizing():
    """
    Comparisons use Higher/Lower/Similar plus the numeric
    difference — no 'green'/'dirty' language anywhere in the
    projection.
    """

    comparison = build_sustainability_comparison(
        200,
        1000,
        [
            {"option_id": "OPT-A", "transport_mode": "Air"},
            {"option_id": "OPT-B", "transport_mode": "Road"},
        ],
    )

    trade_off = comparison["trade_offs"][0]

    assert trade_off["relative_to_recommendation"] == "Lower"
    assert trade_off["difference_kg"] == -100.0

    assert "green" not in str(comparison).lower()
    assert "dirty" not in str(comparison).lower()

    # The reverse configuration: the recommendation is the
    # lower-emitting option.
    reverse = build_sustainability_comparison(
        200,
        1000,
        [
            {"option_id": "OPT-B", "transport_mode": "Road"},
            {"option_id": "OPT-A", "transport_mode": "Air"},
        ],
    )

    assert (
        reverse["trade_offs"][0][
            "relative_to_recommendation"
        ]
        == "Higher"
    )
    assert reverse["trade_offs"][0]["difference_kg"] == 100.0


def test_unavailable_estimate_is_reported_not_fabricated():
    """
    An option whose estimate cannot be produced yields an
    honest unavailable record — never a zero-emissions value.
    """

    comparison = build_sustainability_comparison(
        200,
        1000,
        [
            {"option_id": "OPT-A", "transport_mode": "Air"},
            {"option_id": "OPT-B", "transport_mode": "Blimp"},
        ],
    )

    unavailable = comparison["estimates"][1]

    assert unavailable["status"] == "unavailable"
    assert "Blimp" in unavailable["reason"]
    assert "estimated_co2e_kg" not in unavailable

    # The recommendation still carries its estimate, and no
    # trade-off is fabricated for the missing option.
    assert comparison["estimates"][0]["status"] == "available"
    assert comparison["trade_offs"] == []


def test_comparison_unavailable_when_recommendation_missing():
    """
    Invalid physical inputs make the whole comparison honestly
    unavailable rather than producing estimates.
    """

    comparison = build_sustainability_comparison(
        None,
        1000,
        [{"option_id": "OPT-A", "transport_mode": "Air"}],
    )

    assert comparison["status"] == "unavailable"
    assert comparison["estimates"][0]["status"] == (
        "unavailable"
    )


# ==================================================
# SERVICE INTEGRATION
# ==================================================

def test_service_comparison_for_exception(
    actionable_database,
):
    """
    The service projects the real fixture data: the recommendation
    and its two alternatives all receive estimates from the
    persisted shipment weight/distance.
    """

    comparison = get_sustainability_comparison(
        actionable_database,
        "EXC-900002",
    )

    assert comparison["status"] == "available"

    assert len(comparison["estimates"]) == 3

    assert all(
        estimate["status"] == "available"
        for estimate in comparison["estimates"]
    )

    # Every estimate uses the persisted shipment distance.
    assert all(
        estimate["distance_km"] > 0
        for estimate in comparison["estimates"]
    )


def test_service_returns_none_without_recommendation(
    seeded_database,
):
    """
    No deterministic recommendation → no comparison at all
    (nothing to assess), not an empty structure.
    """

    assert (
        get_sustainability_comparison(
            seeded_database,
            "EXC-900001",
        )
        is None
    )


# ==================================================
# DECISION PRESERVATION (CHECKPOINT V BOUNDARY)
# ==================================================

def test_sustainability_does_not_change_the_decision(
    actionable_database,
):
    """
    Producing sustainability estimates must leave the
    deterministic recommendation, its score, its confidence and
    the workflow state completely untouched.
    """

    generate_workflow_actions(actionable_database)

    before = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    before_status = (
        actionable_database.cursor()
        .execute(
            """
            SELECT status FROM recovery_actions
            WHERE exception_id = 'EXC-900002'
            """
        )
        .fetchone()["status"]
    )

    get_sustainability_comparison(
        actionable_database,
        "EXC-900002",
    )

    after = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    assert (
        after["recommendation"]["option_id"]
        == before["recommendation"]["option_id"]
    )
    assert (
        after["recommendation"]["decision_score"]
        == before["recommendation"]["decision_score"]
    )
    assert (
        after["recommendation"]["confidence"]
        == before["recommendation"]["confidence"]
    )
    assert after["alternatives"] == before["alternatives"]

    after_status = (
        actionable_database.cursor()
        .execute(
            """
            SELECT status FROM recovery_actions
            WHERE exception_id = 'EXC-900002'
            """
        )
        .fetchone()["status"]
    )

    assert after_status == before_status == PENDING_APPROVAL


def test_weights_are_untouched_by_sustainability():
    """
    The decision policy is exactly the Checkpoint T weights —
    sustainability is not a fifth factor.
    """

    from app.config import DECISION_WEIGHTS

    assert DECISION_WEIGHTS == {
        "cost": 0.25,
        "transit": 0.30,
        "risk": 0.25,
        "priority_alignment": 0.20,
    }


# ==================================================
# AI EVIDENCE (ADDITIVE, TESTED)
# ==================================================

def test_sustainability_is_available_as_ai_evidence(
    actionable_database,
):
    """
    The AI evidence builder now carries the sustainability
    projection (additive Checkpoint U extension), and the
    built-in advisory brief still validates against the
    contract.
    """

    evidence = build_decision_brief_evidence(
        actionable_database,
        "EXC-900002",
    )

    sustainability = evidence["sustainability"]

    assert sustainability["status"] == "available"
    assert len(sustainability["estimates"]) == 3

    # The advisory layer still works end to end with the
    # additive evidence.
    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
    )

    assert brief["status"] == "available"


def test_sustainability_schema_never_persisted(
    actionable_database,
):
    """
    Sustainability estimates are deterministic app-layer
    calculations: producing them writes nothing to any table
    (row counts unchanged).
    """

    cursor = actionable_database.cursor()

    def _total_rows():
        return cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM shipments)
              + (SELECT COUNT(*) FROM exceptions)
              + (SELECT COUNT(*) FROM recovery_options)
              + (SELECT COUNT(*) FROM recovery_actions)
            """
        ).fetchone()[0]

    before = _total_rows()

    get_sustainability_comparison(
        actionable_database,
        "EXC-900002",
    )

    assert _total_rows() == before
