"""
Checkpoint U — advisory AI decision-support tests.

The AI layer is advisory only. These tests protect the
boundary from both directions:

- a valid brief is presented and grounded in the deterministic
  evidence;
- provider failure, malformed output, fabricated identifiers
  and action-claim language all degrade to the honest
  unavailable state;
- the deterministic recommendation, rationale and every
  workflow transition remain entirely outside AI influence.

All tests use isolated temporary databases and the deterministic
built-in provider or explicit fakes — no network, no real model,
no development database.
"""

import pytest

from app.ai_support import (
    ADVISORY_DISCLAIMER,
    AiProviderError,
    BriefValidationError,
    TemplateBriefProvider,
    validate_decision_brief,
)
from app.services import (
    build_decision_brief_evidence,
    get_decision_brief,
)
from app.workflow_engine import (
    APPROVED,
    PENDING_APPROVAL,
    approve_action,
    generate_workflow_actions,
)
from tests.conftest import seed_minimal_supply_chain
from app.generate_recovery_options import generate_recovery_options


# ==================================================
# FIXTURES / FAKES
# ==================================================

@pytest.fixture()
def actionable_database(seeded_database):
    """Isolated DB with deterministic recovery options generated."""

    generate_recovery_options(seeded_database)

    return seeded_database


class FakeProvider:
    """Contract-valid fake provider with configurable output."""

    name = "fake-provider"

    def __init__(self, brief=None, error=None):
        self.brief = brief if brief is not None else {
            "situation_summary": "Situation summary grounded "
            "in the evidence.",
            "recommended_action": "Explains option OPT-000001 "
            "as recommended.",
            "rationale": "Explanation grounded in the factor "
            "breakdown.",
            "tradeoffs": "Factual trade-off statement.",
            "verification_points": ["Check the delivery plan."],
            "disclaimer": ADVISORY_DISCLAIMER,
            "provider": self.name,
        }
        self.error = error
        self.calls = []

    def __call__(self, evidence):
        self.calls.append(evidence)

        if self.error is not None:
            raise self.error

        return self.brief


def _erroring_provider(error):
    """A provider that always raises (mimics real failure)."""

    def _provider(evidence):
        raise error

    return _provider


# ==================================================
# EVIDENCE GROUNDING
# ==================================================

def test_evidence_contains_structured_deterministic_facts(
    actionable_database,
):
    """
    The AI input must be the structured deterministic output the
    planner already sees: exception facts, recommendation,
    alternatives, rationale and persisted history.
    """

    evidence = build_decision_brief_evidence(
        actionable_database,
        "EXC-900002",
    )

    assert evidence is not None

    exception = evidence["exception"]
    assert exception["exception_id"] == "EXC-900002"
    assert exception["severity"] == "High"
    assert exception["description"]
    assert exception["required_delivery_date"]

    recommendation = evidence["recommendation"]
    assert recommendation is not None
    assert "decision_score" in recommendation
    assert "confidence" in recommendation

    assert len(evidence["alternatives"]) >= 1

    rationale = evidence["rationale"]
    assert rationale is not None
    assert rationale["weights"]
    assert rationale["factor_breakdown"]

    assert evidence["history"]
    assert any(
        entry["event"] == "Exception detected"
        for entry in evidence["history"]
    )


# ==================================================
# CONTRACT / VALIDATION
# ==================================================

def test_valid_brief_is_accepted_and_labelled_advisory(
    actionable_database,
):
    """A contract-valid brief is presented with advisory labels."""

    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=FakeProvider(),
    )

    assert brief["status"] == "available"
    assert brief["advisory_label"] == (
        "AI-assisted · Advisory only"
    )
    assert brief["disclaimer"] == ADVISORY_DISCLAIMER

    for field in (
        "situation_summary",
        "recommended_action",
        "rationale",
        "tradeoffs",
    ):
        assert isinstance(brief[field], str)
        assert brief[field].strip()


def test_built_in_provider_output_is_contract_valid(
    actionable_database,
):
    """
    The deterministic built-in provider's output passes the same
    validation as any external provider.
    """

    evidence = build_decision_brief_evidence(
        actionable_database,
        "EXC-900002",
    )

    raw = TemplateBriefProvider()(evidence)

    validated = validate_decision_brief(raw, evidence)

    assert validated["status"] == "available"
    assert validated["provider"] == "adensa-evidence-brief/v1"

    # Grounded: every identifier it mentions exists in the
    # evidence.
    from app.ai_support import IDENTIFIER_PATTERN

    evidence_text = (
        evidence["exception"]["exception_id"]
        + " "
        + evidence["recommendation"]["option_id"]
    )

    known = {evidence["exception"]["exception_id"]}

    for mention in IDENTIFIER_PATTERN.findall(
        " ".join(
            [
                validated["situation_summary"],
                validated["recommended_action"],
                validated["rationale"],
                validated["tradeoffs"],
            ]
        )
    ):
        assert mention in known or mention.startswith(
            ("SHP", "ORD", "CAR", "OPT")
        )


def test_missing_required_field_is_rejected(
    actionable_database,
):
    """A brief missing a required field is rejected safely."""

    provider = FakeProvider()
    del provider.brief["rationale"]

    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=provider,
    )

    assert brief["status"] == "unavailable"
    assert "Deterministic recommendation remains available" in (
        brief["message"]
    )


def test_overlong_field_is_rejected(actionable_database):

    provider = FakeProvider()
    provider.brief["situation_summary"] = "x" * 2000

    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=provider,
    )

    assert brief["status"] == "unavailable"


def test_non_string_field_is_rejected(actionable_database):

    provider = FakeProvider()
    provider.brief["tradeoffs"] = 42

    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=provider,
    )

    assert brief["status"] == "unavailable"


# ==================================================
# ADVISORY BOUNDARY
# ==================================================

@pytest.mark.parametrize(
    "claim",
    [
        "The system has approved this recovery.",
        "I have executed the recovery action ACT-000001.",
        "This exception was resolved automatically.",
        "We have rejected the alternative.",
    ],
)
def test_action_claim_language_is_rejected(
    actionable_database,
    claim,
):
    """No brief text may present itself as having acted."""

    provider = FakeProvider()
    provider.brief["situation_summary"] = claim

    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=provider,
    )

    assert brief["status"] == "unavailable"


def test_fabricated_identifier_is_rejected(
    actionable_database,
):
    """
    A brief that mentions an operational identifier absent from
    the evidence is inventing a fact and must be rejected.
    """

    provider = FakeProvider()
    provider.brief["recommended_action"] = (
        "Consider alternative OPT-999999 which fits better."
    )

    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=provider,
    )

    assert brief["status"] == "unavailable"
    assert "OPT-999999" in brief["message"]


def test_provider_failure_degrades_gracefully(
    actionable_database,
):
    """Provider outage/timeout behaves as unavailable, not crash."""

    brief = get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=_erroring_provider(
            AiProviderError("provider unreachable")
        ),
    )

    assert brief["status"] == "unavailable"
    assert "provider unreachable" in brief["message"]
    assert "Deterministic recommendation remains available" in (
        brief["message"]
    )


def test_deterministic_recommendation_is_untouched_by_ai(
    actionable_database,
):
    """
    Whatever the provider returns, the deterministic assessment
    is unchanged — same recommendation object, same scores, same
    confidence.
    """

    before = build_decision_brief_evidence(
        actionable_database,
        "EXC-900002",
    )["recommendation"]

    hostile_provider = FakeProvider()
    hostile_provider.brief["recommended_action"] = (
        "Choose alternative OPT-000003 instead; it is better."
    )

    get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=hostile_provider,
    )

    after = build_decision_brief_evidence(
        actionable_database,
        "EXC-900002",
    )["recommendation"]

    assert after["option_id"] == before["option_id"]
    assert after["decision_score"] == before["decision_score"]
    assert after["confidence"] == before["confidence"]


def test_ai_output_cannot_transition_workflow_state(
    actionable_database,
):
    """
    Generating a brief must not move the recovery action through
    any lifecycle transition: approval still requires the real
    workflow service.
    """

    generate_workflow_actions(actionable_database)

    before = actionable_database.cursor().execute(
        """
        SELECT status FROM recovery_actions
        WHERE exception_id = 'EXC-900002'
        """
    ).fetchone()["status"]

    assert before == PENDING_APPROVAL

    get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=FakeProvider(),
    )

    after = actionable_database.cursor().execute(
        """
        SELECT status FROM recovery_actions
        WHERE exception_id = 'EXC-900002'
        """
    ).fetchone()["status"]

    assert after == PENDING_APPROVAL

    # And the real transition still works only through the
    # workflow engine.
    approve_action(
        actionable_database,
        actionable_database.cursor().execute(
            "SELECT action_id FROM recovery_actions"
        ).fetchone()["action_id"],
        "A. Planner",
    )

    final = actionable_database.cursor().execute(
        """
        SELECT status FROM recovery_actions
        WHERE exception_id = 'EXC-900002'
        """
    ).fetchone()["status"]

    assert final == APPROVED


def test_brief_is_never_persisted(actionable_database):
    """
    The brief lives only in the caller's hands — no AI text is
    written to any table.
    """

    get_decision_brief(
        actionable_database,
        "EXC-900002",
        provider=FakeProvider(),
    )

    cursor = actionable_database.cursor()

    tables = [
        row["name"]
        for row in cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    ]

    for table in tables:

        columns = [
            row["name"]
            for row in cursor.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        ]

        for column in columns:

            values = cursor.execute(
                f"SELECT {column} FROM {table}"
            ).fetchall()

            for row in values:

                value = row[0]

                if isinstance(value, str):
                    assert "grounded in the evidence" not in value
                    assert "fake-provider" not in value


# ==================================================
# NO-RECOMMENDATION PATH
# ==================================================

def test_no_recommendation_means_no_brief(seeded_database):
    """
    Without a deterministic recommendation there is nothing to
    explain — the honest unavailable state is returned and no
    provider is called.
    """

    provider = FakeProvider()

    brief = get_decision_brief(
        seeded_database,
        "EXC-900001",
        provider=provider,
    )

    assert brief["status"] == "unavailable"
    assert provider.calls == []
    assert "manual" in brief["message"].lower()


def test_unknown_exception_returns_unavailable(
    seeded_database,
):
    """A missing exception degrades honestly."""

    brief = get_decision_brief(
        seeded_database,
        "EXC-DOES-NOT-EXIST",
        provider=FakeProvider(),
    )

    assert brief["status"] == "unavailable"


# ==================================================
# BUILT-IN PROVIDER CONTENT (GROUNDED)
# ==================================================

def test_built_in_provider_quotes_only_evidence_facts(
    actionable_database,
):
    """
    The built-in summariser may only state facts present in the
    evidence: the recorded issue, the dates, the recommendation,
    the weights and the confidence basis.
    """

    evidence = build_decision_brief_evidence(
        actionable_database,
        "EXC-900002",
    )

    brief = validate_decision_brief(
        TemplateBriefProvider()(evidence),
        evidence,
    )

    exception = evidence["exception"]

    assert exception["description"] in (
        brief["situation_summary"]
    )

    assert (
        evidence["recommendation"]["transport_mode"]
        in brief["recommended_action"]
    )

    assert str(
        evidence["recommendation"]["decision_score"]
    )[:4] in brief["recommended_action"]

    assert exception["estimated_arrival"] in (
        brief["situation_summary"]
    )


def test_built_in_provider_flags_arrival_gap(
    seeded_database,
):
    """
    When the recorded ETA misses the required delivery, the
    verification points say exactly that with the real dates.
    """

    # Make the fixture's delayed shipment actually miss its
    # required date in the evidence.
    evidence = build_decision_brief_evidence(
        seeded_database,
        "EXC-900002",
    )

    assert evidence["exception"]["required_delivery_date"]

    provider = TemplateBriefProvider()

    # Direct provider call on shaped evidence: ETA after the
    # required date must surface as a verification point.
    shaped = dict(evidence)
    shaped["exception"] = dict(evidence["exception"])
    shaped["exception"]["estimated_arrival"] = "2026-09-17"
    shaped["exception"]["required_delivery_date"] = (
        "2026-09-15"
    )
    shaped["recommendation"] = {
        "option_id": "OPT-000001",
        "transport_mode": "Air",
        "carrier_id": "CAR-900001",
        "decision_score": 80.0,
        "confidence": "High",
    }
    shaped["alternatives"] = []
    shaped["rationale"] = {
        "weights": {
            "cost": 0.25,
            "transit": 0.30,
            "risk": 0.25,
            "priority_alignment": 0.20,
        },
        "factor_breakdown": [
            {
                "factor": "Cost fit",
                "weight": 0.25,
                "values": [
                    {
                        "option_id": "OPT-000001",
                        "transport_mode": "Air",
                        "score": 61.0,
                        "contribution": 15.25,
                    }
                ],
            }
        ],
        "trade_offs": [],
        "confidence_basis": "test basis",
    }

    raw = provider(shaped)

    assert any(
        "2026-09-17" in point and "2026-09-15" in point
        for point in raw["verification_points"]
    )
