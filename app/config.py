import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


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
# API CORS CONFIGURATION
# ==================================================

# Origins allowed to call the versioned application API
# (ADR-011) from a browser — the separately hosted
# operational frontend. Sourced from the environment as a
# comma-separated list; empty by default, so the API is
# browser-origin-locked to whatever the deployment configures
# and never silently wide open ("*"). Machine-to-machine
# callers (Power Automate, the CLI) are unaffected: CORS only
# constrains browsers.

_cors_origins = os.environ.get("ADENSA_CORS_ORIGINS", "")

ADENSA_CORS_ORIGINS = [
    origin.strip()
    for origin in _cors_origins.split(",")
    if origin.strip()
]


# ==================================================
# DATABASE CONFIGURATION (P5.2 PERSISTENCE SEAM)
# ==================================================
#
# Backend selection is environment-driven. DATABASE_URL
# absent -> the existing default SQLite development database
# at DATABASE_PATH below (unchanged behavior). DATABASE_URL
# may name either backend:
#
#     sqlite:///C:/path/to/adensa.db     (Windows absolute path)
#     sqlite:////abs/posix/path          (POSIX absolute path)
#     postgresql://user:secret@host:5432/adensa
#
# A postgresql:// URL is *represented* here but not yet
# connectable: the connection factory fails fast with a clear
# error until the PostgreSQL backend checkpoint lands, so no
# half-supported dialect can silently corrupt operational
# data. No credentials are ever hard-coded, logged or exposed
# to the frontend; safe_description() redacts the password
# for any operational logging.


def _redact_url(url: str) -> str:
    """Mask the password of a database URL for safe display."""

    try:
        parts = urlsplit(url)
    except ValueError:
        return "postgresql (unparseable URL)"

    netloc = parts.netloc

    if "@" in netloc:
        userinfo, _, hostport = netloc.rpartition("@")
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:***@{hostport}"

    return urlunsplit(
        (parts.scheme, netloc, parts.path, "", "")
    )


@dataclass(frozen=True)
class DatabaseConfig:
    """The configured database backend, resolved at call time."""

    backend: str  # "sqlite" | "postgresql"
    # None for PostgreSQL; None also means "the default SQLite
    # development path" for the sqlite backend.
    sqlite_path: Path | None = None
    url: str | None = None

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def is_postgresql(self) -> bool:
        return self.backend == "postgresql"

    def safe_description(self) -> str:
        """
        Human-readable description with credentials redacted —
        the only form of this configuration that may appear in
        logs or diagnostics.
        """

        if self.is_sqlite:
            return f"sqlite ({self.sqlite_path or 'default development path'})"

        return f"postgresql ({_redact_url(self.url or '')})"


def _parse_sqlite_url(url: str) -> Path:
    """Extract the file path from a sqlite:/// URL."""

    # The authority component is always empty for sqlite URLs,
    # so the path starts right after scheme + "//". Strip the
    # single slash that separates the empty authority from the
    # URL path (the SQLAlchemy sqlite-URL convention):
    #
    #   sqlite:///C:/data/adensa.db   -> C:/data/adensa.db
    #   sqlite:////abs/posix/path     -> /abs/posix/path
    #   sqlite:///relative/adensa.db  -> relative/adensa.db
    #
    # A leading slash on the result therefore means a genuine
    # POSIX-absolute path — never an empty-authority artifact —
    # so Path equality holds on every platform.

    path = url[len("sqlite://"):]

    if path.startswith("/"):
        path = path[1:]

    return Path(path)


def get_database_config() -> DatabaseConfig:
    """
    Resolve the configured database backend.

    Read at call time (not import time) so tests and entry
    points can select a backend per process via the
    environment without re-importing the module.
    """

    url = os.environ.get("DATABASE_URL", "").strip()

    if not url:
        return DatabaseConfig(backend="sqlite")

    scheme = url.split(":", 1)[0].lower()

    if scheme in ("postgres", "postgresql"):
        return DatabaseConfig(
            backend="postgresql",
            url=url,
        )

    if scheme == "sqlite":
        return DatabaseConfig(
            backend="sqlite",
            sqlite_path=_parse_sqlite_url(url),
        )

    raise ValueError(
        "DATABASE_URL uses an unsupported scheme: only "
        "sqlite:/// and postgresql:// are recognized."
    )


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


# ==================================================
# SUSTAINABILITY CONFIGURATION (PROTOTYPE)
# ==================================================

# Estimated transport emissions for recovery options.
#
# Methodology (prototype assumption, NOT measured data):
#
#     estimated CO2e (kg) = shipment tonnes
#                         × route kilometres
#                         × mode emissions factor
#
# Factors are kg CO2e per tonne-kilometre, expressed in
# indicative prototype magnitudes consistent with the
# publicly known ordering of transport modes (air highest,
# sea lowest). They are configurable assumptions for
# decision-support comparison, not carbon accounting, and
# every UI surface labels the result as an estimate.
#
# Only the transport modes Adensa actually supports are
# listed; an unsupported mode must fail safely rather than
# silently produce zero emissions.

TRANSPORT_EMISSIONS_FACTORS = {
    "Air": 0.60,
    "Road": 0.10,
    "Rail": 0.028,
    "Sea": 0.015,
}

EMISSIONS_UNIT = "kg CO₂e"

EMISSIONS_METHODOLOGY_NOTE = (
    "Estimated transport emissions = shipment tonnes × "
    "route kilometres × configured mode factor. Factors "
    "are prototype assumptions, not measured data."
)