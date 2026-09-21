import os
from pathlib import Path


# ==================================================
# API SECURITY CONFIGURATION
# ==================================================

# Prototype-grade API-key authentication for the FastAPI
# boundary (app/api.py). The key is sourced exclusively from
# the environment and never hard-coded, committed or logged;
# when it is unset the mutation endpoints fail closed (503)
# instead of silently allowing unauthenticated access.
#
# This is a controlled prototype mechanism, NOT a production
# identity architecture (no OAuth, no users, no JWT).

ADENSA_API_KEY = os.environ.get("ADENSA_API_KEY")


# ==================================================
# PROJECT PATHS
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "adensa.db"


# ==================================================
# SIMULATION CONFIGURATION
# ==================================================

# Adensa Digital currently operates in a controlled
# synthetic supply-chain simulation environment.

SIMULATION_DATE = "2026-09-10"
SIMULATION_TIMESTAMP = "2026-09-10 12:00:00"


# ==================================================
# WORKFLOW CONFIGURATION
# ==================================================

# In the current prototype, recovery execution is
# simulated one day after the shipment's planned
# departure.

RECOVERY_EXECUTION_OFFSET_DAYS = 1


# ==================================================
# DECISION ENGINE CONFIGURATION
# ==================================================

# The decision engine computes the overall score as a
# weighted combination of the four factor scores, so the
# weights are only meaningful as a complete, normalized
# policy. Fail fast at import time if the configuration
# drifts from that assumption.

DECISION_WEIGHTS = {
    "cost": 0.25,
    "transit": 0.30,
    "risk": 0.25,
    "priority_alignment": 0.20,
}

assert abs(sum(DECISION_WEIGHTS.values()) - 1.0) < 1e-9, (
    "DECISION_WEIGHTS must sum to 1.0; the decision score "
    "is a weighted combination of the four factor scores."
)


# Cost benchmarks in EUR

COST_BENCHMARK = {
    "excellent": 1500,
    "acceptable": 3000,
    "expensive": 5000,
}


# Recovery transit benchmarks in days

TRANSIT_BENCHMARK = {
    "excellent": 3,
    "acceptable": 7,
    "slow": 14,
}


# Operational risk benchmarks

RISK_BENCHMARK = {
    "excellent": 25,
    "acceptable": 50,
    "high": 75,
}