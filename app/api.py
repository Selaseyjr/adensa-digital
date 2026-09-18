"""
HTTP boundary for the Adensa Digital application services.

This module is a thin FastAPI client of app.services — the
third consumer of the same application layer alongside the
Streamlit UI (app/main.py) and the terminal CLI (app/cli.py):

    Streamlit UI ──────┐
                       ├─→ services → engines → repositories → SQLite
    FastAPI (app/api) ─┘
    CLI (app/cli) ─────┘

Rules kept by this boundary:

- No business logic and no SQL: every route delegates to one
  existing service function and returns its structure.
- Request-scoped connections through a FastAPI dependency that
  closes the connection after each request. Transactions stay
  owned by the engines exactly as in every other client.
- Domain failures surface as RecoveryWorkflowError, mapped to
  HTTP 409 with the existing engine message. Unexpected errors
  remain generic 500 responses without internal details.
- The read endpoints return the existing service structures
  verbatim (sqlite3.Row values converted to dicts); Pydantic
  models are used only where they add a meaningful contract
  (/health, /metrics).
"""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import services
from app.database import get_connection
from app.errors import (
    ActionNotFoundError,
    InvalidTransitionError,
    RecoveryWorkflowError,
)


app = FastAPI(title="Adensa Digital API")


# ==================================================
# REQUEST-SCOPED CONNECTION
# ==================================================

def get_db():
    connection = get_connection()

    try:
        yield connection

    finally:
        connection.close()


# ==================================================
# RESPONSE MODELS
# ==================================================

class HealthResponse(BaseModel):
    status: str


class MetricsResponse(BaseModel):
    open_exceptions: int
    critical_exceptions: int
    pending_approvals: int


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1)


class RejectRequest(BaseModel):
    rejected_by: str = Field(min_length=1)


# ==================================================
# ERROR MAPPING
# ==================================================

@app.exception_handler(RecoveryWorkflowError)
def recovery_workflow_error_handler(request, exc):
    """
    Map recovery-workflow business-rule violations to
    HTTP 409, passing the existing engine message through.
    """

    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)},
    )


@app.exception_handler(ActionNotFoundError)
def action_not_found_error_handler(request, exc):
    """
    The addressed recovery action does not exist: HTTP 404.
    Registered before the base-class handler above; FastAPI
    dispatches to the most specific handler.
    """

    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )


@app.exception_handler(InvalidTransitionError)
def invalid_transition_error_handler(request, exc):
    """
    The requested workflow transition is not permitted:
    HTTP 409 with the existing engine message.
    """

    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)},
    )


# ==================================================
# ROUTES
# ==================================================

@app.get(
    "/health",
    response_model=HealthResponse,
)
def read_health():
    """Application liveness."""

    return HealthResponse(status="ok")


@app.get(
    "/metrics",
    response_model=MetricsResponse,
)
def read_metrics(
    connection=Depends(get_db),
):
    """Dashboard KPI counts."""

    return services.get_dashboard_metrics(connection)


@app.get("/exceptions")
def list_exceptions(
    connection=Depends(get_db),
):
    """Open-exception inbox with shipment and order context."""

    rows = services.get_exception_inbox(connection)

    return [dict(row) for row in rows]


@app.get("/exceptions/{exception_id}/review")
def read_exception_review(
    exception_id: str,
    connection=Depends(get_db),
):
    """
    Decision-engine review for an exception. A missing
    exception yields 404 (the service returns None).
    """

    result = services.get_exception_review(
        connection,
        exception_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Exception {exception_id} not found."
            ),
        )

    return result


@app.get("/exceptions/{exception_id}/actions/latest")
def read_latest_action(
    exception_id: str,
    connection=Depends(get_db),
):
    """
    Most recent recovery action for an exception, or a null
    body when no action exists.
    """

    action = services.get_latest_action(
        connection,
        exception_id,
    )

    return dict(action) if action is not None else None


# ==================================================
# MUTATIONS
# ==================================================

def _resolve_latest_action_or_404(
    connection,
    exception_id,
):
    """
    Resolve the exception-keyed action for the mutation
    endpoints, mirroring the UI's action resolution: no
    action means the addressed resource does not exist.
    """

    action = services.get_latest_action(
        connection,
        exception_id,
    )

    if action is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No recovery action exists for "
                f"exception {exception_id}."
            ),
        )

    return action


@app.post(
    "/exceptions/{exception_id}/approve",
)
def approve_exception(
    exception_id: str,
    request: ApproveRequest,
    connection=Depends(get_db),
):
    """
    Approve the latest recovery action of an exception.
    """

    action = _resolve_latest_action_or_404(
        connection,
        exception_id,
    )

    outcome = services.approve_recovery(
        connection,
        action["action_id"],
        request.approved_by,
    )

    return outcome


@app.post(
    "/exceptions/{exception_id}/reject",
)
def reject_exception(
    exception_id: str,
    request: RejectRequest,
    connection=Depends(get_db),
):
    """
    Reject the latest recovery action of an exception.
    """

    action = _resolve_latest_action_or_404(
        connection,
        exception_id,
    )

    outcome = services.reject_recovery(
        connection,
        action["action_id"],
        request.rejected_by,
    )

    return outcome


@app.post(
    "/recovery-actions/{action_id}/execute",
)
def execute_recovery_action_endpoint(
    action_id: str,
    connection=Depends(get_db),
):
    """
    Execute an approved recovery action. A structured
    domain failure (success False) is returned as HTTP 409
    with the outcome message.
    """

    outcome = services.execute_approved_recovery(
        connection,
        action_id,
    )

    if outcome["success"] is False:
        raise HTTPException(
            status_code=409,
            detail=outcome["message"],
        )

    return outcome
