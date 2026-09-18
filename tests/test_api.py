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


# ==================================================
# MUTATIONS — APPROVE
# ==================================================

def test_approve_happy_path_returns_identity_fields(api_client):
    client, connection = api_client

    try:
        action = _generate_options_and_action(connection)
    finally:
        connection.close()

    response = client.post(
        "/exceptions/EXC-900002/approve",
        json={"approved_by": "API Test"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["action_id"] == action["action_id"]
    assert body["shipment_id"] == "SHP-900002"
    # new_mode comes from the stored recovery option
    # (Road wins the seeded recommendation), not from
    # the shipment's current mode.
    assert body["previous_mode"] == "Sea"
    assert body["new_mode"] == "Road"
    assert body["carrier_id"].startswith("CAR-")
    assert body["new_eta"] == "Pending execution"
    assert body["exception_status"] == "Open"
    assert "approved successfully" in body["message"]


def test_approve_missing_exception_returns_404(api_client):
    client, _ = api_client

    response = client.post(
        "/exceptions/EXC-999999/approve",
        json={"approved_by": "API Test"},
    )

    assert response.status_code == 404
    assert "No recovery action exists" in response.json()["detail"]


def test_approve_missing_actor_returns_422(api_client):
    client, _ = api_client

    response = client.post(
        "/exceptions/EXC-900002/approve",
        json={},
    )

    assert response.status_code == 422


def test_approve_empty_actor_returns_422(api_client):
    client, _ = api_client

    response = client.post(
        "/exceptions/EXC-900002/approve",
        json={"approved_by": ""},
    )

    assert response.status_code == 422


def test_double_approve_returns_409(api_client):
    client, connection = api_client

    try:
        _generate_options_and_action(connection)
    finally:
        connection.close()

    first = client.post(
        "/exceptions/EXC-900002/approve",
        json={"approved_by": "API Test"},
    )

    assert first.status_code == 200

    second = client.post(
        "/exceptions/EXC-900002/approve",
        json={"approved_by": "API Test"},
    )

    assert second.status_code == 409
    assert "Invalid workflow transition" in second.json()["detail"]


# ==================================================
# MUTATIONS — REJECT
# ==================================================

def test_reject_happy_path_preserves_sentinels(api_client):
    client, connection = api_client

    try:
        _generate_options_and_action(connection)
    finally:
        connection.close()

    response = client.post(
        "/exceptions/EXC-900002/reject",
        json={"rejected_by": "API Test"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert "rejected" in body["message"]
    assert body["exception_status"] == "Open"
    assert body["carrier_id"] == "No execution"
    assert body["new_eta"] == "No execution"
    assert body["recovery_event"] == "None"


def test_reject_missing_actor_returns_422(api_client):
    client, _ = api_client

    response = client.post(
        "/exceptions/EXC-900002/reject",
        json={},
    )

    assert response.status_code == 422


# ==================================================
# MUTATIONS — EXECUTE
# ==================================================

def test_execute_still_open_branch_returns_200(api_client):
    client, connection = api_client

    try:
        action = _generate_options_and_action(connection)

        services.approve_recovery(
            connection,
            action["action_id"],
            "API Test",
        )
    finally:
        connection.close()

    response = client.post(
        f"/recovery-actions/{action['action_id']}/execute",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    # Seeded timing: Sea 2026-09-20 vs required 2026-09-15,
    # Road arrives 2026-09-17 — still late, so Open.
    assert body["previous_mode"] == "Sea"
    assert body["new_mode"] == "Road"
    assert body["new_eta"] == "2026-09-17"
    assert body["exception_status"] == "Open"
    assert "executed successfully" in body["message"]


def test_execute_missing_action_returns_404(
    api_client,
):
    """
    ActionNotFoundError specificity: the subtype handler must
    answer 404 even though the base RecoveryWorkflowError
    handler (409) is also registered.
    """

    client, _ = api_client

    response = client.post(
        "/recovery-actions/ACT-999999/execute",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Action ACT-999999 not found."
    )


def test_execute_closed_exception_maps_failure_outcome_to_409(
    api_client,
):
    """
    A structured success False outcome from the service is an
    intentional HTTP 409 whose detail is exactly the outcome
    message — mapped via the success field, never by
    inspecting message strings. The base RecoveryWorkflowError
    handler delivers the 409.
    """

    client, connection = api_client

    try:
        action = _generate_options_and_action(connection)

        services.approve_recovery(
            connection,
            action["action_id"],
            "API Test",
        )

        connection.execute(
            """
            UPDATE exceptions
            SET resolution_status = 'Resolved'
            WHERE exception_id = 'EXC-900002'
            """
        )
        connection.commit()
    finally:
        connection.close()

    response = client.post(
        f"/recovery-actions/{action['action_id']}/execute",
    )

    assert response.status_code == 409

    detail = response.json()["detail"]

    assert detail.startswith("Recovery execution failed:")
    assert "already Resolved" in detail
