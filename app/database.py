import logging
import sqlite3

from app.config import DATABASE_PATH, get_database_config
from app.migrations import apply_pending_migrations
from app.pg_compat import Row, rows_from_cursor, translate_sql

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


class PostgresConnectionAdapter:
    """
    Adapt a psycopg connection to the sqlite3-style surface the
    application already uses:

        connection.execute(sql, params) -> cursor (rows attached)
        connection.commit() / rollback() / close()
        connection.cursor().execute(...) -> cursor

    PostgreSQL differences are absorbed exactly here:

    - SQL is translated from the SQLite dialect at execution
      time (app.pg_compat.translate_sql) — one SQL source of
      truth in the application;
    - result rows are converted to Row objects with the
      sqlite3.Row access contract, so no driver-specific type
      crosses the service boundary;
    - explicit `BEGIN` statements are dropped: under
      autocommit, PostgreSQL already starts a transaction on
      the first data-modifying statement, and psycopg forbids
      issuing BEGIN manually (the transaction begins
      implicitly and is terminated by commit()/rollback(),
      exactly the discipline the engines already follow).

    The adapter holds no state beyond the wrapped connection;
    commit(), rollback() and close() pass through to the
    wrapped psycopg connection, so the engines' transaction
    discipline works unchanged.
    """

    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return _PostgresCursor(self._connection.cursor())

    def execute(self, sql, parameters=()):
        return _PostgresCursor(self._connection.cursor()).execute(
            sql,
            parameters,
        )

    def __getattr__(self, name):
        # commit, rollback, close and any future passthrough.
        return getattr(self._connection, name)


class _PostgresCursor:
    """
    sqlite3-flavoured cursor over a psycopg cursor: execute()
    accepts SQLite-dialect SQL, and fetchone()/fetchall()
    return Row objects carrying the cursor description's
    column names.
    """

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, parameters=()):
        if _is_explicit_begin(sql):
            # A no-op under autocommit (see the adapter
            # docstring): the transaction begins implicitly
            # with the first data statement.
            return self

        self._cursor.execute(translate_sql(sql), parameters)

        return self

    def executemany(self, sql, seq):
        self._cursor.executemany(translate_sql(sql), seq)

        return self

    def fetchone(self):
        row = self._cursor.fetchone()

        if row is None:
            return None

        return Row(self._row_names(), row)

    def fetchall(self):
        return rows_from_cursor(self._cursor)

    def _row_names(self):
        description = self._cursor.description

        if description is None:
            return []

        return [column.name for column in description]

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()

    def __enter__(self):
        self._cursor.__enter__()

        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)


def _is_explicit_begin(sql):
    stripped = sql.strip().lower()

    return stripped == "begin" or stripped == "begin;"


_DEFAULT_CONNECT_TIMEOUT = "10"


def _with_default_connect_timeout(url):
    """
    Return the URL with a libpq connect_timeout applied unless
    the operator already configured one. Never changes any other
    part of the URL — credentials included.
    """

    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)

    existing = dict(parse_qsl(parts.query))

    if "connect_timeout" in existing:
        return url

    query = urlencode(
        [*parse_qsl(parts.query), ("connect_timeout", _DEFAULT_CONNECT_TIMEOUT)]
    )

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
    )


def _connect_postgresql(config):
    """
    PostgreSQL backend (P5.3).

    Opens a psycopg connection against the configured
    DATABASE_URL and wraps it in the sqlite3-style adapter the
    application already consumes.

    Credentials stay server-side: the URL is never logged and
    only ever reaches psycopg; diagnostics go through
    DatabaseConfig.safe_description() which redacts passwords.
    """

    try:
        import psycopg
    except ImportError as error:  # pragma: no cover - environment guard
        raise RuntimeError(
            "DATABASE_URL selects the PostgreSQL backend but the "
            "psycopg driver is not installed. Install the optional "
            "dependency set: pip install -r requirements-postgres.txt"
        ) from error

    logger.info(
        "Connecting to PostgreSQL backend: %s",
        config.safe_description(),
    )

    # A PostgreSQL host that never answers must fail startup
    # quickly instead of hanging for the TCP-stack default
    # (minutes). The libpq connect_timeout is applied unless the
    # operator already set one in the URL.
    connection = psycopg.connect(
        _with_default_connect_timeout(config.url),
        autocommit=True,
    )

    return PostgresConnectionAdapter(connection)


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

    config = get_database_config()

    if config.is_sqlite:
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

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    initialize_database()
    logger.info("Adensa Digital database initialized successfully.")