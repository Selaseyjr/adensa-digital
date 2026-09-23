"""
SQLite→PostgreSQL compatibility layer (P5.3).

The application's SQL is written in SQLite's dialect and its
code consumes sqlite3.Row-style results. Rather than forking
every query into per-backend variants, this module performs an
explicit, deterministic translation at the persistence boundary
so the repositories, engines and services keep exactly one SQL
source of truth (extending the single-history principle of
ADR-012 to the dialect itself).

Statement translations (and only these):

?           -> %s            (paramstyle: qmark to format)
INSERT OR IGNORE INTO x
            -> INSERT INTO x ... ON CONFLICT DO NOTHING
feasible = 1 / active = 1
            -> feasible IS TRUE / active IS TRUE
                (the columns are BOOLEAN under PostgreSQL;
                 `= 1` does not even type-check against a
                 boolean, and `= TRUE` would drop NULL rows
                 silently — `IS TRUE` is the exact predicate)

DDL translations (the migration history stays the single
schema definition; the PostgreSQL rendering of the same DDL
resolves the type decisions from P5.1 explicitly):

INTEGER PRIMARY KEY AUTOINCREMENT
            -> SERIAL PRIMARY KEY       (inventory)
estimated_impact REAL NOT NULL
            -> estimated_impact TEXT NOT NULL
                (the application has always stored descriptive
                 text here and the /v1 contract declares str;
                 PostgreSQL REAL would reject it outright)
feasible INTEGER NOT NULL
active INTEGER NOT NULL
            -> BOOLEAN NOT NULL          (real booleans)
REAL        -> DOUBLE PRECISION
                (double precision avoids float4 truncation of
                 costs, scores and emissions factors)

Rows: the Row class reproduces the sqlite3.Row access contract
(name indexing, positional indexing, tuple(), len(), iteration,
keys(), dict()) so no driver-specific object crosses the
service boundary. sqlite3.Row itself cannot be constructed
directly on Python 3.14, so the PostgreSQL path carries its own
compatible implementation.

All identifiers in the schema are lowercase and unquoted, so
PostgreSQL's identifier folding is a non-issue.
"""

import re


# --------------------------------------------------
# SQL TRANSLATION
# --------------------------------------------------

# INSERT OR IGNORE ... VALUES (...)  ->  INSERT ... ON CONFLICT DO NOTHING
_INSERT_OR_IGNORE = re.compile(
    r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
    re.IGNORECASE,
)

# Trailing values-clause detection for appending the conflict
# clause after the final closing parenthesis of an INSERT.
_VALUES_END = re.compile(
    r"\)\s*(?:;\s*)?$"
)

_BOOLEAN_PREDICATES = (
    (re.compile(r"\bfeasible\s*=\s*1\b", re.IGNORECASE), "feasible IS TRUE"),
    (re.compile(r"\bactive\s*=\s*1\b", re.IGNORECASE), "active IS TRUE"),
)

_DDL_TRANSLATIONS = (
    (
        re.compile(
            r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
            re.IGNORECASE,
        ),
        "SERIAL PRIMARY KEY",
    ),
    (
        re.compile(
            r"\bestimated_impact\s+REAL\s+NOT\s+NULL\b",
            re.IGNORECASE,
        ),
        "estimated_impact TEXT NOT NULL",
    ),
    (
        re.compile(
            r"\bfeasible\s+INTEGER\s+NOT\s+NULL\b",
            re.IGNORECASE,
        ),
        "feasible BOOLEAN NOT NULL",
    ),
    (
        re.compile(
            r"\bactive\s+INTEGER\s+NOT\s+NULL\b",
            re.IGNORECASE,
        ),
        "active BOOLEAN NOT NULL",
    ),
    (
        re.compile(r"\bREAL\b", re.IGNORECASE),
        "DOUBLE PRECISION",
    ),
)


def _translate_insert_or_ignore(sql: str) -> str:
    """
    Rewrite INSERT OR IGNORE into INSERT ... ON CONFLICT DO
    NOTHING. The conflict clause must follow the statement's
    values list, so the final closing parenthesis is located
    from the end and re-emitted before the clause (any trailing
    semicolon/whitespace is preserved).
    """

    rewritten = _INSERT_OR_IGNORE.sub("INSERT INTO", sql)

    match = None

    for match in _VALUES_END.finditer(rewritten):
        pass

    if match is None:
        # No recognizable VALUES terminator: leave the
        # statement untouched rather than half-rewrite it
        # (dropping OR IGNORE without adding the conflict
        # clause would silently change the semantics).
        return sql

    head = rewritten[: match.start()]
    tail = rewritten[match.start():]

    # head ends just before the final ')'; tail starts with
    # that ')' plus any trailing whitespace/semicolon. Re-emit
    # the closing parenthesis, then the conflict clause, then
    # the tail minus the ')' it carries.
    return f"{head}) ON CONFLICT DO NOTHING{tail[1:]}"


def translate_sql(sql: str) -> str:
    """
    Translate one SQLite-dialect statement (or script) into
    PostgreSQL dialect, including SQLite-flavoured DDL.
    Whitespace and layout are preserved.
    """

    translated = sql.replace("?", "%s")

    for pattern, replacement in _DDL_TRANSLATIONS:
        translated = pattern.sub(replacement, translated)

    for pattern, replacement in _BOOLEAN_PREDICATES:
        translated = pattern.sub(replacement, translated)

    if _INSERT_OR_IGNORE.search(translated):
        translated = _translate_insert_or_ignore(translated)

    return translated


# --------------------------------------------------
# ROW COMPATIBILITY
# --------------------------------------------------

class Row:
    """
    Dictionary-like row with the sqlite3.Row access contract:
    name indexing, positional indexing (including negative),
    tuple(), len(), iteration, keys() and dict() conversion.
    """

    __slots__ = ("_keys", "_values")

    def __init__(self, keys, values):

        self._keys = tuple(keys)
        self._values = tuple(values)

    def __getitem__(self, key):

        if isinstance(key, (int, slice)):
            return self._values[key]

        if isinstance(key, str):
            try:
                index = self._keys.index(key)
            except ValueError:
                raise IndexError(f"No column named {key!r}")

            return self._values[index]

        raise TypeError(
            "Row index must be an integer, slice or string"
        )

    def __contains__(self, key):
        return key in self._keys

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._keys)

    def items(self):
        return list(zip(self._keys, self._values))

    def __eq__(self, other):

        if isinstance(other, Row):
            return (
                self._keys == other._keys
                and self._values == other._values
            )

        if isinstance(other, (list, tuple)):
            return self._values == tuple(other)

        return NotImplemented

    def __hash__(self):
        return hash((self._keys, self._values))

    def __repr__(self):
        pairs = ", ".join(
            f"{key!r}: {value!r}"
            for key, value in zip(self._keys, self._values)
        )
        return f"Row({{{pairs}}})"


def rows_from_cursor(cursor):
    """
    Fetch and convert every remaining result row of a psycopg
    cursor into Row objects, using the cursor's own column
    description for the names.
    """

    description = cursor.description

    if description is None:
        return []

    names = [column.name for column in description]

    return [
        Row(names, row)
        for row in cursor.fetchall()
    ]
