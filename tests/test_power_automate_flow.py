"""
Closed-loop integration contract for the Power Automate
first slice (Checkpoint I).

This module exercises exactly the sequence the external
Power Automate flow performs — through the public HTTP
boundary only, using the same endpoints, headers and
payloads the real flow uses. It is the executable
specification of the integration:

    poll inbox
      -> select one actionable exception
      -> fetch the decision-engine review
      -> human decision (approve / reject)
      -> mutation through the protected endpoint
      -> execute when approved
      -> read Adensa's current state back
      -> build the outcome notification payload

Adensa remains the source of truth: every step reads or
validates Adensa's returned state. No business rule is
duplicated here beyond selecting which exception to present
and reporting the state Adensa itself reports.

All tests run on the temporary database fixtures; the
development database is never touched.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.generate_recovery_options import generate_recovery_options
from app.workflow_engine import generate_workflow_actions

# Synthetic test credential: never a real secret, never
# committed as configuration. It exists only inside the
# test session.
FLOW_API_KEY = "flow-test-key-not-a-secret"


@pytest.fixture()
def flow_client(seeded_database, monkeypatch):
    """
    A TestClient authenticated exactly as the Power
    Automate flow authenticates: X-API-Key on every
    operational request.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        FLOW_API_KEY,
    )

    with TestClient(app) as client:
        client.headers.update({"X-API-Key": FLOW_API_KEY})
        yield client, seeded_database


def _arrival_and_actions(connection):
    """
    Simulate operational data arriving and the pipeline
    producing recommendations: the real generators run, the
    way the incremental pipeline does.
    """

    generate_recovery_options(connection)
    generate_workflow_actions(connection)


def _poll_inbox(client):
    """GET /exceptions — the flow's polling step."""

    response = client.get("/exceptions")

    assert response.status_code == 200

    return response.json()


def _select_actionable_exception(rows):
    """
    The flow's selection rule: the first open exception
    that has at least one feasible recovery option.
    """

    for row in rows:

        if row["feasible_option_count"] > 0:
            return row

    return None


def _latest_action(client, exception_id):
    """GET /exceptions/{id}/actions/latest — the flow's state re-read."""

    response = client.get(
        f"/exceptions/{exception_id}/actions/latest"
    )

    assert response.status_code == 200

    return response.json()


# ==================================================
# THE CLOSED LOOP — APPROVAL PATH
# ==================================================

def test_closed_loop_approval_execution_outcome(flow_client):
    """
    The complete first-slice journey: poll, select, review,
    approve, execute, read back, notify — with the outcome
    notification reflecting Adensa's actual state.
    """

    client, connection = flow_client

    _arrival_and_actions(connection)

    # --------------------------------------------------
    # 1-2. POLL AND SELECT
    # --------------------------------------------------

    rows = _poll_inbox(client)
    selected = _select_actionable_exception(rows)

    assert selected is not None
    assert selected["exception_id"] == "EXC-900002"
    assert selected["severity"] == "High"
    assert selected["shipment_id"] == "SHP-900002"

    exception_id = selected["exception_id"]

    # --------------------------------------------------
    # 3. REVIEW — sufficient for a human decision
    # --------------------------------------------------

    review = client.get(
        f"/exceptions/{exception_id}/review"
    ).json()

    recommendation = review["recommendation"]

    assert recommendation is not None
    assert recommendation["option_id"]
    assert recommendation["transport_mode"]
    assert recommendation["estimated_cost"] > 0
    assert recommendation["decision_score"] > 0
    assert recommendation["confidence"] in (
        "High",
        "Medium",
        "Low",
    )
    assert recommendation["reason"]

    assert len(review["alternatives"]) == 2

    # --------------------------------------------------
    # 4-5. HUMAN DECISION REACHES ADENSA
    # --------------------------------------------------

    approval = client.post(
        f"/exceptions/{exception_id}/approve",
        json={"approved_by": "Flow Planner"},
    )

    assert approval.status_code == 200

    approval_outcome = approval.json()

    assert approval_outcome["success"] is True
    assert approval_outcome["action_id"]

    action_id = approval_outcome["action_id"]

    # --------------------------------------------------
    # 6. ADENSA VALIDATED THE TRANSITION
    # --------------------------------------------------

    action = _latest_action(client, exception_id)

    assert action["status"] == "Approved"
    assert action["approved_by"] == "Flow Planner"
    assert action["approved_at"]

    # --------------------------------------------------
    # 7. EXECUTE THE APPROVED ACTION
    # --------------------------------------------------

    execution = client.post(
        f"/recovery-actions/{action_id}/execute"
    )

    assert execution.status_code == 200

    execution_outcome = execution.json()

    assert execution_outcome["success"] is True
    assert execution_outcome["exception_status"] in (
        "Resolved",
        "Open",
    )

    # --------------------------------------------------
    # 8. READ ADENSA'S CURRENT STATE BACK
    # --------------------------------------------------

    action = _latest_action(client, exception_id)

    assert action["status"] == "Executed"
    assert action["executed_at"]

    rows_after = _poll_inbox(client)
    ids_after = {row["exception_id"] for row in rows_after}

    # --------------------------------------------------
    # 9. OUTCOME NOTIFICATION FROM ACTUAL STATE
    #
    # The fixture scenario leaves the shipment one day past
    # its required delivery: executed but STILL OPEN. The
    # notification must say so — never "Resolved".
    # --------------------------------------------------

    if execution_outcome["exception_status"] == "Open":

        assert exception_id in ids_after

        notification = {
            "exception_id": exception_id,
            "decision": "Approved by Flow Planner",
            "outcome": "Executed — Still Open",
            "detail": (
                f"{action_id} executed "
                f"({approval_outcome['previous_mode']} -> "
                f"{execution_outcome['new_mode']}); "
                "new ETA still misses the required "
                "delivery date. Exception remains open "
                "and monitored."
            ),
            "new_eta": execution_outcome["new_eta"],
        }

        assert notification["outcome"] != (
            "Executed — Resolved"
        )

    else:

        assert exception_id not in ids_after

        notification = {
            "exception_id": exception_id,
            "decision": "Approved by Flow Planner",
            "outcome": "Executed — Resolved",
            "detail": (
                f"{action_id} executed; shipment now "
                "meets the required delivery date."
            ),
            "new_eta": execution_outcome["new_eta"],
        }

    assert notification["outcome"].startswith("Executed")


# ==================================================
# THE CLOSED LOOP — REJECTION PATH
# ==================================================

def test_closed_loop_rejection_does_not_execute(flow_client):
    """
    A rejected recommendation must never execute: the flow
    reads the rejected state and reports it without
    performing any execution mutation.
    """

    client, connection = flow_client

    _arrival_and_actions(connection)

    rows = _poll_inbox(client)
    selected = _select_actionable_exception(rows)
    exception_id = selected["exception_id"]

    review = client.get(
        f"/exceptions/{exception_id}/review"
    ).json()

    assert review["recommendation"] is not None

    rejection = client.post(
        f"/exceptions/{exception_id}/reject",
        json={"rejected_by": "Flow Planner"},
    )

    assert rejection.status_code == 200
    assert rejection.json()["success"] is True

    # The flow only executes approved actions; the read-back
    # proves the rejection is the recorded state.
    action = _latest_action(client, exception_id)

    assert action["status"] == "Rejected"
    assert action["approved_by"] == "Flow Planner"
    assert action["executed_at"] is None

    notification = {
        "exception_id": exception_id,
        "decision": "Rejected by Flow Planner",
        "outcome": "Rejected — no execution performed",
        "detail": (
            "The recommendation was not accepted; the "
            "exception remains open for manual handling."
        ),
    }

    assert notification["outcome"].startswith("Rejected")

    # The exception is still open and pollable for follow-up
    # (manual intervention path).
    rows_after = _poll_inbox(client)
    ids_after = {row["exception_id"] for row in rows_after}

    assert exception_id in ids_after


# ==================================================
# TIMEOUT / RETRY / DUPLICATE PROTECTION
# ==================================================

def test_timeout_recheck_does_not_duplicate_decision(flow_client):
    """
    A mutation response lost to a timeout must never lead
    to a blind repeat: the flow re-reads Adensa's state and
    only mutates when the state proves it is still required.
    Adensa's guards additionally reject any blind repeat.
    """

    client, connection = flow_client

    _arrival_and_actions(connection)

    rows = _poll_inbox(client)
    selected = _select_actionable_exception(rows)
    exception_id = selected["exception_id"]

    # First approval succeeds — but suppose Power Automate
    # never receives the response.
    approval = client.post(
        f"/exceptions/{exception_id}/approve",
        json={"approved_by": "Flow Planner"},
    )

    assert approval.status_code == 200

    # Timeout recovery: re-read state first.
    action = _latest_action(client, exception_id)

    # The state proves the decision is already recorded, so
    # the flow must NOT re-send the approval.
    if action["status"] == "Approved":
        re_approval = client.post(
            f"/exceptions/{exception_id}/approve",
            json={"approved_by": "Flow Planner"},
        )

        # Adensa's authoritative guard rejects the blind
        # repeat with the domain conflict — no duplicate
        # business action exists.
        assert re_approval.status_code == 409

    # The action proceeds to execution exactly once.
    action_id = action["action_id"]

    execution = client.post(
        f"/recovery-actions/{action_id}/execute"
    )

    assert execution.status_code == 200

    # A repeated execute request (another simulated timeout
    # retry) is rejected by the same state validation.
    re_execution = client.post(
        f"/recovery-actions/{action_id}/execute"
    )

    assert re_execution.status_code == 409

    # Exactly one execution is recorded.
    action = _latest_action(client, exception_id)

    assert action["status"] == "Executed"


def test_concurrent_conflicting_decision_is_authoritative(
    flow_client,
):
    """
    If two humans decide against each other, Adensa's state
    validation decides: the first transition wins, the
    conflicting one is refused, and the recorded actor is
    the first decision's actor.
    """

    client, connection = flow_client

    _arrival_and_actions(connection)

    rows = _poll_inbox(client)
    selected = _select_actionable_exception(rows)
    exception_id = selected["exception_id"]

    first = client.post(
        f"/exceptions/{exception_id}/approve",
        json={"approved_by": "Planner One"},
    )

    assert first.status_code == 200

    conflict = client.post(
        f"/exceptions/{exception_id}/reject",
        json={"rejected_by": "Planner Two"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]

    action = _latest_action(client, exception_id)

    assert action["status"] == "Approved"
    assert action["approved_by"] == "Planner One"


# ==================================================
# SECURITY BOUNDARY OF THE FLOW
# ==================================================

def test_flow_endpoints_reject_unauthenticated_requests(
    seeded_database,
    monkeypatch,
):
    """
    Every endpoint the flow uses refuses keyless requests:
    a misconfigured flow can neither read operational data
    nor mutate state.
    """

    monkeypatch.setattr(
        "app.api.ADENSA_API_KEY",
        FLOW_API_KEY,
    )

    with TestClient(app) as client:

        protected = [
            ("GET", "/exceptions"),
            ("GET", "/exceptions/EXC-900002/review"),
            ("GET", "/exceptions/EXC-900002/actions/latest"),
            (
                "POST",
                "/exceptions/EXC-900002/approve",
                {"approved_by": "Flow Planner"},
            ),
            (
                "POST",
                "/exceptions/EXC-900002/reject",
                {"rejected_by": "Flow Planner"},
            ),
            (
                "POST",
                "/recovery-actions/ACT-000001/execute",
                None,
            ),
        ]

        for entry in protected:

            method, path = entry[0], entry[1]
            body = entry[2] if len(entry) > 2 else None

            response = (
                client.post(path, json=body)
                if method == "POST"
                else client.get(path)
            )

            assert response.status_code == 401, path

        # The flow's precondition probe stays public.
        assert client.get("/health").status_code == 200


def test_flow_precondition_health_is_public():
    """
    The flow's liveness precondition works without a key so
    an unconfigured-key outage is distinguishable from the
    service being down.
    """

    with TestClient(app) as client:

        assert client.get("/health").json() == {"status": "ok"}
