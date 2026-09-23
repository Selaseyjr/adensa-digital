import logging
import sqlite3

from app.config import DATABASE_PATH, get_database_config
from app.migrations import apply_pending_migrations

logger = logging.getLogger(__name__)


# ==================================================
# DATABASE CONNECTION (BACKEND-AWARE FACTORY, P5.2)
# ==================================================
#
# The single connection boundary for every entry point
# (FastAPI, Streamlit, CLI, tests). Everything above this
# layer receives a connection and never constructs one, so
# the backend becomes an implementation detail here.
#
# The SQLite path is deliberately unchanged — including the
# module-level DATABASE_PATH default that the test suite
# re-points at disposable files (tests/conftest.py,
# tests/test_bootstrap.py, tests/test_migrations.py). The
# DATABASE_URL environment variable selects the backend when
# present; with it absent, get_sqlite_path() resolves to that
# module-level default, so the established behavior and test
# seams keep working exactly as before.


def get_sqlite_path():
    """
    Resolve the SQLite database file for this process.

    Order: an explicit sqlite:/// DATABASE_URL, otherwise the
    module-level DATABASE_PATH default (the seam the test
    suite monkeypatches).
    """

    config = get_database_config()

    if config.is_sqlite and config.sqlite_path is not None:
        return config.sqlite_path

    return DATABASE_PATH


def _connect_sqlite(path):
    """Open the SQLite backend with the project's connection contract."""

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row

    # Foreign-key enforcement must be enabled for every SQLite connection.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def _connect_postgresql(config):
    """
    PostgreSQL connection path of the seam.

    Represented and intentionally not implemented yet (P5.1):
    the PostgreSQL backend checkpoint will supply the driver
    and its row/transaction setup here. Failing fast keeps a
    misconfigured DATABASE_URL from silently falling back to
    SQLite and writing operational data to the wrong backend.
    """

    raise NotImplementedError(
        "PostgreSQL is configured via DATABASE_URL but the "
        "PostgreSQL backend is not implemented yet. Remove "
        "DATABASE_URL to use the default SQLite backend."
    )


def get_connection():
    """
    Create and return a connection to the configured Adensa
    Digital database backend.
    """

    config = get_database_config()

    if config.is_sqlite:
        return _connect_sqlite(get_sqlite_path())

    return _connect_postgresql(config)


# ==================================================
# DATABASE INITIALIZATION
# ==================================================

def initialize_database():
    """
    Bring the database schema to the current version.

    Schema evolution is owned by the migration history
    (app.migrations, ADR-012): a fresh database applies the full
    history, an older database applies the pending migrations,
    and a current database performs no unnecessary work.
    """

    # Make sure the data folder exists.
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection()

    try:
        apply_pending_migrations(connection)
    finally:
        connection.close()


# ==================================================
# RUN DATABASE INITIALIZATION
# ==================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_database()
    logger.info("Adensa Digital database initialized successfully.")