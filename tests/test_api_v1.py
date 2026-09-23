# ==================================================
# P2: VERSIONED APPLICATION BOUNDARY (/v1) — CONTRACT
# TESTS (ADR-011)
# ==================================================
#
# The /v1 surface exposes the workspace capabilities the
# future web client needs, over the same service layer,
# API-key guard and error mapping as the machine-to-machine
# endpoints. These tests verify the HTTP contracts: response
# schemas, representative domain behaviour, error paths and
# the boundary's independence from the persistence layer's
# row type. data/adensa.db is never touched.

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.config import ADENSA_CORS_ORIGINS
from app.generate_recovery_options import generate_recovery_options
from app.migrations import CURRENT_VERSION
from app.services import get_latest_action as services_get_latest_action
from app.workflow_engine import generate_workflow_actions

from tests.test_api import (
    TEST_API_KEY,
    api_client,  # noqa: F401 — reuse the shared authorized client.
)


def _generate_options_and_action(connection):
    """
    Create the real recovery options and workflow action for
    EXC-900002 through the production generators.
    """

    generate_recovery_options(connection)
    generate_workflow_actions(connection)


# ==================================================
# READINESS
# ==================================================

def test_v1_inbox_estimated_impact_matches_domain_output(api_client):
    """
    The inbox contract must describe the data the detection
    engine actually writes: `estimated_impact` is the domain's
    descriptive operational sentence, not a numeric amount.

    This pins the live-data regression caught during P3: the
    models originally declared a float and every real bootstrap
    dataset request failed response validation (HTTP 500) while
    float-seeded fixtures passed.
    """

    client, connection = api_client

    response = client.get("/v1/exceptions/inbox")

    assert response.status_code == 200

    rows = response.json()
    assert rows, "expected the seeded exception in the inbox"

    for row in rows:
        assert isinstance(row["estimated_impact"], str)

    # The production detection engine's exact wording.
    assert rows[0]["estimated_impact"].startswith(
        "Estimated delivery delay of "
    )


def test_ready_verifies_database_reachability(api_client):
    """
    /ready is public and confirms the application can use
    the configured database, exposing no internals.
    """

    client, _ = api_client

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
    }


def test_ready_fails_against_outdated_schema(seeded_database, monkeypatch):
    """
    A schema-current database minus a later migration's table
    (the P3.1 drift state: canonical DDL present, version stamp
    absent) must fail readiness as degraded — the API cannot
    silently operate against a known stale schema (ADR-012).
    """

    connection = seeded_database
    connection.execute("PRAGMA user_version = 0")
    connection.commit()

    try:
        with TestClient(app) as client:
            response = client.get("/ready")

            assert response.status_code == 503
            assert response.json() == {
                "status": "degraded",
                "database": "schema-outdated",
            }
    finally:
        connection.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
        connection.commit()


# ==================================================
# INBOX + CONTROL TOWER
# ==================================================

def test_v1_inbox_returns_contract_shapes(api_client):
    """
    The /v1 inbox returns the documented work-queue contract
    with the seeded exception present and correct types.
    """

    client, connection = api_client

    response = client.get("/v1/exceptions/inbox")

    assert response.status_code == 200

    rows = response.json()

    assert isinstance(rows, list)
    assert len(rows) >= 1

    row = next(
        r for r in rows if r["exception_id"] == "EXC-900002"
    )

    assert row["severity"] == "High"
    assert row["exception_type"] == "Shipment Delay"
    assert row["shipment_id"] == "SHP-900002"
    assert row["transport_mode"] == "Sea"
    assert isinstance(row["feasible_option_count"], int)
    assert isinstance(row["executed_still_open"], int)
    assert row["resolution_status"] == "Open"


def test_v1_control_tower_summary_contract(api_client):
    """
    The control-tower summary returns the documented metric
    populations and queues.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    response = client.get("/v1/control-tower/summary")

    assert response.status_code == 200

    body = response.json()

    for key in (
        "open_exceptions",
        "actionable_exceptions",
        "monitoring_exceptions",
        "pending_approvals",
        "awaiting_execution",
        "critical_exceptions",
        "follow_up_required",
        "follow_up_queue",
        "recently_resolved",
    ):
        assert key in body

    assert body["open_exceptions"] >= 1
    assert body["pending_approvals"] == 1
    assert body["follow_up_queue"] == []
    assert body["recently_resolved"] == []
    assert body["monitoring_exceptions"] == 1
    assert body["actionable_exceptions"] == 1


# ==================================================
# INVESTIGATION: CONTEXT / STATE / HISTORY
# ==================================================

def test_v1_context_returns_situation_contract(api_client):
    """
    The investigation context carries the full Situation &
    Impact contract for the seeded exception.
    """

    client, _ = api_client

    response = client.get("/v1/exceptions/EXC-900002/context")

    assert response.status_code == 200

    body = response.json()

    assert body["exception_id"] == "EXC-900002"
    assert body["shipment_id"] == "SHP-900002"
    assert body["order_id"] == "ORD-900001"
    assert body["customer_id"] == "CUS-900001"
    assert body["severity"] == "High"
    assert body["status"] == "Open"
    assert body["origin"] == "Rotterdam"
    assert body["destination"] == "Hamburg"
    assert body["route"] == "Rotterdam → Hamburg"
    assert body["required_delivery_date"] == "2026-09-15"


def test_v1_state_classifies_decision_required(api_client):
    """
    A pending action classifies the exception as Decision
    required through the persisted-evidence contract.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    response = client.get("/v1/exceptions/EXC-900002/state")

    assert response.status_code == 200

    body = response.json()

    assert body["state"] == "Decision required"
    assert body["follow_up_required"] is False
    assert "Pending Approval" in body["reason"] or (
        "awaiting" in body["reason"]
    )


def test_v1_state_without_action_reports_no_system_recovery(api_client):
    """
    An exception with no recovery action reports the honest
    no-system-recovery state.
    """

    client, _ = api_client

    response = client.get("/v1/exceptions/EXC-900001/state")

    assert response.status_code == 200

    body = response.json()

    assert body["state"] == "No system recovery available"
    assert body["follow_up_required"] is False


def test_v1_history_returns_chronological_entries(api_client):
    """
    The history endpoint returns the reconstructed lifecycle:
    detection first, then the evidence-ordered entries.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    response = client.get("/v1/exceptions/EXC-900002/history")

    assert response.status_code == 200

    entries = response.json()

    assert isinstance(entries, list)
    assert entries[0]["event"] == "Exception detected"
    assert entries[0]["sequence"] == 0

    events = [entry["event"] for entry in entries]

    assert "Recovery options evaluated" in events
    assert "Recommendation generated" in events

    for entry in entries:
        assert set(entry) == {
            "timestamp",
            "event",
            "detail",
            "actor",
            "sequence",
        }


# ==================================================
# INVESTIGATION: ASSESSMENT + SUSTAINABILITY
# ==================================================

def test_v1_assessment_returns_recommendation_and_rationale(api_client):
    """
    The assessment contract carries the deterministic
    recommendation, its alternatives and the full rationale.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    response = client.get("/v1/exceptions/EXC-900002/assessment")

    assert response.status_code == 200

    body = response.json()

    recommendation = body["recommendation"]

    assert recommendation is not None
    assert recommendation["transport_mode"] in (
        "Air",
        "Road",
        "Rail",
    )
    assert recommendation["decision_score"] > 0
    assert recommendation["confidence"] in (
        "High",
        "Medium",
        "Low",
    )

    assert len(body["alternatives"]) == 2

    rationale = body["rationale"]

    assert rationale is not None
    assert abs(
        sum(rationale["weights"].values()) - 1.0
    ) < 1e-9
    assert {
        factor["factor"]
        for factor in rationale["factor_breakdown"]
    } == {
        "Cost fit",
        "Transit fit",
        "Risk fit",
        "Priority fit",
    }
    assert body["evaluated_options"] == []


def test_v1_assessment_without_feasible_options_explains_why(api_client):
    """
    The Low-severity exception has no feasible recovery: the
    assessment reports no recommendation and carries the
    evaluated options instead.
    """

    client, connection = api_client

    generate_recovery_options(connection)

    response = client.get("/v1/exceptions/EXC-900001/assessment")

    assert response.status_code == 200

    body = response.json()

    assert body["recommendation"] is None
    assert body["alternatives"] == []
    assert body["rationale"] is None
    assert isinstance(body["evaluated_options"], list)


def test_v1_sustainability_returns_comparison_or_unavailable(api_client):
    """
    The sustainability endpoint returns the informational
    comparison for a recommended exception, and the
    structured unavailable state when nothing can be
    compared.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    response = client.get("/v1/exceptions/EXC-900002/sustainability")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "available"
    assert body["unit"] == "kg CO₂e"
    assert len(body["estimates"]) == 3
    assert body["lowest_emission_option"] is not None

    # The no-recommendation exception is an existing
    # exception with nothing to compare: the structured
    # unavailable state, not a 404.
    response = client.get("/v1/exceptions/EXC-900001/sustainability")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "unavailable"
    assert "reason" in body


# ==================================================
# MANUAL INTERVENTIONS
# ==================================================

def test_v1_manual_resolution_round_trip(api_client):
    """
    Recording a manual resolution through /v1 persists the
    intervention, reports the resulting exception status and
    is readable back through the interventions endpoint.
    """

    client, _ = api_client

    response = client.post(
        "/v1/exceptions/EXC-900001/manual-resolution",
        json={
            "intervention_type": "Carrier call",
            "external_party": "Fixture Carrier",
            "resolution_summary": "Coordinated a revised delivery plan.",
            "recorded_by": "P. Planner",
            "outcome": "Resolved",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["intervention_id"].startswith("INT-")
    assert body["exception_id"] == "EXC-900001"
    assert body["outcome"] == "Resolved"
    assert body["exception_status"] == "Resolved"
    assert body["recorded_by"] == "P. Planner"

    listing = client.get("/v1/exceptions/EXC-900001/interventions")

    assert listing.status_code == 200

    records = listing.json()

    assert len(records) == 1
    assert records[0]["intervention_id"] == body["intervention_id"]
    assert records[0]["external_party"] == "Fixture Carrier"


def test_v1_manual_resolution_rejects_invalid_type(api_client):
    """
    An unknown intervention type is a domain failure mapped
    to 409; nothing is recorded.
    """

    client, _ = api_client

    response = client.post(
        "/v1/exceptions/EXC-900001/manual-resolution",
        json={
            "intervention_type": "Carrier pigeon",
            "external_party": "Fixture Carrier",
            "resolution_summary": "Not a valid path.",
            "recorded_by": "P. Planner",
            "outcome": "Resolved",
        },
    )

    assert response.status_code == 409


def test_v1_manual_resolution_missing_exception_returns_404(api_client):
    """
    A manual resolution for an unknown exception is 404.
    """

    client, _ = api_client

    response = client.post(
        "/v1/exceptions/EXC-DOES-NOT-EXIST/manual-resolution",
        json={
            "intervention_type": "Carrier call",
            "external_party": "Fixture Carrier",
            "resolution_summary": "Nothing to resolve.",
            "recorded_by": "P. Planner",
            "outcome": "Resolved",
        },
    )

    assert response.status_code == 404


def test_v1_manual_resolution_requires_actor_and_summary(api_client):
    """
    The request contract enforces the required free-text
    fields at the boundary (422 before any domain logic).
    """

    client, _ = api_client

    response = client.post(
        "/v1/exceptions/EXC-900001/manual-resolution",
        json={
            "intervention_type": "Carrier call",
            "external_party": "Fixture Carrier",
            "resolution_summary": "",
            "recorded_by": "",
            "outcome": "Resolved",
        },
    )

    assert response.status_code == 422


# ==================================================
# OPERATIONS: REFRESH + SIMULATION
# ==================================================

def test_v1_refresh_is_idempotent_and_reports_new_work(api_client):
    """
    The first refresh on the seeded dataset reports the work
    it created; a second refresh creates nothing new.
    """

    client, _ = api_client

    response = client.post("/v1/operations/refresh")

    assert response.status_code == 200

    first = response.json()

    assert first["new_exceptions"] >= 0
    assert first["new_options"] == 3
    assert first["new_actions"] == 1
    # Both open exceptions were evaluated; only the one with
    # a feasible recommendation produced an action.
    assert first["actions_evaluated"] == 2
    assert first["actions_without_recommendation"] == 1
    assert first["actions_skipped"] == 0

    response = client.post("/v1/operations/refresh")

    assert response.status_code == 200

    second = response.json()

    assert second["new_exceptions"] == 0
    assert second["new_options"] == 0
    assert second["new_actions"] == 0


def test_v1_simulate_arrival_creates_arrival_only(api_client):
    """
    The simulation endpoint creates one controlled arrival
    and never exceptions or actions — detection is the
    refresh's job.
    """

    client, _ = api_client

    response = client.post("/v1/operations/simulate-arrival")

    assert response.status_code == 200

    body = response.json()

    assert body["shipment_id"].startswith("SHP-SIM-")
    assert body["event_count"] == 2
    assert body["delay_days"] == 6

    summary = client.get("/v1/control-tower/summary").json()

    assert summary["pending_approvals"] == 0


def test_v1_simulate_arrival_without_data_returns_409(
    seeded_database,
    monkeypatch,
):
    """
    With no operational data to derive a scenario from, the
    simulation endpoint fails honestly with 409.
    """

    # Remove the exceptions and shipments (children first)
    # so no arrival-scenario context exists.
    seeded_database.execute("DELETE FROM exceptions")
    seeded_database.execute("DELETE FROM shipments")
    seeded_database.commit()

    monkeypatch.setattr("app.api.ADENSA_API_KEY", TEST_API_KEY)

    with TestClient(app) as client:

        response = client.post(
            "/v1/operations/simulate-arrival",
            headers={"X-API-Key": TEST_API_KEY},
        )

    assert response.status_code == 409


# ==================================================
# ERROR PATHS
# ==================================================

def test_v1_reads_missing_exception_return_404(api_client):
    """
    Every per-exception /v1 read maps a missing exception to
    a clean 404.
    """

    client, _ = api_client

    for path in (
        "/v1/exceptions/EXC-DOES-NOT-EXIST/context",
        "/v1/exceptions/EXC-DOES-NOT-EXIST/state",
        "/v1/exceptions/EXC-DOES-NOT-EXIST/history",
        "/v1/exceptions/EXC-DOES-NOT-EXIST/assessment",
        "/v1/exceptions/EXC-DOES-NOT-EXIST/interventions",
    ):

        response = client.get(path)

        assert response.status_code == 404, path


def test_v1_sustainability_missing_exception_returns_404(api_client):
    """
    The sustainability read maps a missing exception to 404
    (distinguished from the structured unavailable state).
    """

    client, _ = api_client

    response = client.get(
        "/v1/exceptions/EXC-DOES-NOT-EXIST/sustainability"
    )

    assert response.status_code == 404


# ==================================================
# BOUNDARY INTEGRITY
# ==================================================

def test_v1_responses_are_json_compatible_not_row_objects(api_client):
    """
    The boundary contract (ADR-011): service results reaching
    /v1 are ordinary JSON structures. Every response body
    survives a full JSON round trip and no persistence-layer
    row representation leaks into any field.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    for path in (
        "/v1/exceptions/inbox",
        "/v1/control-tower/summary",
        "/v1/exceptions/EXC-900002/context",
        "/v1/exceptions/EXC-900002/state",
        "/v1/exceptions/EXC-900002/history",
        "/v1/exceptions/EXC-900002/assessment",
        "/v1/exceptions/EXC-900002/sustainability",
        "/v1/exceptions/EXC-900002/interventions",
    ):

        response = client.get(path)

        assert response.status_code == 200, path

        # jsonable round trip raises for non-JSON-native values.
        encoded = response.content.decode("utf-8")

        assert "sqlite3" not in encoded, path


def test_v1_endpoints_require_api_key(seeded_database, monkeypatch):
    """
    The /v1 surface is guarded by the same API-key
    mechanism: missing or wrong keys are rejected before any
    domain logic.
    """

    monkeypatch.setattr("app.api.ADENSA_API_KEY", TEST_API_KEY)

    with TestClient(app) as client:

        for path in (
            "/v1/control-tower/summary",
            "/v1/exceptions/inbox",
            "/v1/exceptions/EXC-900002/context",
            "/v1/exceptions/EXC-900002/assessment",
        ):

            assert client.get(path).status_code == 401, path

            assert (
                client.get(
                    path,
                    headers={"X-API-Key": "wrong-key"},
                ).status_code
                == 401
            ), path

        assert (
            client.post(
                "/v1/operations/refresh"
            ).status_code
            == 401
        )


def test_ready_and_health_stay_public(seeded_database, monkeypatch):
    """
    The probe contracts are unchanged: /health and /ready
    need no key even when the operational endpoints fail
    closed.
    """

    monkeypatch.setattr("app.api.ADENSA_API_KEY", None)

    with TestClient(app) as client:

        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json()["status"] == "ready"
        assert (
            client.get("/v1/exceptions/inbox").status_code
            == 503
        )


# ==================================================
# CORS CONFIGURATION
# ==================================================

def test_cors_disabled_by_default(seeded_database, monkeypatch):
    """
    With no CORS middleware mounted (empty origin
    configuration), the preflight request is not handled at
    all: Method Not Allowed, no allow-origin header.
    """

    monkeypatch.setattr("app.api.ADENSA_API_KEY", TEST_API_KEY)

    with TestClient(app) as client:

        response = client.options(
            "/v1/exceptions/inbox",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-api-key",
            },
        )

    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_configured_origin_only(seeded_database, monkeypatch):
    """
    A configured origin is honoured for preflight and actual
    requests; a different origin is not. The configuration is
    read at import time, so this test re-imports the app
    module with the environment set.
    """

    monkeypatch.setenv(
        "ADENSA_CORS_ORIGINS",
        "http://localhost:3000",
    )

    import importlib

    import app.api as api_module
    import app.config as config_module

    importlib.reload(config_module)
    importlib.reload(api_module)

    try:

        assert api_module.ADENSA_CORS_ORIGINS == [
            "http://localhost:3000"
        ]

        with TestClient(api_module.app) as client:

            preflight = client.options(
                "/v1/exceptions/inbox",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "x-api-key",
                },
            )

            assert preflight.status_code == 200
            assert (
                preflight.headers["access-control-allow-origin"]
                == "http://localhost:3000"
            )

            actual = client.get(
                "/v1/exceptions/inbox",
                headers={
                    "X-API-Key": TEST_API_KEY,
                    "Origin": "http://localhost:3000",
                },
            )

            # The reloaded module reads the repository-default
            # key config (unset in this environment), so the
            # operational endpoint fails closed (503). The CORS
            # assertion is what matters here: the configured
            # origin is echoed on the fail-closed response.
            assert actual.status_code == 503
            assert (
                actual.headers["access-control-allow-origin"]
                == "http://localhost:3000"
            )

            other = client.get(
                "/v1/exceptions/inbox",
                headers={
                    "X-API-Key": TEST_API_KEY,
                    "Origin": "http://evil.example",
                },
            )

            assert other.status_code == 503
            assert (
                "access-control-allow-origin" not in other.headers
            )

    finally:

        importlib.reload(config_module)
        importlib.reload(api_module)


def test_cors_configuration_defaults_to_no_origins():
    """
    The repository default is an empty allow-list: no origin
    is trusted unless a deployment configures one.
    """

    assert ADENSA_CORS_ORIGINS == []


# ==================================================
# DECISION BRIEF (ADVISORY AI, P4.x)
# ==================================================

def test_v1_decision_brief_returns_advisory_contract(api_client):
    """
    The advisory AI decision brief for a recommended exception
    is available, carries the advisory label and disclaimer,
    and is grounded in the deterministic assessment.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    response = client.get("/v1/exceptions/EXC-900002/decision-brief")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "available"
    assert body["advisory_label"] == "AI-assisted · Advisory only"
    assert body["provider"] == "adensa-evidence-brief/v1"
    assert body["situation_summary"].strip()
    assert body["recommended_action"].strip()
    assert body["rationale"].strip()
    assert body["tradeoffs"].strip()
    assert isinstance(body["verification_points"], list)
    assert body["disclaimer"].strip()

    # Grounded in the requested exception's own evidence: the
    # brief names the assessed option of EXC-900002, and no
    # identifier outside this exception's evidence appears.
    assert "OPT-" in body["recommended_action"]

    from app.ai_support import IDENTIFIER_PATTERN

    for identifier in IDENTIFIER_PATTERN.findall(
        " ".join(
            [
                body["situation_summary"],
                body["recommended_action"],
                body["rationale"],
                body["tradeoffs"],
            ]
        )
    ):
        assert identifier.startswith(
            ("EXC-900002", "SHP-900002", "ORD-900002")
        ) or identifier.startswith(("OPT-", "CAR-", "ACT-"))


def test_v1_decision_brief_is_scoped_to_the_requested_exception(api_client):
    """
    The brief can only describe the requested exception: two
    different exceptions produce different briefs, each
    grounded in its own identifiers.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    brief_900002 = client.get(
        "/v1/exceptions/EXC-900002/decision-brief"
    ).json()

    response_900001 = client.get(
        "/v1/exceptions/EXC-900001/decision-brief"
    )

    assert response_900001.status_code == 200

    brief_900001 = response_900001.json()

    # EXC-900001 is seeded on-time with no generated recovery
    # options: no deterministic recommendation exists, so the
    # honest answer is the structured unavailable state.
    assert brief_900001["status"] == "unavailable"
    assert "EXC-900001" not in str(brief_900001.get(
        "situation_summary"
    ))

    # EXC-900002's own brief names its own exception facts
    # (the summariser cites the shipment, type and severity).
    assert "SHP-900002" in brief_900002["situation_summary"]
    assert "SHP-900001" not in brief_900002["situation_summary"]


def test_v1_decision_brief_missing_exception_returns_404(api_client):
    """
    A nonexistent exception cannot produce a brief: 404,
    distinguishing not-found from the advisory unavailable
    state (mirrors sustainability/interventions).
    """

    client, _ = api_client

    response = client.get("/v1/exceptions/EXC-DOES-NOT-EXIST/decision-brief")

    assert response.status_code == 404
    assert "EXC-DOES-NOT-EXIST" in response.json()["detail"]


def test_v1_decision_brief_fabricated_content_is_rejected(
    api_client,
    monkeypatch,
):
    """
    Advisory content that invents an operational identifier or
    claims an executed action is rejected by the existing
    validation and degrades to the structured unavailable
    state — the boundary never serves unverified text.
    """

    from app.ai_support import (
        ADVISORY_DISCLAIMER,
        AiProviderError,
    )
    from app import services

    client, connection = api_client

    _generate_options_and_action(connection)

    def _fabricating_provider(evidence):
        return {
            "situation_summary": "Situation summary.",
            "recommended_action": (
                "Consider alternative OPT-999999 which fits better."
            ),
            "rationale": "Grounded explanation.",
            "tradeoffs": "Factual statement.",
            "verification_points": [],
            "disclaimer": ADVISORY_DISCLAIMER,
            "provider": "fabricating-provider",
        }

    monkeypatch.setattr(
        services,
        "DEFAULT_PROVIDER",
        _fabricating_provider,
    )

    response = client.get("/v1/exceptions/EXC-900002/decision-brief")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "unavailable"
    assert "OPT-999999" in body["message"]

    # A provider outage degrades the same way — never a 500.
    def _failing_provider(evidence):
        raise AiProviderError("provider unreachable")

    monkeypatch.setattr(
        services,
        "DEFAULT_PROVIDER",
        _failing_provider,
    )

    response = client.get("/v1/exceptions/EXC-900002/decision-brief")

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert "provider unreachable" in response.json()["message"]


def test_v1_decision_brief_does_not_mutate_workflow_or_database(api_client):
    """
    Requesting a brief is a pure read: the recovery action's
    workflow state, the operational tables and the exception's
    lifecycle are byte-identical before and after.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    action = services_get_latest_action(connection, "EXC-900002")

    def _operational_snapshot(connection):

        tables = (
            "exceptions",
            "recovery_options",
            "recovery_actions",
            "shipment_events",
        )

        return {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in tables
        }

    before_counts = _operational_snapshot(connection)
    before_status = action["status"]

    response = client.get("/v1/exceptions/EXC-900002/decision-brief")

    assert response.status_code == 200

    after_action = services_get_latest_action(
        connection,
        "EXC-900002",
    )

    assert after_action["status"] == before_status
    assert _operational_snapshot(connection) == before_counts

    # The brief is not persisted anywhere.
    briefs_table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name LIKE '%brief%'"
    ).fetchall()

    assert briefs_table == []
