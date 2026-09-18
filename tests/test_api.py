"""
Contract tests for the FastAPI boundary (app.api).

The API is exercised through TestClient against the existing
seeded_database fixture. Because the API's connection
dependency calls app.database.get_connection, the temporary
DATABASE_PATH patched by the fixture applies to the API as
well — data/adensa.db is never touched.

These tests verify HTTP contracts (status codes, shapes,
error mapping), not business rules: the engines and services
have their own suites.
"""

import pytest
from fastapi.testclient import TestClient

import app.database as database
from app import services
from app.api import app
from app.errors import RecoveryWorkflowError
from app.generate_recovery_options import generate_recovery_options
from app.repositories import recovery_actions_repo
from app.workflow_engine import generate_workflow_actions


# ==================================================
# FIXTURES / HELPERS
# ==================================================

@pytest.fixture()
def api_client(seeded_database):
    """
    Provide a TestClient served against the seeded temporary
    database, alongside the fixture connection for arranging
    test state.
    """

    with TestClient(app) as client:
        yield client, seeded_database


def _generate_options_and_action(connection):
    """
    Create the real workflow action for EXC-900002 through
    the production generator and workflow engine.
    """

    generate_recovery_options(connection)
    generate_workflow_actions(connection)

    action = recovery_actions_repo.get_latest_action_for_exception(
        connection,
        "EXC-900002",
    )

    assert action is not None

    return action


# ==================================================
# LIVENESS
# ==================================================

def test_health_returns_ok(api_client):
    client, _ = api_client

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ==================================================
# METRICS
# ==================================================

def test_metrics_returns_service_dashboard_counts(api_client):
    client, _ = api_client

    response = client.get("/metrics")

    assert response.status_code == 200

    body = response.json()

    assert set(body.keys()) == {
        "open_exceptions",
        "critical_exceptions",
        "pending_approvals",
    }

    assert body["open_exceptions"] == 2
    assert isinstance(body["pending_approvals"], int)


# ==================================================
# EXCEPTION INBOX
# ==================================================

def test_exceptions_returns_seeded_inbox_rows(api_client):
    client, _ = api_client

    response = client.get("/exceptions")

    assert response.status_code == 200

    rows = response.json()

    assert isinstance(rows, list)
    assert len(rows) == 2

    by_id = {row["exception_id"]: row for row in rows}

    assert set(by_id.keys()) == {"EXC-900001", "EXC-900002"}

    delayed = by_id["EXC-900002"]

    assert delayed["shipment_id"] == "SHP-900002"
    assert delayed["transport_mode"] == "Sea"
    assert delayed["resolution_status"] == "Open"
    assert "required_delivery_date" in delayed
    assert "estimated_impact" in delayed


# ==================================================
# EXCEPTION REVIEW
# ==================================================

def test_review_returns_recommendation_contract(api_client):
    client, connection = api_client

    try:
        generate_recovery_options(connection)

        response = client.get(
            "/exceptions/EXC-900002/review"
        )

        assert response.status_code == 200

        body = response.json()

        recommendation = body["recommendation"]

        assert recommendation is not None
        assert recommendation["option_id"].startswith("OPT-")
        assert "transport_mode" in recommendation
        assert isinstance(
            recommendation["decision_score"], (int, float)
        )
        assert recommendation["confidence"] in (
            "High", "Medium", "Low",
        )
        assert isinstance(body["alternatives"], list)

    finally:
        connection.close()


def test_review_without_feasible_options_returns_null_recommendation(
    api_client,
):
    client, _ = api_client

    # EXC-900001 is Low severity: the generator creates no
    # options for it, so the review carries no recommendation.
    response = client.get(
        "/exceptions/EXC-900001/review"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["recommendation"] is None
    assert body["alternatives"] == []


def test_review_for_missing_exception_returns_404(api_client):
    client, _ = api_client

    response = client.get(
        "/exceptions/EXC-999999/review"
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


# ==================================================
# LATEST ACTION
# ==================================================

def test_latest_action_returns_null_without_actions(api_client):
    client, _ = api_client

    response = client.get(
        "/exceptions/EXC-900002/actions/latest"
    )

    assert response.status_code == 200
    assert response.json() is None


def test_latest_action_returns_created_action(api_client):
    client, connection = api_client

    try:
        _generate_options_and_action(connection)

        response = client.get(
            "/exceptions/EXC-900002/actions/latest"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["action_id"].startswith("ACT-")
        assert body["option_id"].startswith("OPT-")
        assert body["status"] == "Pending Approval"
        assert "action_type" in body
        assert "approved_at" in body
        assert "executed_at" in body

    finally:
        connection.close()


# ==================================================
# ERROR MAPPING
# ==================================================

def test_recovery_workflow_error_maps_to_409(
    api_client,
    monkeypatch,
):
    """
    A RecoveryWorkflowError raised inside a service is mapped
    to HTTP 409 with the existing engine message — the same
    mapping the mutation endpoints of Slice 2 will rely on.
    """

    client, _ = api_client

    def _raise_domain_error(_connection):
        raise RecoveryWorkflowError(
            "Simulated workflow violation."
        )

    monkeypatch.setattr(
        services,
        "get_dashboard_metrics",
        _raise_domain_error,
    )

    response = client.get("/metrics")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Simulated workflow violation."
    }
