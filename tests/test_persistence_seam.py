"""
P5.2 — persistence abstraction seam tests.

The seam under test:

- DATABASE_URL absent resolves to the default SQLite backend;
- a sqlite:/// DATABASE_URL re-points the connection factory
  without touching anything else;
- a postgresql:// DATABASE_URL is *representable* (backend,
  redacted description) while the connection factory fails fast
  — PostgreSQL is not implemented in this checkpoint;
- credentials never survive in a loggable description;
- the migration runner's version state stays pinned to
  PRAGMA user_version on SQLite connections.

No test touches data/adensa.db: everything runs against
in-memory or disposable temporary databases, or against pure
configuration objects.
"""

import os
import sqlite3

import pytest

import app.database as database
from app import migrations
from app.config import (
    DatabaseConfig,
    get_database_config,
)
from app.migrations import (
    CURRENT_VERSION,
    apply_pending_migrations,
    get_schema_version,
)


@pytest.fixture(autouse=True)
def clean_database_url(monkeypatch):
    """Every test starts with no DATABASE_URL in the environment."""

    monkeypatch.delenv("DATABASE_URL", raising=False)


# ==================================================
# CONFIGURATION RESOLUTION
# ==================================================

def test_default_configuration_is_sqlite():
    """DATABASE_URL absent -> the default SQLite backend."""

    config = get_database_config()

    assert config.is_sqlite
    assert not config.is_postgresql
    assert config.sqlite_path is None


def test_sqlite_url_selects_sqlite_backend_with_explicit_path(
    tmp_path,
    monkeypatch,
):
    """A sqlite:/// DATABASE_URL names an explicit database file."""

    database_file = tmp_path / "explicit.db"

    import sys

    if sys.platform.startswith("win"):
        url = "sqlite:///" + str(database_file).replace("\\", "/")
    else:
        url = "sqlite:///" + str(database_file)

    # monkeypatch.setenv, never a raw os.environ write: the
    # environment must be restored for the rest of the session.
    monkeypatch.setenv("DATABASE_URL", url)

    config = get_database_config()

    assert config.is_sqlite
    assert config.sqlite_path == database_file


def test_postgresql_url_is_represented_without_a_server(monkeypatch):
    """
    A postgresql:// URL resolves to the PostgreSQL backend
    configuration without any server being contacted.
    """

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://planner:not-a-real-secret@db.internal:5432/adensa",
    )

    config = get_database_config()

    assert config.is_postgresql
    assert not config.is_sqlite


def test_unsupported_scheme_fails_fast(monkeypatch):
    """An unrecognized DATABASE_URL scheme is a configuration error."""

    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@host/db")

    with pytest.raises(ValueError, match="unsupported scheme"):
        get_database_config()


def test_safe_description_never_contains_credentials():
    """
    The loggable description redacts the password: credentials
    cannot leak through diagnostics.
    """

    config = DatabaseConfig(
        backend="postgresql",
        url="postgresql://planner:super-secret-value@db.internal:5432/adensa",
    )

    description = config.safe_description()

    assert "super-secret-value" not in description
    assert "planner:***@db.internal:5432" in description


def test_safe_description_for_sqlite_names_no_credentials():
    """The SQLite description carries only the path."""

    config = DatabaseConfig(backend="sqlite")

    assert "default development path" in config.safe_description()


# ==================================================
# CONNECTION FACTORY
# ==================================================

def test_factory_uses_module_path_default_without_database_url():
    """
    Without DATABASE_URL the factory opens the module-level
    DATABASE_PATH default — the seam the established test
    suite monkeypatches.
    """

    connection = database.get_connection()

    try:
        assert isinstance(connection, sqlite3.Connection)
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_factory_opens_sqlite_url_path(tmp_path, monkeypatch):
    """A sqlite:/// DATABASE_URL re-points the factory."""

    database_file = tmp_path / "url_seam.db"

    import sys

    if sys.platform.startswith("win"):
        url = "sqlite:///" + str(database_file).replace("\\", "/")
    else:
        url = "sqlite:///" + str(database_file)

    monkeypatch.setenv("DATABASE_URL", url)

    assert database.get_sqlite_path() == database_file

    connection = database.get_connection()

    try:
        assert isinstance(connection, sqlite3.Connection)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_factory_fails_fast_for_postgresql_without_a_driver(monkeypatch):
    """
    A postgresql:// DATABASE_URL must not silently fall back to
    SQLite: the factory raises until the PostgreSQL backend
    checkpoint lands.
    """

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://u:p@localhost:5432/adensa",
    )

    with pytest.raises(NotImplementedError, match="not implemented yet"):
        database.get_connection()


# ==================================================
# MIGRATION VERSION-STATE SEAM
# ==================================================

def test_fresh_sqlite_url_database_reaches_current_version(tmp_path, monkeypatch):
    """
    initialize_database() honors a sqlite:/// DATABASE_URL and
    reconstructs the complete schema through the history.
    """

    database_file = tmp_path / "url_init.db"

    import sys

    if sys.platform.startswith("win"):
        url = "sqlite:///" + str(database_file).replace("\\", "/")
    else:
        url = "sqlite:///" + str(database_file)

    monkeypatch.setenv("DATABASE_URL", url)

    database.initialize_database()

    connection = database.get_connection()

    try:
        assert get_schema_version(connection) == CURRENT_VERSION
    finally:
        connection.close()


def test_version_backend_for_sqlite_connection_is_pragma_based():
    """
    The version-state seam resolves SQLite connections to the
    historical PRAGMA user_version store — the established
    stamp mechanism, unchanged.
    """

    connection = sqlite3.connect(":memory:")

    try:
        read_version, write_version = migrations._version_backend(connection)

        assert read_version() == 0

        write_version(7)
        connection.commit()

        assert read_version() == 7
    finally:
        connection.close()


def test_current_sqlite_database_remains_strict_noop(tmp_path, monkeypatch):
    """
    The current-database guarantee survives the refactor: a
    schema-current database performs no migration work.
    """

    database_file = tmp_path / "noop.db"
    monkeypatch.setattr(database, "DATABASE_PATH", database_file)

    database.initialize_database()

    def _must_not_migrate(connection):
        raise AssertionError("migrations ran on a current database")

    monkeypatch.setattr(migrations, "apply_pending_migrations", _must_not_migrate)

    database.initialize_database()

    connection = database.get_connection()

    try:
        assert get_schema_version(connection) == CURRENT_VERSION
    finally:
        connection.close()


def test_failed_migration_still_does_not_advance_version(tmp_path, monkeypatch):
    """
    The stamping guarantee survives the version-seam refactor:
    a failed migration leaves the recorded version untouched.
    """

    connection = sqlite3.connect(tmp_path / "failure.db")

    exploding = [
        (1, "first", ["CREATE TABLE ok_table (id INTEGER)"]),
        (
            2,
            "second",
            [
                "CREATE TABLE second_table (id INTEGER)",
                "CREATE TABLE broken (incomplete",
            ],
        ),
    ]

    monkeypatch.setattr(migrations, "MIGRATIONS", exploding)

    with pytest.raises(Exception):
        apply_pending_migrations(connection)

    assert get_schema_version(connection) == 1
    connection.close()
