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

Mutation endpoints require a prototype API key: the
api_client fixture provisions a throwaway test key on the
api module and sends it as X-API-Key on every request, so
the existing contract tests exercise the authorized path
unchanged. Dedicated authentication tests cover the
unauthenticated paths. The key is synthetic, exists only
for the duration of each test and is committed nowhere.
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

# Synthetic test credential: never a real secret, never
# committed as configuration. It exists only inside the
# test session.
TEST_API_KEY = "test-api-key-not-a-secret"


@pytest.fixture()
def api_client(seeded_database, monkeypatch):
    """
    Provide a TestClient served against the seeded temporary
    database, alongside the fixture connection for arranging
    test state.

    The fixture provisions the throwaway test key on the api
    module (the name the dependency reads) and sends it as
    X-API-Key on every request, so the existing contract
    tests exercise the authorized path of the mutation
    endpoints unchanged.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        TEST_API_KEY,
    )

    with TestClient(app) as client:
        client.headers.update({"X-API-Key": TEST_API_KEY})
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


# ==================================================
# AUTHENTICATION (PROTOTYPE API KEY)
# ==================================================
#
# Every operational endpoint — mutations and reads alike —
# is guarded by the shared X-API-Key dependency; only
# /health stays public. These tests verify the documented
# security contract: missing or wrong keys are rejected
# before any domain logic runs, an unconfigured key fails
# closed, and failed authentication never mutates state.

MUTATION_REQUESTS = [
    (
        "approve",
        "/exceptions/EXC-900002/approve",
        {"approved_by": "Auth Test"},
    ),
    (
        "reject",
        "/exceptions/EXC-900002/reject",
        {"rejected_by": "Auth Test"},
    ),
    (
        "execute",
        "/recovery-actions/ACT-DOES-NOT-EXIST/execute",
        None,
    ),
]


@pytest.fixture()
def unauthenticated_client(seeded_database, monkeypatch):
    """
    A client whose server has a key configured but whose
    requests carry no API key.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        TEST_API_KEY,
    )

    with TestClient(app) as client:

        yield client


@pytest.fixture()
def misconfigured_client(seeded_database, monkeypatch):
    """
    A client whose server has NO key configured: the
    fail-closed scenario.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        None,
    )

    with TestClient(app) as client:

        yield client


def test_mutations_reject_missing_api_key(unauthenticated_client):
    """
    Every mutation endpoint rejects a request without an
    API key with a clean 401, before any domain logic.
    """

    client = unauthenticated_client

    for name, path, body in MUTATION_REQUESTS:

        response = (
            client.post(path, json=body)
            if body is not None
            else client.post(path)
        )

        assert response.status_code == 401, name
        assert response.json() == {"detail": "Missing API key."}


def test_mutations_reject_incorrect_api_key(seeded_database, monkeypatch):
    """
    A wrong key is rejected with a generic 401 that leaks
    neither the configured key nor the config state.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        TEST_API_KEY,
    )

    with TestClient(app) as client:

        client.headers.update({"X-API-Key": "definitely-wrong"})

        for name, path, body in MUTATION_REQUESTS:

            response = (
                client.post(path, json=body)
                if body is not None
                else client.post(path)
            )

            assert response.status_code == 401, name
            assert response.json() == {"detail": "Invalid API key."}


def test_unconfigured_api_key_fails_closed(misconfigured_client):
    """
    With no key configured the whole operational surface —
    mutations and reads alike — is closed (503) whether or
    not a key is supplied: an operator who has not
    provisioned a key never gets silent open access. Only
    /health remains public (covered separately).
    """

    client = misconfigured_client

    for name, path, body in MUTATION_REQUESTS:

        unauthenticated = (
            client.post(path, json=body)
            if body is not None
            else client.post(path)
        )

        assert unauthenticated.status_code == 503, name

        client.headers.update({"X-API-Key": "some-key"})

        authenticated = (
            client.post(path, json=body)
            if body is not None
            else client.post(path)
        )

        assert authenticated.status_code == 503, name

    for name in READ_ENDPOINTS:

        unauthenticated = client.get(name)

        assert unauthenticated.status_code == 503, name

        client.headers.update({"X-API-Key": "some-key"})

        authenticated = client.get(name)

        assert authenticated.status_code == 503, name


READ_ENDPOINTS = [
    "/metrics",
    "/exceptions",
    "/exceptions/EXC-900002/review",
    "/exceptions/EXC-900002/actions/latest",
]


def test_health_remains_public_without_key(misconfigured_client):
    """
    The documented policy: /health is a liveness probe
    carrying no operational data and stays accessible
    without a key — even with authentication unconfigured.
    """

    assert misconfigured_client.get("/health").status_code == 200


def test_operational_reads_reject_missing_api_key(
    unauthenticated_client,
):
    """
    Every operational read endpoint rejects a keyless
    request with a clean 401, before any domain logic.
    """

    client = unauthenticated_client

    for name in READ_ENDPOINTS:

        response = client.get(name)

        assert response.status_code == 401, name
        assert response.json() == {
            "detail": "Missing API key."
        }, name


def test_operational_reads_reject_incorrect_api_key(
    seeded_database,
    monkeypatch,
):
    """
    A wrong key is rejected on every operational read with
    a generic 401 that leaks neither the configured key nor
    the config state.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        TEST_API_KEY,
    )

    with TestClient(app) as client:

        client.headers.update({"X-API-Key": "definitely-wrong"})

        for name in READ_ENDPOINTS:

            response = client.get(name)

            assert response.status_code == 401, name
            assert response.json() == {
                "detail": "Invalid API key."
            }, name


def test_operational_reads_succeed_with_correct_key(
    seeded_database,
    monkeypatch,
):
    """
    With the correct key every operational read returns its
    existing service contract.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        TEST_API_KEY,
    )

    with TestClient(app) as client:

        client.headers.update({"X-API-Key": TEST_API_KEY})

        metrics = client.get("/metrics").json()
        assert metrics == {
            "open_exceptions": 2,
            "critical_exceptions": 0,
            "pending_approvals": 0,
        }

        exceptions = client.get("/exceptions").json()
        assert isinstance(exceptions, list)
        assert len(exceptions) == 2

        review = client.get(
            "/exceptions/EXC-900002/review"
        ).json()
        assert "recommendation" in review

        latest_action = client.get(
            "/exceptions/EXC-900002/actions/latest"
        )
        assert latest_action.status_code == 200
        assert latest_action.json() is None


def test_authentication_failure_does_not_mutate_database(api_client):
    """
    Rejected requests must leave no trace: the action stays
    Pending Approval, counts are unchanged, and the
    authorized path still works afterwards.
    """

    client, connection = api_client

    _generate_options_and_action(connection)

    before_actions = connection.execute(
        "SELECT COUNT(*) FROM recovery_actions"
    ).fetchone()[0]

    # The api_client sends the correct key; strip it to
    # simulate the unauthenticated attempts — mutations and
    # reads alike.
    saved_key = client.headers.pop("X-API-Key")

    try:

        for _, path, body in MUTATION_REQUESTS:

            response = (
                client.post(path, json=body)
                if body is not None
                else client.post(path)
            )

            assert response.status_code == 401

        for name in READ_ENDPOINTS:

            assert client.get(name).status_code == 401

    finally:

        client.headers.update({"X-API-Key": saved_key})

    after_actions = connection.execute(
        "SELECT COUNT(*) FROM recovery_actions"
    ).fetchone()[0]

    action = connection.execute(
        """
        SELECT status
        FROM recovery_actions
        WHERE exception_id = 'EXC-900002'
        """
    ).fetchone()

    assert after_actions == before_actions
    assert action["status"] == "Pending Approval"

    # The authorized path is unaffected by the rejected
    # attempts.
    response = client.post(
        "/exceptions/EXC-900002/approve",
        json={"approved_by": "Auth Test"},
    )

    assert response.status_code == 200


def test_authentication_precedes_domain_error_mapping(
    seeded_database,
    monkeypatch,
):
    """
    A wrong key yields 401 even for a nonexistent action or
    exception: authentication sits in front of routing and
    domain validation, while correctly authenticated
    requests keep the existing 404/409 error mapping.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        TEST_API_KEY,
    )

    with TestClient(app) as client:

        client.headers.update({"X-API-Key": "definitely-wrong"})

        response = client.post(
            "/recovery-actions/ACT-DOES-NOT-EXIST/execute",
        )

        assert response.status_code == 401

        response = client.get(
            "/exceptions/EXC-DOES-NOT-EXIST/review",
        )

        assert response.status_code == 401
