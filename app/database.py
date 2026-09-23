import logging
import sqlite3

from app.config import DATABASE_PATH
from app.migrations import apply_pending_migrations

logger = logging.getLogger(__name__)


# ==================================================
# DATABASE CONNECTION
# ==================================================

def get_connection():
    """Create and return a connection to the Adensa Digital database."""

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    # Foreign-key enforcement must be enabled for every SQLite connection.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


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