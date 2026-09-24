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
- API-key authentication (X-API-Key header, sourced from
  configuration) guards every operational endpoint: all
  three mutations and all operational reads. Only /health —
  a liveness probe carrying no operational data — stays
  public. The key is never logged and never appears in
  error responses.
"""

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from app import services
from app.config import ADENSA_API_KEY, ADENSA_CORS_ORIGINS, get_database_config
from app.database import get_connection
from app.migrations import CURRENT_VERSION, get_schema_version
from app.errors import (
    ActionNotFoundError,
    InvalidTransitionError,
    RecoveryWorkflowError,
)


logger = logging.getLogger(__name__)


# ==================================================
# STARTUP VERIFICATION (lifespan)
# ==================================================


def verify_database_startup() -> None:
    """
    Verify the configured database is reachable and its schema
    is at the current migration version.

    Deployment model (ADR-012): migrations are applied by the
    bootstrap/CLI path before the API starts — this check only
    verifies; it never migrates. Failures raise so the server
    fails fast instead of serving requests against a database
    it cannot use.

    Log lines carry the redacted backend description only —
    never credentials or connection strings.
    """

    description = get_database_config().safe_description()

    try:
        connection = get_connection()
    except Exception:
        logger.error(
            "Startup verification failed: database unreachable (%s)",
            description,
        )
        raise

    try:
        if get_schema_version(connection) < CURRENT_VERSION:
            raise RuntimeError(
                "Database schema is outdated: apply migrations "
                "before starting the API."
            )
    except RuntimeError:
        logger.error(
            "Startup verification failed: %s", description
        )
        raise
    except Exception:
        logger.error(
            "Startup verification failed: schema version could "
            "not be read (%s)",
            description,
        )
        raise
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify the database contract before serving requests."""

    verify_database_startup()

    logger.info(
        "Startup verification passed: %s",
        get_database_config().safe_description(),
    )

    yield


app = FastAPI(title="Adensa Digital API", lifespan=lifespan)


# ==================================================
# CORS (browser origins for the versioned application API)
# ==================================================

# Machine-to-machine callers (Power Automate, the CLI) are
# unaffected by CORS — it only constrains browsers. Origins
# are configured exclusively through the environment
# (ADENSA_CORS_ORIGINS); with nothing configured no browser
# origin is trusted, and the wildcard is deliberately never
# used because the API carries operational data.

if ADENSA_CORS_ORIGINS:

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ADENSA_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key"],
    )


# ==================================================
# API-KEY AUTHENTICATION (prototype boundary security)
# ==================================================

# Standard header-based key mechanism. The key itself lives
# only in configuration/environment: it is never hard-coded,
# never returned in any response and never logged.

_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Prototype API key for mutation endpoints.",
)


def require_api_key(
    supplied_key: str = Depends(_api_key_header),
):
    """
    Guard the mutation endpoints.

    - a missing header -> 401;
    - a wrong key -> 401 (constant-time comparison, generic
      message: neither the configured key nor the config
      state is leaked);
    - an unconfigured key -> 503 fail-closed: an operator who
      has not provisioned a key gets an explicit signal,
      never silent unauthenticated mutation access.
    """

    if ADENSA_API_KEY is None:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Mutation API is not configured for "
                "external access."
            ),
        )

    if supplied_key is None:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
        )

    if not secrets.compare_digest(
        supplied_key,
        ADENSA_API_KEY,
    ):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return supplied_key


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


# --------------------------------------------------
# /v1 APPLICATION-BOUNDARY CONTRACTS (ADR-011)
#
# Explicit schemas for the operational reads the future
# web client consumes. Every model mirrors the existing
# service output — the API does not invent a new domain
# model, it makes the current one visible and checkable.
# --------------------------------------------------

class ReadyResponse(BaseModel):
    status: str
    database: str


class InboxRow(BaseModel):
    """One open exception in the operational work queue."""

    exception_id: str
    shipment_id: str
    exception_type: str
    severity: str
    # The detection engine writes a descriptive operational
    # sentence ("Estimated delivery delay of N day(s). Customer
    # delivery commitment at risk.") — the model mirrors that
    # actual domain output.
    estimated_impact: str
    resolution_status: str
    transport_mode: str
    current_location: str
    estimated_arrival: str | None
    priority: str
    required_delivery_date: str
    feasible_option_count: int
    executed_still_open: int


class ControlTowerRecentlyResolved(BaseModel):
    exception_id: str
    exception_type: str
    severity: str
    resolution_status: str
    resolved_at: str | None
    resolution_path: str


class ControlTowerFollowUpEntry(BaseModel):
    exception_id: str
    severity: str
    exception_type: str
    detected_at: str
    action_id: str | None
    executed_at: str | None
    estimated_arrival: str | None
    required_delivery_date: str
    actionable: bool
    reason: str


class ControlTowerSummary(BaseModel):
    """The control-tower projection: bounded-queue and full-population metrics with their distinct populations."""

    open_exceptions: int
    actionable_exceptions: int
    monitoring_exceptions: int
    pending_approvals: int
    awaiting_execution: int
    critical_exceptions: int
    follow_up_required: int
    follow_up_queue: list[ControlTowerFollowUpEntry]
    recently_resolved: list[ControlTowerRecentlyResolved]


# --------------------------------------------------
# ANALYTICS CONTRACTS (ADR-014)
#
# Read-only analytical projections for the control-tower
# visualization layer. Every dataset carries its analytical
# basis as contract metadata: the frontend labels each
# series truthfully ("Delivered shipments by planned-arrival
# month", "Exceptions by shipment departure month") instead
# of hiding the assumptions in component copy.
# --------------------------------------------------

class AnalyticsServicePerformancePoint(BaseModel):
    """One month of delivered-shipment on-time performance."""

    month: str
    delivered: int
    on_time: int
    on_time_rate: float | None


class AnalyticsIncidencePoint(BaseModel):
    """One departure month's exception incidence (not detection time)."""

    month: str
    departing: int
    exceptions: int
    incidence_rate: float | None


class AnalyticsVolumePoint(BaseModel):
    """One month's recorded shipment volume."""

    month: str
    shipments: int


class AnalyticsServicePerformanceSeries(BaseModel):
    """On-time delivery by planned-arrival month plus its analytical basis."""

    basis: str
    points: list[AnalyticsServicePerformancePoint]


class AnalyticsIncidenceSeries(BaseModel):
    """Departure-month exception incidence plus its analytical basis."""

    basis: str
    points: list[AnalyticsIncidencePoint]


class AnalyticsVolumeSeries(BaseModel):
    """Shipment volume by planned-departure month plus its analytical basis."""

    basis: str
    points: list[AnalyticsVolumePoint]


class AnalyticsTransportEntry(BaseModel):
    """One transport mode's delivered population and on-time share."""

    transport_mode: str
    delivered: int
    on_time: int
    on_time_rate: float | None


class AnalyticsCarrierEntry(BaseModel):
    """One carrier's delivered population and on-time share."""

    carrier_id: str
    carrier_name: str
    delivered: int
    on_time: int
    on_time_rate: float | None


class AnalyticsWarehouseEntry(BaseModel):
    """One warehouse's recorded exception count."""

    warehouse_id: str
    warehouse_name: str
    exceptions: int


class AnalyticsSeverityEntry(BaseModel):
    """One severity class's open-exception count (workflow snapshot)."""

    severity: str
    exceptions: int


class AnalyticsCategoricalSeries(BaseModel):
    """A categorical breakdown plus its truthful analytical basis."""

    basis: str
    entries: list[
        AnalyticsTransportEntry
        | AnalyticsCarrierEntry
        | AnalyticsWarehouseEntry
        | AnalyticsSeverityEntry
    ]


class AnalyticsOverview(BaseModel):
    """The analytical overview: seven honest datasets, no invented history."""

    service_performance: AnalyticsServicePerformanceSeries
    exception_incidence: AnalyticsIncidenceSeries
    shipment_volume: AnalyticsVolumeSeries
    transport: AnalyticsCategoricalSeries
    carriers: AnalyticsCategoricalSeries
    warehouses: AnalyticsCategoricalSeries
    severity: AnalyticsCategoricalSeries


class ManualInterventionRecord(BaseModel):
    intervention_id: str
    exception_id: str
    intervention_type: str
    external_party: str
    resolution_summary: str
    new_expected_delivery: str | None
    outcome: str
    notes: str | None
    recorded_by: str
    recorded_at: str


class HistoryEntry(BaseModel):
    """One reconstructed operational-history event (timestamp is None for steps the schema never dates)."""

    timestamp: str | None
    event: str
    detail: str
    actor: str
    sequence: int


class ExceptionContext(BaseModel):
    """The investigation context for one exception (Situation & Impact surface)."""

    exception_id: str
    shipment_id: str
    order_id: str
    customer_id: str
    customer_name: str
    exception_type: str
    severity: str
    status: str
    description: str
    priority: str
    origin: str
    destination: str
    route: str
    transport_mode: str
    carrier_id: str
    shipment_status: str
    planned_departure: str
    estimated_arrival: str | None
    required_delivery_date: str


class InvestigationState(BaseModel):
    """The persisted-evidence classification of an investigated exception."""

    state: str
    follow_up_required: bool
    reason: str


class ScoredOption(BaseModel):
    """A scored recovery option exactly as the decision engine produced it."""

    option_id: str
    transport_mode: str
    carrier_id: str
    estimated_cost: float
    estimated_transit_days: float
    risk_score: float
    cost_score: float
    transit_score: float
    risk_component: float
    priority_score: float
    cost_contribution: float
    transit_contribution: float
    risk_contribution: float
    priority_contribution: float
    decision_score: float
    confidence: str | None = None
    reason: str | None = None


class FactorValue(BaseModel):
    option_id: str
    transport_mode: str
    score: float
    contribution: float


class RationaleFactor(BaseModel):
    factor: str
    weight: float
    values: list[FactorValue]


class RationaleTradeOff(BaseModel):
    option_id: str
    transport_mode: str
    stronger_factors: list[str]


class RecommendationRationale(BaseModel):
    """The decision rationale: policy weights, per-factor breakdown, trade-offs, confidence basis."""

    weights: dict[str, float]
    factor_breakdown: list[RationaleFactor]
    trade_offs: list[RationaleTradeOff]
    confidence_basis: str


class EvaluatedOption(BaseModel):
    """An evaluated recovery option when no feasible recommendation exists."""

    option_id: str
    transport_mode: str
    carrier_id: str
    estimated_cost: float
    estimated_transit_days: float
    risk_score: float
    feasible: bool


class RecoveryAssessment(BaseModel):
    """The recovery assessment: recommendation + alternatives + rationale, or the evaluated options explaining why there is none."""

    recommendation: ScoredOption | None
    alternatives: list[ScoredOption]
    evaluated_options: list[EvaluatedOption]
    rationale: RecommendationRationale | None


class SustainabilityEstimate(BaseModel):
    """One option's estimated emissions, or an honest unavailable record."""

    transport_mode: str
    option_id: str | None
    status: str
    reason: str | None = None
    shipment_weight_kg: float | None = None
    shipment_weight_tonnes: float | None = None
    distance_km: float | None = None
    emissions_factor: float | None = None
    estimated_co2e_kg: float | None = None
    unit: str | None = None
    methodology: str | None = None
    data_quality_note: str | None = None


class SustainabilityTradeOff(BaseModel):
    option_id: str
    transport_mode: str
    estimated_co2e_kg: float
    difference_kg: float
    relative_to_recommendation: str


class LowestEmissionOption(BaseModel):
    option_id: str
    transport_mode: str
    estimated_co2e_kg: float


class SustainabilityComparison(BaseModel):
    """Informational emissions comparison; never part of the recommendation."""

    status: str
    unit: str
    methodology: str
    data_quality_note: str
    estimates: list[SustainabilityEstimate]
    trade_offs: list[SustainabilityTradeOff]
    lowest_emission_option: LowestEmissionOption | None


class SustainabilityUnavailable(BaseModel):
    status: str
    reason: str


class DecisionBrief(BaseModel):
    """
    The advisory AI decision brief exactly as the ai_support
    contract produces it — never the operational authority.

    The available state carries the planner-facing brief; the
    structured unavailable state carries only `status` and
    `message`. Optional fields keep both states in one honest
    contract instead of inventing placeholder content.
    """

    status: str
    advisory_label: str | None = None
    situation_summary: str | None = None
    recommended_action: str | None = None
    rationale: str | None = None
    tradeoffs: str | None = None
    verification_points: list[str] | None = None
    disclaimer: str | None = None
    provider: str | None = None
    message: str | None = None


class LatestAction(BaseModel):
    """The most recent recovery action and its workflow state."""

    action_id: str
    option_id: str | None
    action_type: str
    status: str
    approved_by: str | None
    approved_at: str | None
    executed_at: str | None


class WorkflowOutcome(BaseModel):
    """A workflow mutation outcome (approve/reject/execute)."""

    success: bool
    message: str
    action_id: str | None = None
    shipment_id: str | None = None
    previous_mode: str | None = None
    new_mode: str | None = None
    carrier_id: str | None = None
    new_eta: str | None = None
    recovery_event: str | None = None
    required_delivery: str | None = None
    exception_status: str | None = None


class ManualResolutionRequest(BaseModel):
    """A planner-recorded manual resolution; free-text fields are validated by the service."""

    intervention_type: str
    external_party: str = Field(min_length=1)
    resolution_summary: str = Field(min_length=1)
    recorded_by: str = Field(min_length=1)
    outcome: str
    new_expected_delivery: str | None = None
    notes: str | None = None


class ManualResolutionOutcome(WorkflowOutcome):
    """The recorded manual-intervention outcome."""

    exception_id: str
    intervention_id: str
    intervention_type: str
    external_party: str
    resolution_summary: str
    new_expected_delivery: str | None
    outcome: str
    notes: str | None
    recorded_by: str
    recorded_at: str
    exception_status: str


class OperationalRefreshSummary(BaseModel):
    """What one operational-refresh run created."""

    new_exceptions: int
    new_options: int
    new_exception_ids: list[str]
    actions_evaluated: int
    new_actions: int
    actions_without_recommendation: int
    actions_skipped: int


class SimulatedArrivalSummary(BaseModel):
    """One controlled simulated shipment arrival."""

    shipment_id: str
    order_id: str
    carrier_id: str
    event_count: int
    required_delivery: str
    estimated_arrival: str
    delay_days: int


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


@app.exception_handler(Exception)
def unexpected_exception_handler(request: Request, exc: Exception):
    """
    Last-resort handler: an unexpected application exception
    must leave a server-side trace identifying where it
    happened, while the client keeps receiving FastAPI's
    generic 500 response (no internals, no stack details).

    Deliberately logged without the request body, headers or
    query string — those can carry credentials or operational
    payloads.
    """

    # exc_info is passed explicitly: the handler runs outside
    # the raising frame, so sys.exc_info() is empty here.
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
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
    "/ready",
    response_model=ReadyResponse,
)
def read_ready(
    connection=Depends(get_db),
):
    """
    Readiness: the application can open and use the
    configured database, and the schema is at the current
    migration version — an outdated schema fails readiness
    instead of surfacing as runtime errors (ADR-012).
    Deliberately minimal — a SELECT that touches no
    operational table and no internals in the response.
    """

    connection.execute("SELECT 1").fetchone()

    if get_schema_version(connection) < CURRENT_VERSION:
        return JSONResponse(
            status_code=503,
            content=ReadyResponse(
                status="degraded",
                database="schema-outdated",
            ).model_dump(),
        )

    return ReadyResponse(
        status="ready",
        database="ok",
    )


@app.get(
    "/metrics",
    response_model=MetricsResponse,
)
def read_metrics(
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """Dashboard KPI counts."""

    return services.get_dashboard_metrics(connection)


@app.get("/exceptions")
def list_exceptions(
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """Open-exception inbox with shipment and order context."""

    rows = services.get_exception_inbox(connection)

    return [dict(row) for row in rows]


@app.get("/exceptions/{exception_id}/review")
def read_exception_review(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
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
    _api_key: str = Depends(require_api_key),
):
    """
    Most recent recovery action for an exception, or a null
    body when no action exists.
    """

    action = services.get_latest_action(
        connection,
        exception_id,
    )

    return action


# ==================================================
# VERSIONED APPLICATION BOUNDARY (/v1, ADR-011)
#
# The application-facing capability surface for the future
# web client. Same service layer, same API-key guard, same
# error mapping as the machine-to-machine endpoints above;
# new paths so the existing integration contract is not
# silently reshaped.
# ==================================================

def _not_found(detail):

    raise HTTPException(status_code=404, detail=detail)


@app.get(
    "/v1/control-tower/summary",
    response_model=ControlTowerSummary,
)
def read_control_tower_summary(
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """Control-tower projection: bounded-queue and full-population metrics plus the follow-up and resolved queues."""

    return services.get_control_tower_summary(connection)


@app.get(
    "/v1/analytics/overview",
    response_model=AnalyticsOverview,
)
def read_analytics_overview(
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """
    Analytical overview for the control-tower visualization
    layer (ADR-014): read-only, server-computed aggregations
    with their analytical bases as contract metadata. The
    frontend never performs domain arithmetic and never
    invents a time axis.
    """

    return services.get_analytics_overview(connection)


@app.get(
    "/v1/exceptions/inbox",
    response_model=list[InboxRow],
)
def read_exception_inbox_v1(
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """The bounded operational work queue (actionable first, then newest detected)."""

    return services.get_exception_inbox(connection)


@app.get(
    "/v1/exceptions/{exception_id}/context",
    response_model=ExceptionContext,
)
def read_exception_context_v1(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """The investigation context for one exception (Situation & Impact)."""

    context = services.get_exception_context(
        connection,
        exception_id,
    )

    if context is None:

        _not_found(
            f"Exception {exception_id} not found."
        )

    return context


@app.get(
    "/v1/exceptions/{exception_id}/state",
    response_model=InvestigationState,
)
def read_investigation_state_v1(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """The persisted-evidence operational state of one exception."""

    state = services.classify_investigation_state(
        connection,
        exception_id,
    )

    if state is None:

        _not_found(
            f"Exception {exception_id} not found."
        )

    return state


@app.get(
    "/v1/exceptions/{exception_id}/history",
    response_model=list[HistoryEntry],
)
def read_exception_history_v1(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """The reconstructed chronological operational history of one exception."""

    history = services.get_exception_history(
        connection,
        exception_id,
    )

    if history is None:

        _not_found(
            f"Exception {exception_id} not found."
        )

    return history


@app.get(
    "/v1/exceptions/{exception_id}/assessment",
    response_model=RecoveryAssessment,
)
def read_recovery_assessment_v1(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """The deterministic recovery assessment: recommendation, alternatives, rationale — or the evaluated options explaining why none exists."""

    assessment = services.get_recovery_assessment(
        connection,
        exception_id,
    )

    if assessment is None:

        _not_found(
            f"Exception {exception_id} not found."
        )

    return assessment


@app.get(
    "/v1/exceptions/{exception_id}/sustainability",
    response_model=(
        SustainabilityComparison | SustainabilityUnavailable
    ),
)
def read_sustainability_v1(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """The informational emissions comparison, or the structured unavailable state when there is nothing to compare."""

    # Distinguish a missing exception (404) from an existing
    # exception with no deterministic recommendation to
    # compare (the structured unavailable state).

    exception = services.get_exception_context(
        connection,
        exception_id,
    )

    if exception is None:

        _not_found(
            f"Exception {exception_id} not found."
        )

    comparison = services.get_sustainability_comparison(
        connection,
        exception_id,
    )

    if comparison is None:

        return SustainabilityUnavailable(
            status="unavailable",
            reason=(
                "No deterministic recommendation exists for "
                "this exception, so there is nothing to "
                "compare."
            ),
        )

    return comparison


@app.get(
    "/v1/exceptions/{exception_id}/interventions",
    response_model=list[ManualInterventionRecord],
)
def read_manual_interventions_v1(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """The recorded manual interventions for one exception (newest first)."""

    exception = services.get_exception_context(
        connection,
        exception_id,
    )

    if exception is None:

        _not_found(
            f"Exception {exception_id} not found."
        )

    return services.get_manual_interventions(
        connection,
        exception_id,
    )


@app.get(
    "/v1/exceptions/{exception_id}/decision-brief",
    response_model=DecisionBrief,
)
def read_decision_brief_v1(
    exception_id: str,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """
    The advisory AI decision brief for one exception.

    Advisory layer only: it interprets evidence the
    deterministic decision engine has already established and
    is never the operational authority. The provider runs
    inside the existing ai_support boundary — no external
    model is contacted, the brief is never persisted, and no
    workflow or database state can change.

    A missing exception is 404 (distinguishing not-found from
    the structured unavailable advisory state), mirroring the
    sustainability and interventions endpoints.
    """

    exception = services.get_exception_context(
        connection,
        exception_id,
    )

    if exception is None:

        _not_found(
            f"Exception {exception_id} not found."
        )

    return services.get_decision_brief(
        connection,
        exception_id,
    )


@app.post(
    "/v1/exceptions/{exception_id}/manual-resolution",
    response_model=ManualResolutionOutcome,
)
def record_manual_resolution_v1(
    exception_id: str,
    request: ManualResolutionRequest,
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """Record a planner-performed manual resolution for an exception with no feasible system recovery."""

    outcome = services.record_manual_resolution(
        connection,
        exception_id,
        request.intervention_type,
        request.external_party,
        request.resolution_summary,
        request.recorded_by,
        request.outcome,
        new_expected_delivery=request.new_expected_delivery,
        notes=request.notes,
    )

    return outcome


@app.post(
    "/v1/operations/refresh",
    response_model=OperationalRefreshSummary,
)
def run_operational_refresh_v1(
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """Run the operational pipeline: detect exceptions, generate options, evaluate actions."""

    return services.run_operational_refresh(connection)


@app.post(
    "/v1/operations/simulate-arrival",
    response_model=SimulatedArrivalSummary,
)
def run_simulated_arrival_v1(
    connection=Depends(get_db),
    _api_key: str = Depends(require_api_key),
):
    """Create one controlled simulated shipment arrival (no exceptions; the refresh detects them)."""

    arrival = services.run_data_arrival_simulation(connection)

    if arrival is None:

        raise HTTPException(
            status_code=409,
            detail=(
                "No operational data to derive a simulated "
                "arrival from."
            ),
        )

    return arrival


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
    _api_key: str = Depends(require_api_key),
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
    _api_key: str = Depends(require_api_key),
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
    _api_key: str = Depends(require_api_key),
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
