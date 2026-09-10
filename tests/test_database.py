import sqlite3
from pathlib import Path


# ==================================================
# DATABASE LOCATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "adensa.db"


# ==================================================
# EXPECTED DATABASE SCHEMA
# ==================================================

EXPECTED_SCHEMA = {
    "customers": [
        "customer_id",
        "customer_name",
        "customer_type",
        "country",
        "city",
        "service_level",
    ],

    "suppliers": [
        "supplier_id",
        "supplier_name",
        "country",
        "city",
        "reliability_score",
        "average_lead_time_days",
        "active",
    ],

    "products": [
        "product_id",
        "product_name",
        "category",
        "subcategory",
        "unit_weight_kg",
        "unit_volume_m3",
        "unit_value",
        "supplier_id",
        "lead_time_days",
        "reorder_point",
        "safety_stock",
        "active",
    ],

    "warehouses": [
        "warehouse_id",
        "warehouse_name",
        "city",
        "country",
        "capacity_units",
    ],

    "carriers": [
        "carrier_id",
        "carrier_name",
        "transport_modes",
        "reliability_score",
    ],

    "orders": [
        "order_id",
        "customer_id",
        "order_date",
        "required_delivery_date",
        "required_delivery_time",
        "service_level",
        "priority",
        "status",
        "warehouse_id",
    ],

    "order_items": [
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
    ],

    "inventory": [
        "inventory_id",
        "product_id",
        "warehouse_id",
        "quantity_on_hand",
        "quantity_reserved",
        "quantity_available",
        "reorder_point",
        "safety_stock",
        "inventory_status",
        "last_updated",
    ],

    "shipments": [
        "shipment_id",
        "order_id",
        "carrier_id",
        "origin",
        "destination",
        "transport_mode",
        "quantity",
        "weight_kg",
        "volume_m3",
        "priority",
        "planned_departure",
        "actual_departure",
        "planned_arrival",
        "estimated_arrival",
        "actual_arrival",
        "status",
        "shipping_cost",
        "distance_km",
        "current_location",
        "last_updated",
    ],

    "shipment_events": [
        "event_id",
        "shipment_id",
        "event_type",
        "event_timestamp",
        "location",
        "description",
    ],

    "exceptions": [
        "exception_id",
        "shipment_id",
        "exception_type",
        "severity",
        "detected_at",
        "description",
        "estimated_impact",
        "resolution_status",
        "resolved_at",
    ],

    "recovery_options": [
        "option_id",
        "exception_id",
        "transport_mode",
        "carrier_id",
        "estimated_cost",
        "estimated_transit_days",
        "capacity_available",
        "risk_score",
        "feasible",
    ],

    "recovery_actions": [
        "action_id",
        "exception_id",
        "option_id",
        "action_type",
        "description",
        "status",
        "approved_by",
        "approved_at",
        "executed_at",
    ],
}


# ==================================================
# CONNECT TO DATABASE
# ==================================================

connection = sqlite3.connect(DATABASE_PATH)
cursor = connection.cursor()

# Enable foreign-key enforcement for this connection
cursor.execute("PRAGMA foreign_keys = ON")


# ==================================================
# TEST 1 — TABLES
# ==================================================

cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    AND name != 'sqlite_sequence'
    ORDER BY name
""")

tables = {row[0] for row in cursor.fetchall()}

expected_tables = set(EXPECTED_SCHEMA.keys())

if tables == expected_tables:
    print("✓ All expected tables exist.")
else:
    print("✗ Table structure mismatch.")
    print("Missing:", expected_tables - tables)
    print("Unexpected:", tables - expected_tables)


# ==================================================
# TEST 2 — COLUMNS
# ==================================================

print("\nChecking columns...")

for table_name, expected_columns in EXPECTED_SCHEMA.items():

    cursor.execute(f"PRAGMA table_info({table_name})")

    actual_columns = [row[1] for row in cursor.fetchall()]

    if actual_columns == expected_columns:
        print(f"✓ {table_name}")
    else:
        print(f"✗ {table_name}")
        print("  Expected:", expected_columns)
        print("  Found:   ", actual_columns)


# ==================================================
# TEST 3 — FOREIGN KEYS
# ==================================================

print("\nChecking foreign keys...")

cursor.execute("PRAGMA foreign_keys")
foreign_keys_enabled = cursor.fetchone()[0]

if foreign_keys_enabled == 1:
    print("✓ Foreign-key enforcement is enabled.")
else:
    print("✗ Foreign-key enforcement is NOT enabled.")


# ==================================================
# CLOSE DATABASE
# ==================================================

connection.close()

print("\nDatabase schema validation complete.")