from app.config import DATABASE_PATH
from app.database import get_connection, initialize_database
from app.generate_data import (
    insert_master_data,
    generate_orders,
    generate_order_items,
    generate_inventory,
    generate_shipments,
    generate_shipment_events,
)
from app.detect_exceptions import detect_exceptions
from app.generate_recovery_options import generate_recovery_options
from app.workflow_engine import generate_workflow_actions


REQUIRED_TABLES = {
    "customers",
    "suppliers",
    "products",
    "warehouses",
    "carriers",
    "orders",
    "order_items",
    "inventory",
    "shipments",
    "shipment_events",
    "exceptions",
    "recovery_options",
    "recovery_actions",
}


def database_schema_exists():
    """
    Check whether the Adensa Digital database exists
    and contains all required tables.
    """
    if not DATABASE_PATH.exists():
        return False

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

        existing_tables = {row["name"] for row in rows}

        return REQUIRED_TABLES.issubset(existing_tables)

    finally:
        connection.close()


def database_contains_operational_data():
    """
    Check whether the database contains the core operational
    data required for the application to function.

    This prevents the bootstrap process from regenerating
    the database every time Streamlit reruns the application.
    """
    if not database_schema_exists():
        return False

    connection = get_connection()

    try:
        checks = {
            "customers": "SELECT COUNT(*) FROM customers",
            "products": "SELECT COUNT(*) FROM products",
            "orders": "SELECT COUNT(*) FROM orders",
            "shipments": "SELECT COUNT(*) FROM shipments",
            "shipment_events": "SELECT COUNT(*) FROM shipment_events",
            "exceptions": "SELECT COUNT(*) FROM exceptions",
            "recovery_options": "SELECT COUNT(*) FROM recovery_options",
        }

        for table, query in checks.items():
            count = connection.execute(query).fetchone()[0]

            if count == 0:
                return False

        return True

    finally:
        connection.close()


def initialize_adensa():
    """
    Initialize the complete Adensa Digital environment.

    On a fresh environment this will:

    1. Create the database schema
    2. Load master data
    3. Generate orders
    4. Generate order items
    5. Generate inventory
    6. Generate shipments
    7. Generate shipment events
    8. Detect shipment exceptions
    9. Generate recovery options
    10. Generate workflow actions

    If the database is already initialized, the function
    exits without regenerating the operational dataset.
    """

    if database_contains_operational_data():
        print("✓ Adensa Digital database already initialized.")
        return

    print("=" * 60)
    print("ADENSA DIGITAL INITIALIZATION")
    print("=" * 60)

    print("\n1. Initializing database schema...")
    initialize_database()

    connection = get_connection()

    try:
        print("\n2. Loading master data...")
        insert_master_data(connection)

        print("\n3. Generating orders...")
        generate_orders(
            connection,
            number_of_orders=5000,
        )

        print("\n4. Generating order items...")
        generate_order_items(connection)

        print("\n5. Generating inventory...")
        generate_inventory(connection)

        print("\n6. Generating shipments...")
        generate_shipments(
            connection,
            number_of_shipments=5000,
        )

        print("\n7. Generating shipment events...")
        generate_shipment_events(connection)

        print("\n8. Detecting shipment exceptions...")
        detect_exceptions(connection)

        print("\n9. Generating recovery options...")
        generate_recovery_options(connection)

        print("\n10. Generating workflow actions...")
        generate_workflow_actions(connection)

        print("\n" + "=" * 60)
        print("ADENSA DIGITAL INITIALIZATION COMPLETE")
        print("=" * 60)

    finally:
        connection.close()