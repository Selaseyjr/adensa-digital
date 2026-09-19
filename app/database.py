import logging
import sqlite3

from app.config import DATABASE_PATH

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
    """Create all Adensa Digital database tables."""

    # Make sure the data folder exists.
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection()
    cursor = connection.cursor()

    # ==================================================
    # 1. CUSTOMERS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            customer_type TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            service_level TEXT NOT NULL
        )
    """)

    # ==================================================
    # 2. SUPPLIERS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            supplier_name TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            reliability_score REAL NOT NULL,
            average_lead_time_days INTEGER NOT NULL,
            active INTEGER NOT NULL
        )
    """)

    # ==================================================
    # 3. PRODUCTS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            unit_weight_kg REAL NOT NULL,
            unit_volume_m3 REAL NOT NULL,
            unit_value REAL NOT NULL,
            supplier_id TEXT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL,
            safety_stock INTEGER NOT NULL,
            active INTEGER NOT NULL,

            FOREIGN KEY (supplier_id)
                REFERENCES suppliers(supplier_id)
        )
    """)

    # ==================================================
    # 4. WAREHOUSES
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warehouses (
            warehouse_id TEXT PRIMARY KEY,
            warehouse_name TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT NOT NULL,
            capacity_units INTEGER NOT NULL
        )
    """)

    # ==================================================
    # 5. CARRIERS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS carriers (
            carrier_id TEXT PRIMARY KEY,
            carrier_name TEXT NOT NULL,
            transport_modes TEXT NOT NULL,
            reliability_score REAL NOT NULL
        )
    """)

    # ==================================================
    # 6. ORDERS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            required_delivery_date TEXT NOT NULL,
            required_delivery_time TEXT NOT NULL,
            service_level TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            warehouse_id TEXT NOT NULL,

            FOREIGN KEY (customer_id)
                REFERENCES customers(customer_id),

            FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(warehouse_id)
        )
    """)

    # ==================================================
    # 7. ORDER ITEMS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            order_item_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,

            FOREIGN KEY (order_id)
                REFERENCES orders(order_id),

            FOREIGN KEY (product_id)
                REFERENCES products(product_id)
        )
    """)

    # ==================================================
    # 8. INVENTORY
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            warehouse_id TEXT NOT NULL,
            quantity_on_hand INTEGER NOT NULL,
            quantity_reserved INTEGER NOT NULL,
            quantity_available INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL,
            safety_stock INTEGER NOT NULL,
            inventory_status TEXT NOT NULL,
            last_updated TEXT NOT NULL,

            FOREIGN KEY (product_id)
                REFERENCES products(product_id),

            FOREIGN KEY (warehouse_id)
                REFERENCES warehouses(warehouse_id)
        )
    """)

    # ==================================================
    # 9. SHIPMENTS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            shipment_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            carrier_id TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            transport_mode TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            weight_kg REAL NOT NULL,
            volume_m3 REAL NOT NULL,
            priority TEXT NOT NULL,
            planned_departure TEXT NOT NULL,
            actual_departure TEXT,
            planned_arrival TEXT NOT NULL,
            estimated_arrival TEXT,
            actual_arrival TEXT,
            status TEXT NOT NULL,
            shipping_cost REAL NOT NULL,
            distance_km REAL NOT NULL,
            current_location TEXT NOT NULL,
            last_updated TEXT NOT NULL,

            FOREIGN KEY (order_id)
                REFERENCES orders(order_id),

            FOREIGN KEY (carrier_id)
                REFERENCES carriers(carrier_id)
        )
    """)

    # ==================================================
    # 10. SHIPMENT EVENTS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipment_events (
            event_id TEXT PRIMARY KEY,
            shipment_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,

            FOREIGN KEY (shipment_id)
                REFERENCES shipments(shipment_id)
        )
    """)

    # ==================================================
    # 11. EXCEPTIONS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exceptions (
            exception_id TEXT PRIMARY KEY,
            shipment_id TEXT NOT NULL,
            exception_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            description TEXT NOT NULL,
            estimated_impact REAL NOT NULL,
            resolution_status TEXT NOT NULL,
            resolved_at TEXT,

            FOREIGN KEY (shipment_id)
                REFERENCES shipments(shipment_id)
        )
    """)

    # ==================================================
    # 12. RECOVERY OPTIONS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recovery_options (
            option_id TEXT PRIMARY KEY,
            exception_id TEXT NOT NULL,
            transport_mode TEXT NOT NULL,
            carrier_id TEXT NOT NULL,
            estimated_cost REAL NOT NULL,
            estimated_transit_days REAL NOT NULL,
            capacity_available REAL NOT NULL,
            risk_score REAL NOT NULL,
            feasible INTEGER NOT NULL,

            FOREIGN KEY (exception_id)
                REFERENCES exceptions(exception_id),

            FOREIGN KEY (carrier_id)
                REFERENCES carriers(carrier_id)
        )
    """)

    # ==================================================
    # 13. RECOVERY ACTIONS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recovery_actions (
            action_id TEXT PRIMARY KEY,
            exception_id TEXT NOT NULL,
            option_id TEXT,
            action_type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            approved_by TEXT,
            approved_at TEXT,
            executed_at TEXT,

            FOREIGN KEY (exception_id)
                REFERENCES exceptions(exception_id),

            FOREIGN KEY (option_id)
                REFERENCES recovery_options(option_id)
        )
    """)

    # ==================================================
    # 14. MANUAL INTERVENTIONS
    # ==================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS manual_interventions (
            intervention_id TEXT PRIMARY KEY,
            exception_id TEXT NOT NULL,
            intervention_type TEXT NOT NULL,
            external_party TEXT NOT NULL,
            resolution_summary TEXT NOT NULL,
            new_expected_delivery TEXT,
            outcome TEXT NOT NULL,
            notes TEXT,
            recorded_by TEXT NOT NULL,
            recorded_at TEXT NOT NULL,

            FOREIGN KEY (exception_id)
                REFERENCES exceptions(exception_id)
        )
    """)

    # ==================================================
    # SAVE CHANGES
    # ==================================================

    connection.commit()
    connection.close()


# ==================================================
# RUN DATABASE INITIALIZATION
# ==================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_database()
    logger.info("Adensa Digital database initialized successfully.")