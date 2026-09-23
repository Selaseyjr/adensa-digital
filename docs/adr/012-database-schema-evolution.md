# ADR-012 — Application-managed database schema evolution

## Status

Accepted

## Context

Every Adensa table was created with `CREATE TABLE IF NOT EXISTS`
inside a single initializer. That made fresh-environment setup
trivially idempotent, but it can never express *change*: a table
that exists under an outdated definition is invisible to the
initializer, there is no record of which structural state a
database is actually in, and startup cannot distinguish a current
database from a stale one.

P3.1 (the schema-drift audit) proved the gap is real, not
theoretical. The development database predated the
`manual_interventions` table, the only drift in the repository,
and the production `/v1/exceptions/{id}/history` and
`/interventions` endpoints failed against it with
`no such table: manual_interventions` while every test suite
stayed green — tests run on freshly initialized temporary
databases, so they are structurally blind to drift on an
existing database. The audit also established that the FastAPI
path, unlike the Streamlit entry point, never runs schema
initialization, so an API deployment can start against an
outdated schema without any signal.

## Decision

Schema evolution is owned by an **explicit, ordered migration
history** in `app/migrations.py`, and the history is the
conceptual source of truth for the schema.

- The history records the project's real evolution:
  `0001 — founding relational schema` (the 13 original tables)
  and `0002 — manual exception resolution`
  (`manual_interventions`). It does not invent migrations that
  never existed.
- The runner is small and dependency-free: each migration is a
  list of SQL statements applied inside one transaction, followed
  by the version stamp. A failure rolls back the failed
  migration's work before the stamp, so the version can never
  claim success for work that did not complete.
- SQLite records the applied version in `PRAGMA user_version`.
  The abstraction itself is sequential version numbers plus plain
  SQL, so the later PostgreSQL transition (P-series) reuses the
  same history with a `schema_migrations` table as the stamp —
  not a second, competing schema-definition system.
- `initialize_database()` now delegates to the runner:
  a fresh database applies the full history, a version-0
  database (every database created before migrations existed)
  applies it additively and idempotently without touching
  existing data, and a current database performs no work.
- `REQUIRED_TABLES` includes `manual_interventions`, so the
  bootstrap schema guard and the migration history describe the
  same schema.
- `/ready` fails closed: it reports
  `503 {"status": "degraded", "database": "schema-outdated"}`
  when the database's schema version is behind, so API startup
  cannot silently operate against a known stale schema.

## Why now, and why not Alembic or SQLAlchemy

Migration tooling is being introduced now because the first
real drift was discovered by a production endpoint failing
against a real database, and because the P-series is actively
building on the API/application boundary — every further
checkpoint that touches persistence compounds the risk.

Alembic and SQLAlchemy remain intentionally deferred. The
repositories are deliberately hand-written SQL (ADR-002);
adopting an ORM, or a migration tool that requires one, would
introduce a parallel schema description for marginal benefit at
the current scale. The home-grown runner is ~20 statements of
history and a loop. The decision to adopt Alembic belongs with
the PostgreSQL transition, if the schema surface grows beyond
what the history can express clearly.

## Consequences

- Schema changes now require a migration, reviewed in code,
  instead of an edit to a DDL block.
- Existing databases upgrade on the normal initialization path;
  no environment-specific repair scripts are needed.
- The development database was upgraded through this path in the
  same checkpoint as the code (its SHA changed by design; the
  operational data was preserved and verified row-for-row).
- Fresh checkouts, tests, and CI exercise the identical
  migration path, so tests can no longer be blind to drift.

## Deliberately deferred

- Alembic / SQLAlchemy and any ORM adoption.
- PostgreSQL itself and a shared-engine migration stamp.
- Destructive migrations (`ALTER`/rebuild tooling) — none has
  ever been needed; the first one that is will be written as an
  explicit, data-preserving migration with tests.
- Automated production migration runs at deploy time: startup
  verification (readiness failing closed) is the current
  contract; unattended upgrades remain a future operational
  decision.
