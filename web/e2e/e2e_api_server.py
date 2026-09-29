"""
P12.4 E2E helper: prepare the disposable database, then serve
the API.

Playwright starts its webServer processes before global setup
runs, so the disposable-database bootstrap must happen inside
this process BEFORE uvicorn begins serving: the application's
fail-fast lifespan check only passes once the schema is
current, so `/health` answers exactly when the database is
ready — no polling workarounds needed.

The database is rebuilt fresh on every run through the
project's canonical, idempotent initializer
(`app.bootstrap.initialize_adensa`), selected via the
documented `DATABASE_URL=sqlite:///` seam (P5.2). The canonical
development database (data/adensa.db) is never touched, and no
remote (Neon) URL is ever inherited: the E2E run owns its own
file.
"""

import logging
import os
import sys

DB_PATH = os.environ["E2E_DATABASE_PATH"]


def prepare_database() -> None:
    """Delete any previous disposable database and rebuild it."""

    for suffix in ("", "-wal", "-shm", "-journal"):
        artifact = DB_PATH + suffix
        if os.path.exists(artifact):
            os.remove(artifact)

    os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"

    from app.bootstrap import initialize_adensa

    logging.basicConfig(level=logging.WARNING)
    initialize_adensa()

    size = os.path.getsize(DB_PATH)
    if size == 0:
        raise RuntimeError("E2E database bootstrap produced an empty file.")

    print(
        f"[e2e] disposable database ready: {DB_PATH} ({size} bytes)",
        file=sys.stderr,
        flush=True,
    )


def main() -> None:
    prepare_database()

    import uvicorn

    uvicorn.run(
        "app.api:app",
        host="127.0.0.1",
        port=int(os.environ.get("E2E_API_PORT", "8013")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
