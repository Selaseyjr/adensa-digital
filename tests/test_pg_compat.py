"""
Serverless dialect tests for the SQLite→PostgreSQL compatibility
layer (app/pg_compat.py).

These run in the default (SQLite) suite without any PostgreSQL
server: translate_sql() and the Row access contract are pure
Python and therefore testable everywhere. The live-server
behaviour (real BOOLEAN columns, SERIAL IDs, ON CONFLICT DO
NOTHING under load) is covered by the opt-in
tests/test_postgres_integration.py suite.
"""

from app.pg_compat import Row, translate_sql


# --------------------------------------------------
# DML TRANSLATION
# --------------------------------------------------


class TestParamstyle:
    def test_qmark_becomes_format(self):
        assert (
            translate_sql("SELECT * FROM t WHERE id = ? AND k = ?")
            == "SELECT * FROM t WHERE id = %s AND k = %s"
        )

    def test_qmark_inside_string_literal_is_also_replaced(self):
        # Known deliberate simplification: '?' has no SQL meaning
        # in this codebase's SQL (no literals contain it —
        # verified in the P5.3 audit), so a blanket replace is
        # sound here. Documented to make the trade-off explicit.
        assert translate_sql("SELECT '?'") == "SELECT '%s'"


class TestInsertOrIgnore:
    def test_simple_insert(self):
        sql = "INSERT OR IGNORE INTO shipments (shipment_id) VALUES (?)"
        expected = (
            "INSERT INTO shipments (shipment_id) VALUES (%s) "
            "ON CONFLICT DO NOTHING"
        )
        assert translate_sql(sql) == expected

    def test_multiline_insert_preserves_layout(self):
        sql = """INSERT OR IGNORE INTO warehouses (
    warehouse_id, warehouse_name
) VALUES (?, ?);"""
        translated = translate_sql(sql)
        assert translated.startswith("INSERT INTO warehouses (")
        assert "VALUES (%s, %s) ON CONFLICT DO NOTHING;" in translated

    def test_insert_without_ignore_untouched(self):
        sql = "INSERT INTO suppliers (supplier_id) VALUES (?)"
        assert "ON CONFLICT" not in translate_sql(sql)

    def test_unterminated_insert_left_unchanged(self):
        # No recognizable VALUES terminator: the translator must
        # not half-rewrite the statement (dropping OR IGNORE
        # without the conflict clause would silently change
        # its semantics).
        sql = "INSERT OR IGNORE INTO t (a) VALUES"
        assert translate_sql(sql) == sql


class TestBooleanPredicates:
    def test_feasible_equals_one(self):
        assert (
            translate_sql("SELECT * FROM recovery_options WHERE feasible = 1")
            == "SELECT * FROM recovery_options WHERE feasible IS TRUE"
        )

    def test_active_equals_one(self):
        assert (
            translate_sql("SELECT * FROM suppliers WHERE active = 1")
            == "SELECT * FROM suppliers WHERE active IS TRUE"
        )

    def test_zero_predicate_untouched(self):
        sql = "SELECT * FROM suppliers WHERE active = 0"
        assert translate_sql(sql) == sql

    def test_word_boundary_respected(self):
        # 'inactive' must not be rewritten by the 'active' rule:
        # the column is INTEGER under both backends.
        sql = "SELECT * FROM t WHERE inactive = 1"
        assert translate_sql(sql) == sql


# --------------------------------------------------
# DDL TRANSLATION (P5.1 TYPE DECISIONS)
# --------------------------------------------------


class TestDdlTranslation:
    def test_autoincrement_becomes_serial(self):
        sql = "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        assert "SERIAL PRIMARY KEY" in translate_sql(sql)
        assert "AUTOINCREMENT" not in translate_sql(sql)

    def test_estimated_impact_becomes_text(self):
        sql = "estimated_impact REAL NOT NULL,"
        assert "estimated_impact TEXT NOT NULL" in translate_sql(sql)

    def test_feasible_active_become_boolean(self):
        sql = (
            "feasible INTEGER NOT NULL,\n"
            "            active INTEGER NOT NULL,"
        )
        translated = translate_sql(sql)
        assert "feasible BOOLEAN NOT NULL" in translated
        assert "active BOOLEAN NOT NULL" in translated

    def test_real_becomes_double_precision(self):
        sql = "reliability_score REAL NOT NULL"
        assert "DOUBLE PRECISION" in translate_sql(sql)

    def test_migration_ddl_translates_cleanly(self):
        # Every statement of the real migration history must
        # translate into something PostgreSQL accepts; the type
        # decisions land exactly once each across the history.
        from app.migrations import MIGRATIONS

        translated_all = []
        for _, _, statements in MIGRATIONS:
            for statement in statements:
                translated_all.append(translate_sql(statement))

        joined = "\n".join(translated_all)
        assert "AUTOINCREMENT" not in joined
        assert "estimated_impact REAL" not in joined
        assert "feasible INTEGER" not in joined
        assert "active INTEGER" not in joined
        assert "REAL" not in joined  # fully resolved to DOUBLE PRECISION
        assert "?" not in joined

        assert joined.count("estimated_impact TEXT NOT NULL") == 1
        assert joined.count("feasible BOOLEAN NOT NULL") >= 1
        assert joined.count("active BOOLEAN NOT NULL") >= 1
        assert joined.count("SERIAL PRIMARY KEY") == 1


# --------------------------------------------------
# ROW COMPATIBILITY
# --------------------------------------------------


class TestRow:
    def test_name_and_positional_indexing(self):
        row = Row(["id", "name"], ["EXC-000001", "delay"])

        assert row["id"] == "EXC-000001"
        assert row["name"] == "delay"
        assert row[0] == "EXC-000001"
        assert row[1] == "delay"
        assert row[-1] == "delay"

    def test_slice_and_iteration(self):
        row = Row(["a", "b", "c"], [1, 2, 3])

        assert list(row[0:2]) == [1, 2]
        assert list(row) == [1, 2, 3]
        assert len(row) == 3
        assert tuple(row) == (1, 2, 3)

    def test_keys_items_dict(self):
        row = Row(["id", "k"], [7, "v"])

        assert row.keys() == ["id", "k"]
        assert row.items() == [("id", 7), ("k", "v")]
        assert dict(row) == {"id": 7, "k": "v"}
        assert "id" in row and "missing" not in row

    def test_missing_column_raises_index_error(self):
        row = Row(["id"], [1])

        try:
            row["nope"]
        except IndexError:
            pass
        else:
            raise AssertionError("expected IndexError")

    def test_bad_key_type_raises_type_error(self):
        row = Row(["id"], [1])

        try:
            row[1.5]
        except TypeError:
            pass
        else:
            raise AssertionError("expected TypeError")

    def test_equality_contract(self):
        row = Row(["a"], [1])

        assert row == Row(["a"], [1])
        assert row == (1,)
        assert row == [1]
        assert row != Row(["a"], [2])

    def test_boolean_values_preserved(self):
        # PostgreSQL BOOLEAN arrives as Python bool; the Row must
        # carry it unchanged so bool()/truthiness reads behave.
        row = Row(["feasible", "active"], [True, False])

        assert row["feasible"] is True
        assert row["active"] is False
