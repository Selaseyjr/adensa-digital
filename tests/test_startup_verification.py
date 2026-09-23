"""
Startup-verification and operational-logging tests (P6.2).

Covers the deployment-hardening contract added to app.api:

- verify_database_startup() succeeds on a current schema and
  closes the connection it opened;
- it fails clearly when the database is unreachable or the
  schema is stale, logging the redacted backend description
  only;
- a stale schema blocks TestClient startup (the lifespan is
  wired);
- an unexpected request exception is logged server-side while
  the client keeps FastAPI's generic 500 response — and no
  API key or request material appears in the log.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app import api as api_module
from app import database
from app.api import verify_database_startup
from app.migrations import CURRENT_VERSION


# ==================================================
# LIFESPAN VERIFICATION
# ==================================================


def test_startup_verification_succeeds_on_current_schema(
    temp_database,
    caplog,
):
    """A reachable, schema-current database passes verification."""

    with caplog.at_level(logging.ERROR, logger="app.api"):
        verify_database_startup()

    error_records = [
        record for record in caplog.records if record.levelno >= logging.ERROR
    ]

    assert error_records == []


def test_startup_closes_the_connection_it_opens(
    temp_database,
    monkeypatch,
):
    """
    The verification connection is always closed — including
    on the success path — so startup cannot leak connections.
    """

    real_connection = database.get_connection()
    closed = []

    class _TrackingConnection:
        def close(self):
            closed.append(True)
            real_connection.close()

        def __getattr__(self, name):
            return getattr(real_connection, name)

    monkeypatch.setattr(
        api_module,
        "get_connection",
        lambda: _TrackingConnection(),
    )

    try:
        verify_database_startup()
    finally:
        if not closed:
            real_connection.close()

    assert closed == [True]


def test_startup_fails_when_database_is_unreachable(
    temp_database,
    monkeypatch,
    caplog,
):
    """
    A connection failure aborts startup with a clear log line
    carrying the redacted backend description only.
    """

    def _broken_connection():
        raise RuntimeError("connection refused (test)")

    monkeypatch.setattr(api_module, "get_connection", _broken_connection)

    with caplog.at_level(logging.ERROR, logger="app.api"):

        with pytest.raises(RuntimeError):
            verify_database_startup()

    assert any(
        "database unreachable" in record.getMessage()
        for record in caplog.records
    )


def test_startup_fails_when_schema_is_stale(
    temp_database,
    caplog,
):
    """
    A version stamp below CURRENT_VERSION fails startup: the
    API must not serve against a known stale schema (ADR-012).
    Migrations stay a bootstrap/CLI responsibility.
    """

    temp_database.execute("PRAGMA user_version = 0")
    temp_database.commit()

    try:
        with caplog.at_level(logging.ERROR, logger="app.api"):

            with pytest.raises(RuntimeError, match="outdated"):
                verify_database_startup()

        assert any(
            "Startup verification failed" in record.getMessage()
            for record in caplog.records
        )
    finally:
        temp_database.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
        temp_database.commit()


def test_stale_schema_blocks_test_client_startup(temp_database):
    """
    The lifespan is wired: entering the app context against a
    stale-schema database raises instead of serving requests.
    """

    temp_database.execute("PRAGMA user_version = 0")
    temp_database.commit()

    try:
        with pytest.raises(RuntimeError):
            with TestClient(api_module.app):
                pass
    finally:
        temp_database.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
        temp_database.commit()


# ==================================================
# UNEXPECTED EXCEPTION LOGGING
# ==================================================


def test_unexpected_exception_is_logged_and_stays_generic(
    seeded_database,
    monkeypatch,
    caplog,
):
    """
    An unexpected application exception produces a generic 500
    for the client and a server-side traceback — without the
    API key, headers or request payload in any log record.
    """

    TEST_KEY = "startup-test-key-not-a-secret"

    monkeypatch.setattr(api_module, "ADENSA_API_KEY", TEST_KEY)

    def _unexpected_failure(connection):
        raise RuntimeError("internal detail for the server log")

    monkeypatch.setattr(
        api_module.services,
        "get_dashboard_metrics",
        _unexpected_failure,
    )

    with caplog.at_level(logging.ERROR, logger="app.api"):
        # raise_server_exceptions=False: the production path,
        # where the handler converts the exception into the
        # generic 500 response instead of the test client
        # re-raising it.
        with TestClient(api_module.app, raise_server_exceptions=False) as client:
            response = client.get(
                "/metrics",
                headers={"X-API-Key": TEST_KEY},
            )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}

    matching = [
        record
        for record in caplog.records
        if "Unhandled exception" in record.getMessage()
    ]

    assert len(matching) == 1

    record = matching[0]

    assert "/metrics" in record.getMessage()
    assert record.exc_info is not None

    # Credential and payload hygiene: the key must not appear,
    # and the request carried no logged headers or body.
    log_text = caplog.text

    assert TEST_KEY not in log_text
    assert "x-api-key" not in log_text.lower()
