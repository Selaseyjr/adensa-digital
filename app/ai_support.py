"""
Advisory AI decision-support layer.

Position in the architecture:

    Streamlit / API / CLI
         ↓
      services
         ↓
   deterministic engines   ← the ONLY decision authority
         ↓
   ai_support (this module) ← advisory interpretation, ABOVE
         ↓                    the decision model
      planner

The deterministic decision engine remains the sole authority for
candidate options, factor scores, policy weights, the
recommendation, confidence and lifecycle state. This module can
only INTERPRET evidence that the deterministic system has already
established. It never selects, scores, overrides, approves,
executes or resolves anything, and it never touches the database.

Providers:

A provider is any callable receiving an evidence dictionary
(structured facts already established by Adensa) and returning a
decision-brief dictionary. The default provider is a deterministic
evidence summariser (no network, no external model) so the
application works — and stays fully testable — with no provider
configured. A real external model provider can later be plugged in
behind the same interface; it would source its credentials from the
environment, never from code or the database, and must translate
all of its failures (missing key, network, timeout, malformed
reply) into AiProviderError.

Output validation:

Every provider output — including the built-in provider's — is
validated before it reaches a planner:

- required fields present, string-typed, bounded length;
- verification_points bounded in count and length;
- the advisory disclaimer present;
- no language claiming an action was approved, executed or
  resolved (the AI is advisory; only the workflow engine changes
  state);
- no operational identifier (exception, shipment, order, option,
  action, carrier) that does not exist in the supplied evidence —
  a fabricated identifier means the output is rejected and the
  brief is reported unavailable rather than shown.
"""

import re


# ==================================================
# ERRORS
# ==================================================

class AiProviderError(Exception):
    """
    A provider failed to produce any output (missing
    credentials, network failure, timeout, provider outage).

    Real providers must translate every provider-specific
    failure into this error so the application can degrade
    gracefully.
    """


class BriefValidationError(ValueError):
    """
    A provider produced output that fails the decision-brief
    contract: missing/invalid fields, forbidden action claims,
    or identifiers that do not exist in the supplied evidence.
    """


# ==================================================
# CONTRACT
# ==================================================

REQUIRED_BRIEF_FIELDS = (
    "situation_summary",
    "recommended_action",
    "rationale",
    "tradeoffs",
)

# Field -> maximum accepted character length. Bounds keep a
# misbehaving provider from dumping unbounded text into the UI.

FIELD_LENGTH_LIMITS = {
    "situation_summary": 1200,
    "recommended_action": 800,
    "rationale": 1500,
    "tradeoffs": 1200,
    "disclaimer": 500,
}

MAX_VERIFICATION_POINTS = 6
MAX_VERIFICATION_POINT_LENGTH = 400

# Language that would present the advisory brief as if a
# workflow action had occurred. Only the workflow/execution
# engines change operational state.

FORBIDDEN_CLAIM_PATTERNS = (
    re.compile(
        r"\b(i|we|the system|adensa|this brief)\s+"
        r"(have\s+|has\s+)?(approved|executed|rejected|resolved)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(has|have|was|were|is|being)\s+(been\s+)?"
        r"(approved|executed|rejected|resolved)\b",
        re.IGNORECASE,
    ),
)

# Operational identifiers the grounding check understands.

IDENTIFIER_PATTERN = re.compile(
    r"\b(?:EXC|SHP|ORD|OPT|ACT|CAR|INT)-\d+\b"
)

ADVISORY_DISCLAIMER = (
    "AI-assisted summary of Adensa's deterministic assessment. "
    "Advisory only: it does not approve, execute, or resolve "
    "anything — the planner decides."
)

UNAVAILABLE_MESSAGE = (
    "AI decision brief unavailable. Deterministic "
    "recommendation remains available."
)


def unavailable_brief(message):
    """
    The structured 'advisory layer unavailable' state. It never
    hides or replaces the deterministic recommendation; the UI
    keeps rendering that regardless.
    """

    return {
        "status": "unavailable",
        "message": message,
    }


# ==================================================
# VALIDATION
# ==================================================

def validate_decision_brief(brief, evidence):
    """
    Validate any provider's decision brief against the contract
    and the supplied evidence. Returns the brief (normalised to
    the public shape) or raises BriefValidationError.
    """

    if not isinstance(brief, dict):
        raise BriefValidationError(
            "brief must be a dictionary"
        )

    for field in REQUIRED_BRIEF_FIELDS:

        value = brief.get(field)

        if not isinstance(value, str) or not value.strip():
            raise BriefValidationError(
                f"missing or non-string field: {field}"
            )

        if len(value) > FIELD_LENGTH_LIMITS[field]:
            raise BriefValidationError(
                f"field too long: {field}"
            )

    disclaimer = brief.get("disclaimer")

    if (
        not isinstance(disclaimer, str)
        or not disclaimer.strip()
        or len(disclaimer) > FIELD_LENGTH_LIMITS["disclaimer"]
    ):
        raise BriefValidationError(
            "missing or invalid disclaimer"
        )

    verification_points = brief.get(
        "verification_points",
        [],
    )

    if not isinstance(verification_points, list):
        raise BriefValidationError(
            "verification_points must be a list"
        )

    if len(verification_points) > MAX_VERIFICATION_POINTS:
        raise BriefValidationError(
            "too many verification_points"
        )

    for point in verification_points:

        if (
            not isinstance(point, str)
            or not point.strip()
            or len(point) > MAX_VERIFICATION_POINT_LENGTH
        ):
            raise BriefValidationError(
                "invalid verification point"
            )

    # --------------------------------------------------
    # ADVISORY BOUNDARY: no action-claim language.
    # --------------------------------------------------

    all_text = " ".join(
        [
            *[brief[field] for field in REQUIRED_BRIEF_FIELDS],
            disclaimer,
            *verification_points,
        ]
    )

    for pattern in FORBIDDEN_CLAIM_PATTERNS:

        if pattern.search(all_text):
            raise BriefValidationError(
                "brief must not claim an operational action "
                "was performed"
            )

    # --------------------------------------------------
    # FACT GROUNDING: every operational identifier in the
    # brief must exist in the supplied evidence.
    # --------------------------------------------------

    known_identifiers = _collect_known_identifiers(evidence)

    for identifier in IDENTIFIER_PATTERN.findall(all_text):

        if identifier not in known_identifiers:
            raise BriefValidationError(
                f"brief mentions unknown operational "
                f"identifier: {identifier}"
            )

    return {
        "status": "available",
        "advisory_label": "AI-assisted · Advisory only",
        "situation_summary": brief["situation_summary"].strip(),
        "recommended_action": brief["recommended_action"].strip(),
        "rationale": brief["rationale"].strip(),
        "tradeoffs": brief["tradeoffs"].strip(),
        "verification_points": [
            point.strip() for point in verification_points
        ],
        "disclaimer": disclaimer.strip(),
        "provider": str(brief.get("provider", "unknown")),
    }


def _collect_known_identifiers(evidence):

    known = set()

    exception = evidence.get("exception") or {}

    for key in (
        "exception_id",
        "shipment_id",
        "order_id",
        "customer_id",
        "carrier_id",
    ):
        value = exception.get(key)

        if isinstance(value, str):
            known.add(value)

    recommendation = evidence.get("recommendation") or {}

    if recommendation.get("option_id"):
        known.add(recommendation["option_id"])

    if recommendation.get("carrier_id"):
        known.add(recommendation["carrier_id"])

    for option in evidence.get("alternatives") or []:

        if option.get("option_id"):
            known.add(option["option_id"])

        if option.get("carrier_id"):
            known.add(option["carrier_id"])

    # Identifiers already recorded in the persisted history are
    # established facts too.

    for entry in evidence.get("history") or []:

        detail = entry.get("detail") or ""

        if isinstance(detail, str):
            known.update(
                IDENTIFIER_PATTERN.findall(detail)
            )

    return known


# ==================================================
# BUILT-IN PROVIDER (DETERMINISTIC, NO NETWORK)
# ==================================================

class TemplateBriefProvider:
    """
    The default decision-brief provider.

    It is deliberately NOT a language model: it is a
    deterministic summariser that turns the structured evidence
    into planner-facing sentences. It needs no credentials, makes
    no network calls, and always produces contract-valid output,
    so the advisory layer works — and is fully testable — before
    any external model is connected.

    A real model provider implements the same callable interface
    and is registered by replacing DEFAULT_PROVIDER; its
    credentials come from the environment and its failures must
    surface as AiProviderError.
    """

    name = "adensa-evidence-brief/v1"

    def __call__(self, evidence):

        return self.build_brief(evidence)

    def build_brief(self, evidence):

        exception = evidence["exception"]
        recommendation = evidence.get("recommendation")
        rationale = evidence.get("rationale")
        alternatives = evidence.get("alternatives") or []

        situation = (
            f"{exception['exception_type']} "
            f"({exception['severity']} severity) on shipment "
            f"{exception['shipment_id']} for "
            f"{exception['customer_name']}. "
            f"Recorded issue: {exception['description']}. "
            f"Shipment status {exception['shipment_status']}; "
            f"estimated arrival "
            f"{exception['estimated_arrival']} against required "
            f"delivery "
            f"{exception['required_delivery_date']}. "
            f"Exception is currently {exception['status']}."
        )

        weights = rationale["weights"]

        recommended_action = (
            f"Adensa recommends {recommendation['transport_mode']} "
            f"via {recommendation['carrier_id']} "
            f"(option {recommendation['option_id']}): decision "
            f"score {recommendation['decision_score']:.2f}, "
            f"confidence {recommendation['confidence']}."
        )

        contributions = ", ".join(
            f"{factor['factor'].lower()} fit "
            f"{factor['values'][0]['score']:.0f} contributing "
            f"{factor['values'][0]['contribution']:.2f}"
            for factor in rationale["factor_breakdown"]
        )

        rationale_text = (
            f"Policy weights favour this option (cost "
            f"{weights['cost']:.0%}, transit "
            f"{weights['transit']:.0%}, risk "
            f"{weights['risk']:.0%}, priority "
            f"{weights['priority_alignment']:.0%}): "
            f"{contributions}. "
            f"{rationale['confidence_basis']}"
        )

        trade_offs = rationale.get("trade_offs") or []

        if trade_offs:

            tradeoff_text = "; ".join(
                f"{entry['transport_mode']} "
                f"({entry['option_id']}) scores higher on "
                f"{' and '.join(entry['stronger_factors'])}"
                for entry in trade_offs
            )

            tradeoff_text = (
                f"{tradeoff_text} — the recommendation still "
                "wins on the weighted overall score."
            )

        else:

            tradeoff_text = (
                "No alternative scores higher on any individual "
                "factor."
            )

        verification_points = (
            self._verification_points(
                evidence,
                alternatives,
            )
        )

        return {
            "situation_summary": situation,
            "recommended_action": recommended_action,
            "rationale": rationale_text,
            "tradeoffs": tradeoff_text,
            "verification_points": verification_points,
            "disclaimer": ADVISORY_DISCLAIMER,
            "provider": self.name,
        }

    def _verification_points(
        self,
        evidence,
        alternatives,
    ):

        exception = evidence["exception"]
        points = []

        estimated_arrival = exception.get("estimated_arrival")
        required_delivery = exception.get(
            "required_delivery_date"
        )

        if (
            estimated_arrival
            and required_delivery
            and str(estimated_arrival) > str(required_delivery)
        ):
            points.append(
                "Confirm the revised delivery plan — estimated "
                f"arrival {estimated_arrival} remains later than "
                f"the required delivery date {required_delivery}."
            )

        if not alternatives:
            points.append(
                "Only one feasible recovery option was "
                "identified by the rules — verify that no other "
                "operationally viable recovery exists."
            )

        for entry in evidence.get("rationale", {}).get(
            "trade_offs",
            [],
        ):
            points.append(
                f"Review the {entry['transport_mode']} "
                f"alternative ({entry['option_id']}) — it "
                "scores higher on "
                f"{' and '.join(entry['stronger_factors'])}; "
                "confirm the weighted trade-off is acceptable."
            )

        return points


DEFAULT_PROVIDER = TemplateBriefProvider()
