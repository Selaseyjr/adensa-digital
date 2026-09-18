"""
Adensa Digital repository layer (Phase 1a).

Repositories own the SQL for a single aggregate and expose it
as plain functions that accept an existing sqlite connection:

    UI → engines → repositories → SQLite

Design rules:

- Plain functions only: no classes, no base classes, no ORM.
- Repositories never commit: transaction boundaries stay with
  the calling engine functions, exactly as before.
- Repositories contain no business rules; they move existing
  SQL verbatim, preserving semantics, ordering, parameters
  and returned columns.
- Repositories import nothing from the engines, so the
  dependency graph stays acyclic.
"""
