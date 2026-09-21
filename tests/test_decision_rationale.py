"""
Checkpoint T — decision rationale and policy transparency tests.

These tests protect the explainability layer around the existing
deterministic decision engine:

- the rationale projection exposes the engine's own factor
  scores, weighted contributions and ranking (never recomputed);
- the displayed policy weights come from the authoritative
  configuration (app.config.DECISION_WEIGHTS);
- the confidence label keeps its score-separation semantics and
  is never presented as a probability of success.

All tests run on isolated temporary databases created through the
production initializer; the real development database is never
touched.
"""

import pytest

from app.config import DECISION_WEIGHTS
from app.decision_engine import score_option
from app.generate_recovery_options import generate_recovery_options
from app.services import (
    RATIONALE_FACTORS,
    get_recommendation_rationale,
    get_recovery_assessment,
)


# ==================================================
# POLICY / CONFIGURATION
# ==================================================

def test_decision_weights_sum_to_one():
    """
    The decision score is a weighted combination of the four
    factor scores, so the configured policy weights must form a
    complete, normalized set. app.config enforces this at import
    time; this test documents the invariant explicitly.
    """

    assert set(DECISION_WEIGHTS.keys()) == {
        "cost",
        "transit",
        "risk",
        "priority_alignment",
    }

    assert abs(sum(DECISION_WEIGHTS.values()) - 1.0) < 1e-9


def test_rationale_weights_come_from_authoritative_config():
    """
    The rationale projection must expose the same weight objects
    the decision engine uses - never a duplicated copy.
    """

    review = {
        "recommendation": {
            "option_id": "OPT-TEST",
            "transport_mode": "Road",
            "cost_score": 80.0,
            "transit_score": 80.0,
            "risk_component": 80.0,
            "priority_score": 80.0,
            "cost_contribution": 80.0 * DECISION_WEIGHTS["cost"],
            "transit_contribution": (
                80.0 * DECISION_WEIGHTS["transit"]
            ),
            "risk_contribution": (
                80.0 * DECISION_WEIGHTS["risk"]
            ),
            "priority_contribution": (
                80.0 * DECISION_WEIGHTS["priority_alignment"]
            ),
            "decision_score": 80.0,
        },
        "alternatives": [],
    }

    rationale = get_recommendation_rationale(review)

    assert rationale["weights"] == {
        "cost": DECISION_WEIGHTS["cost"],
        "transit": DECISION_WEIGHTS["transit"],
        "risk": DECISION_WEIGHTS["risk"],
        "priority_alignment": (
            DECISION_WEIGHTS["priority_alignment"]
        ),
    }


# ==================================================
# RATIONALE CORRECTNESS (REAL ENGINE OUTPUT)
# ==================================================

@pytest.fixture()
def actionable_database(seeded_database):
    """
    An isolated database with recovery options generated for the
    deterministic fixtures, so the decision engine has feasible
    candidates to rank.
    """

    generate_recovery_options(seeded_database)

    return seeded_database


def test_factor_scores_match_decision_engine_results(
    actionable_database,
):
    """
    Every factor value in the rationale must be the engine's own
    scored output for the same option - nothing recomputed.
    """

    assessment = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    assert assessment is not None
    assert assessment["recommendation"] is not None

    rationale = assessment["rationale"]
    assert rationale is not None

    # The compared options are exactly the recommendation plus
    # the ranked alternatives, in engine order (each factor row
    # carries the same option sequence).
    compared_ids = [
        value["option_id"]
        for value in rationale["factor_breakdown"][0]["values"]
    ]

    assert compared_ids == [
        assessment["recommendation"]["option_id"]
    ] + [
        option["option_id"]
        for option in assessment["alternatives"]
    ]

    # Each factor value equals the engine's factor score for
    # that option.
    all_scored = [
        assessment["recommendation"],
        *assessment["alternatives"],
    ]

    for factor in rationale["factor_breakdown"]:

        for value in factor["values"]:

            engine_option = next(
                option
                for option in all_scored
                if option["option_id"] == value["option_id"]
            )

            # The value equals the engine's own outputs for the
            # factor this row represents.
            factor_score_key = dict(
                (label, score_key)
                for label, score_key, _w, _c in RATIONALE_FACTORS
            )[factor["factor"]]

            factor_contribution_key = dict(
                (label, contribution_key)
                for label, _s, _w, contribution_key in (
                    RATIONALE_FACTORS
                )
            )[factor["factor"]]

            assert value["score"] == (
                engine_option[factor_score_key]
            )

            assert value["contribution"] == (
                engine_option[factor_contribution_key]
            )

    # One breakdown row per configured factor, in the fixed
    # planner-readable order.
    assert [factor["factor"] for factor in rationale["factor_breakdown"]] == [
        "Cost fit",
        "Transit fit",
        "Risk fit",
        "Priority fit",
    ]


def test_weighted_contributions_sum_to_decision_score(
    actionable_database,
):
    """
    For each scored option, the four weighted contributions must
    sum to the engine's decision score (within rounding).
    """

    assessment = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    rationale = assessment["rationale"]

    contribution_keys = [
        contribution_key
        for _l, _s, _w, contribution_key in RATIONALE_FACTORS
    ]

    all_scored = [
        assessment["recommendation"],
        *assessment["alternatives"],
    ]

    for option in all_scored:

        total = sum(
            option[key] for key in contribution_keys
        )

        assert abs(total - option["decision_score"]) < 0.01


def test_recommended_option_is_highest_scoring(
    actionable_database,
):
    """
    The option presented as recommended must be the highest-
    scoring option according to the existing deterministic
    engine, and the alternatives must follow its ranking.
    """

    assessment = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    recommendation = assessment["recommendation"]
    alternatives = assessment["alternatives"]

    assert recommendation["decision_score"] >= max(
        option["decision_score"] for option in alternatives
    )

    alternative_scores = [
        option["decision_score"] for option in alternatives
    ]

    assert alternative_scores == sorted(
        alternative_scores,
        reverse=True,
    )


def test_alternative_factor_scores_remain_comparable(
    actionable_database,
):
    """
    The rationale must carry every alternative's factor values so
    the planner can compare options - not only the winner.
    """

    assessment = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    assert len(assessment["alternatives"]) >= 1

    rationale = assessment["rationale"]

    compared_counts = {
        len(factor["values"])
        for factor in rationale["factor_breakdown"]
    }

    # Recommendation + every alternative, in every factor row.
    assert compared_counts == {
        1 + len(assessment["alternatives"])
    }


def test_trade_offs_identify_where_alternatives_win(
    actionable_database,
):
    """
    Where an alternative beats the recommendation on an
    individual factor, the rationale must state that factually;
    where it does not, no trade-off is fabricated.
    """

    assessment = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    recommendation = assessment["recommendation"]
    alternatives = assessment["alternatives"]
    rationale = assessment["rationale"]

    factor_keys = {
        label: score_key
        for label, score_key, _w, _c in RATIONALE_FACTORS
    }

    expected_trade_offs = set()

    for option in alternatives:

        stronger = [
            label
            for label, score_key in factor_keys.items()
            if option[score_key] > recommendation[score_key]
        ]

        if stronger:
            expected_trade_offs.add(
                (option["option_id"], tuple(stronger))
            )

    actual_trade_offs = {
        (entry["option_id"], tuple(entry["stronger_factors"]))
        for entry in rationale["trade_offs"]
    }

    assert actual_trade_offs == expected_trade_offs


# ==================================================
# CONFIDENCE SEMANTICS
# ==================================================

def test_confidence_basis_states_score_separation(
    actionable_database,
):
    """
    With multiple feasible options, the confidence basis must
    describe the separation between the recommendation and the
    next-best alternative, and must not present the label as a
    probability of success.
    """

    assessment = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    recommendation = assessment["recommendation"]
    alternatives = assessment["alternatives"]
    rationale = assessment["rationale"]

    assert len(alternatives) >= 1

    next_best_score = max(
        option["decision_score"] for option in alternatives
    )

    score_gap = (
        recommendation["decision_score"] - next_best_score
    )

    assert f"{score_gap:.2f} points" in (
        rationale["confidence_basis"]
    )

    assert "not a probability of success" in (
        rationale["confidence_basis"]
    )

    # The label itself keeps the engine's separation meaning:
    # gap >= 15 High, >= 7 Medium, otherwise Low.
    if score_gap >= 15:
        assert recommendation["confidence"] == "High"
    elif score_gap >= 7:
        assert recommendation["confidence"] == "Medium"
    else:
        assert recommendation["confidence"] == "Low"


def test_sole_option_confidence_is_not_a_probability(
    actionable_database,
):
    """
    A single feasible option is reported High because it is the
    only candidate - the rationale must say exactly that, not
    imply statistical certainty.
    """

    from app.workflow_engine import generate_workflow_actions

    # EXC-900002 is High severity with three feasible options;
    # remove two of them to leave exactly one feasible option.
    cursor = actionable_database.cursor()

    cursor.execute(
        """
        DELETE FROM recovery_options
        WHERE exception_id = 'EXC-900002'
          AND option_id NOT IN (
              SELECT option_id
              FROM recovery_options
              WHERE exception_id = 'EXC-900002'
              ORDER BY option_id
              LIMIT 1
          )
        """
    )

    actionable_database.commit()

    generate_workflow_actions(actionable_database)

    assessment = get_recovery_assessment(
        actionable_database,
        "EXC-900002",
    )

    assert assessment["recommendation"] is not None
    assert assessment["alternatives"] == []
    assert assessment["recommendation"]["confidence"] == "High"

    rationale = assessment["rationale"]

    assert "single feasible" in rationale["confidence_basis"]
    assert "not a probability of success" in (
        rationale["confidence_basis"]
    )


# ==================================================
# NO-RECOMMENDATION PATH
# ==================================================

def test_no_recommendation_produces_no_rationale(
    seeded_database,
):
    """
    Without a feasible recommendation there is nothing to
    explain: the assessment must expose rationale=None rather
    than an empty or fabricated structure.
    """

    assessment = get_recovery_assessment(
        seeded_database,
        "EXC-900001",
    )

    assert assessment["recommendation"] is None
    assert assessment["rationale"] is None


# ==================================================
# ENGINE OUTPUT CONTRACT
# ==================================================

def test_score_option_exposes_weighted_contributions(
    actionable_database,
):
    """
    The engine's score_option output must contain the weighted
    contribution keys the rationale projection consumes, derived
    from the configured weights.
    """

    cursor = actionable_database.cursor()

    row = cursor.execute(
        """
        SELECT * FROM recovery_options
        WHERE exception_id = 'EXC-900002'
        LIMIT 1
        """
    ).fetchone()

    assert row is not None

    scored = score_option(
        dict(row),
        "High",
    )

    for contribution_key in (
        "cost_contribution",
        "transit_contribution",
        "risk_contribution",
        "priority_contribution",
    ):
        assert contribution_key in scored

    expected_total = (
        scored["cost_score"] * DECISION_WEIGHTS["cost"]
        + scored["transit_score"] * DECISION_WEIGHTS["transit"]
        + scored["risk_component"] * DECISION_WEIGHTS["risk"]
        + scored["priority_score"]
        * DECISION_WEIGHTS["priority_alignment"]
    )

    assert abs(
        scored["decision_score"] - expected_total
    ) < 0.01
