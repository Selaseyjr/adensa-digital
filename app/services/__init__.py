"""
Application service layer - package facade (P12.3).

Owns the application/workflow orchestration that previously
lived in the Streamlit reference client (retired, ADR-013):

    Next.js UI
         |
         v
    FastAPI (app/api) / CLI (app/cli)
         |
         v
      services        <- this package
         |
         v
      engines
         |
         v
    repositories
         |
         v
   SQLite / PostgreSQL

Rules:

- Services sequence engines and repositories and construct
  application-level result dictionaries for any frontend.
- Business rules stay in the engines; this package never
  duplicates them.
- No UI imports and no UI strings: clients consume the
  returned dictionaries.
- No commits and no transaction management: transaction
  boundaries remain exactly where they were (inside the
  engine operations).

This module is a pure re-export facade over the cohesive
service groups (P12.3 decomposition): every existing
`app.services` import path keeps working unchanged.
"""

from app.services.context import get_exception_context
from app.services.history import (
    get_exception_history,
    get_manual_interventions,
)
from app.services.inbox import (
    WORKFLOW_STATES,
    get_dashboard_metrics,
    get_exception_inbox,
)
from app.services.manual_resolution import (
    INTERVENTION_TYPES,
    OUTCOME_RESOLVED,
    OUTCOME_STILL_OPEN,
    record_manual_resolution,
)
from app.services.pipeline import run_operational_refresh
from app.services.review import (
    RATIONALE_FACTORS,
    get_exception_review,
    get_latest_action,
    get_recommendation_rationale,
    get_recovery_assessment,
)
from app.services.decision_brief import (
    build_decision_brief_evidence,
    get_decision_brief,
)
from app.services.operational_state import (
    classify_investigation_state,
    get_analytics_overview,
    get_control_tower_summary,
    get_follow_up_queue,
)
from app.services.sustainability import (
    get_sustainability_comparison,
)
from app.services.simulation import run_data_arrival_simulation
from app.services.workflow import (
    approve_recovery,
    execute_approved_recovery,
    reject_recovery,
)

# Patch-seam compatibility (P12.3): the pre-split module's
# namespace carried the engine functions and the AI provider
# it called, and the test suite patches them through this
# module object (services.detect_exceptions etc.). The moved
# groups call these through the package at call time, so the
# seam behaves identically. These are the SAME objects the
# monolith imported - re-exported, not wrapped.
from app.ai_support import DEFAULT_PROVIDER  # noqa: E402
from app.detect_exceptions import detect_exceptions  # noqa: E402
from app.execution_engine import execute_recovery_action  # noqa: E402
from app.generate_recovery_options import generate_recovery_options  # noqa: E402
from app.workflow_engine import generate_workflow_actions  # noqa: E402

__all__ = [
    "WORKFLOW_STATES",
    "DEFAULT_PROVIDER",
    "detect_exceptions",
    "execute_recovery_action",
    "generate_recovery_options",
    "generate_workflow_actions",
    "RATIONALE_FACTORS",
    "INTERVENTION_TYPES",
    "OUTCOME_RESOLVED",
    "OUTCOME_STILL_OPEN",
    "get_analytics_overview",
    "get_control_tower_summary",
    "get_dashboard_metrics",
    "get_decision_brief",
    "get_exception_context",
    "get_exception_history",
    "get_exception_inbox",
    "get_exception_review",
    "get_follow_up_queue",
    "get_latest_action",
    "get_manual_interventions",
    "get_recommendation_rationale",
    "get_recovery_assessment",
    "get_sustainability_comparison",
    "approve_recovery",
    "reject_recovery",
    "execute_approved_recovery",
    "record_manual_resolution",
    "run_data_arrival_simulation",
    "run_operational_refresh",
    "classify_investigation_state",
    "build_decision_brief_evidence",
]
