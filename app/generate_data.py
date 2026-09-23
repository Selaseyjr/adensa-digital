import logging
import random
from datetime import datetime, timedelta

from app.database import get_connection


# ==================================================
# CONFIGURATION
# ==================================================

# Makes generated data reproducible
random.seed(42)

logger = logging.getLogger(__name__)


# ==================================================
# MASTER DATA
# ==================================================

CUSTOMERS = [
    ("CUST-001", "Nordic Electronics GmbH", "Enterprise", "Germany", "Frankfurt", "Premium"),
    ("CUST-002", "EuroTech Distribution AG", "Distributor", "Germany", "Hamburg", "Standard"),
    ("CUST-003", "Medion Systems Europe", "Enterprise", "Germany", "Essen", "Premium"),
    ("CUST-004", "Alpine Digital Solutions", "Enterprise", "Switzerland", "Zurich", "Premium"),
    ("CUST-005", "Iberia Tech Retail", "Retailer", "Spain", "Madrid", "Standard"),
    ("CUST-006", "Paris Connected Systems", "Enterprise", "France", "Paris", "Premium"),
    ("CUST-007", "Milano Device Group", "Distributor", "Italy", "Milan", "Standard"),
    ("CUST-008", "Benelux Smart Devices", "Distributor", "Netherlands", "Amsterdam", "Standard"),
    ("CUST-009", "Central Europe Components", "Manufacturer", "Czech Republic", "Prague", "Standard"),
    ("CUST-010", "Rhein Digital Commerce", "Retailer", "Germany", "Cologne", "Premium"),
]


SUPPLIERS = [
    ("SUP-001", "Shenzhen Precision Electronics", "China", "Shenzhen", 0.94, 18, 1),
    ("SUP-002", "Shanghai Advanced Components", "China", "Shanghai", 0.91, 21, 1),
    ("SUP-003", "Seoul Semiconductor Systems", "South Korea", "Seoul", 0.96, 14, 1),
    ("SUP-004", "Tokyo Micro Devices", "Japan", "Tokyo", 0.97, 16, 1),
    ("SUP-005", "Singapore Integrated Supply", "Singapore", "Singapore", 0.93, 19, 1),
    ("SUP-006", "Guangzhou Smart Components", "China", "Guangzhou", 0.89, 23, 1),
]


PRODUCTS = [
    ("PROD-001", "Smartphone Display Module", "Electronics", "Displays", 0.18, 0.0012, 145.00, "SUP-001", 18, 500, 250, 1),
    ("PROD-002", "Lithium Battery Pack", "Electronics", "Batteries", 0.42, 0.0025, 85.00, "SUP-002", 21, 800, 400, 1),
    ("PROD-003", "Wireless Communication Chip", "Electronics", "Semiconductors", 0.03, 0.0001, 42.00, "SUP-003", 14, 1500, 700, 1),
    ("PROD-004", "Camera Sensor Module", "Electronics", "Sensors", 0.08, 0.0004, 68.00, "SUP-004", 16, 900, 450, 1),
    ("PROD-005", "USB-C Power Controller", "Electronics", "Power Components", 0.02, 0.00008, 18.00, "SUP-005", 19, 2000, 1000, 1),
    ("PROD-006", "5G Antenna Module", "Electronics", "Communication", 0.06, 0.0003, 31.00, "SUP-003", 14, 1200, 600, 1),
    ("PROD-007", "Memory Module 16GB", "Electronics", "Memory", 0.04, 0.0002, 29.00, "SUP-002", 21, 1800, 900, 1),
    ("PROD-008", "Smartphone Mainboard", "Electronics", "Circuit Boards", 0.22, 0.0015, 190.00, "SUP-001", 18, 600, 300, 1),
    ("PROD-009", "Fingerprint Sensor", "Electronics", "Sensors", 0.015, 0.00005, 22.00, "SUP-004", 16, 1300, 650, 1),
    ("PROD-010", "Fast Charging Module", "Electronics", "Power Components", 0.07, 0.00035, 35.00, "SUP-006", 23, 1000, 500, 1),
]


WAREHOUSES = [
    ("WH-001", "Frankfurt Central Distribution Center", "Frankfurt", "Germany", 50000),
    ("WH-002", "Hamburg Northern Distribution Center", "Hamburg", "Germany", 40000),
    ("WH-003", "Rotterdam European Hub", "Rotterdam", "Netherlands", 60000),
    ("WH-004", "Milan Southern Distribution Center", "Milan", "Italy", 35000),
    ("WH-005", "Paris Western Distribution Center", "Paris", "France", 45000),
]


CARRIERS = [
    ("CAR-001", "DHL Global Forwarding", "Air,Sea,Road,Rail", 0.95),
    ("CAR-002", "Kuehne + Nagel", "Air,Sea,Road,Rail", 0.93),
    ("CAR-003", "DB Schenker", "Air,Sea,Road,Rail", 0.91),
    ("CAR-004", "Maersk Logistics", "Sea,Road,Rail", 0.89),
    ("CAR-005", "DSV", "Air,Sea,Road,Rail", 0.92),
    ("CAR-006", "CMA CGM Logistics", "Sea,Road,Rail", 0.88),
]


# ==================================================
# INSERT MASTER DATA
# ==================================================

def insert_master_data(connection):
    """Insert master data safely without creating duplicates."""

    cursor = connection.cursor()

    # --------------------------------------------------
    # Customers
    # --------------------------------------------------

    cursor.executemany("""
        INSERT OR IGNORE INTO customers (
            customer_id,
            customer_name,
            customer_type,
            country,
            city,
            service_level
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, CUSTOMERS)

    # --------------------------------------------------
    # Suppliers
    # --------------------------------------------------

    # Boolean columns bind real booleans: SQLite stores them
    # as 0/1 exactly as before; PostgreSQL requires true/false
    # for its BOOLEAN columns (P5.3 type decision).
    cursor.executemany(
        """
        INSERT OR IGNORE INTO suppliers (
            supplier_id,
            supplier_name,
            country,
            city,
            reliability_score,
            average_lead_time_days,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        [
            (supplier_id, supplier_name, country, city,
             reliability_score, average_lead_time_days, bool(active))
            for (
                supplier_id,
                supplier_name,
                country,
                city,
                reliability_score,
                average_lead_time_days,
                active,
            ) in SUPPLIERS
        ],
    )

    # --------------------------------------------------
    # Products
    # --------------------------------------------------

    cursor.executemany(
        """
        INSERT OR IGNORE INTO products (
            product_id,
            product_name,
            category,
            subcategory,
            unit_weight_kg,
            unit_volume_m3,
            unit_value,
            supplier_id,
            lead_time_days,
            reorder_point,
            safety_stock,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            (
                product_id,
                product_name,
                category,
                subcategory,
                unit_weight_kg,
                unit_volume_m3,
                unit_value,
                supplier_id,
                lead_time_days,
                reorder_point,
                safety_stock,
                bool(active),
            )
            for (
                product_id,
                product_name,
                category,
                subcategory,
                unit_weight_kg,
                unit_volume_m3,
                unit_value,
                supplier_id,
                lead_time_days,
                reorder_point,
                safety_stock,
                active,
            ) in PRODUCTS
        ],
    )

    # --------------------------------------------------
    # Warehouses
    # --------------------------------------------------

    cursor.executemany("""
        INSERT OR IGNORE INTO warehouses (
            warehouse_id,
            warehouse_name,
            city,
            country,
            capacity_units
        )
        VALUES (?, ?, ?, ?, ?)
    """, WAREHOUSES)

    # --------------------------------------------------
    # Carriers
    # --------------------------------------------------

    cursor.executemany("""
        INSERT OR IGNORE INTO carriers (
            carrier_id,
            carrier_name,
            transport_modes,
            reliability_score
        )
        VALUES (?, ?, ?, ?)
    """, CARRIERS)

    connection.commit()

    logger.info("✓ Master data verified")


# ==================================================
# GENERATE ORDERS
# ==================================================

def generate_orders(connection, number_of_orders=5000):
    """Generate customer orders if they do not already exist."""

    cursor = connection.cursor()

    # Check how many orders already exist
    cursor.execute("SELECT COUNT(*) FROM orders")
    existing_orders = cursor.fetchone()[0]

    if existing_orders >= number_of_orders:
        logger.info(
            f"✓ Orders already contain "
            f"{existing_orders:,} records"
        )
        return

    # Existing order IDs
    cursor.execute("SELECT order_id FROM orders")

    existing_ids = {
        row["order_id"]
        for row in cursor.fetchall()
    }

    # Get customer IDs
    customer_ids = [
        row["customer_id"]
        for row in cursor.execute(
            "SELECT customer_id FROM customers"
        ).fetchall()
    ]

    # Get warehouse IDs
    warehouse_ids = [
        row["warehouse_id"]
        for row in cursor.execute(
            "SELECT warehouse_id FROM warehouses"
        ).fetchall()
    ]

    orders = []

    start_date = datetime(2026, 1, 1)

    for i in range(1, number_of_orders + 1):

        order_id = f"ORD-{i:05d}"

        # Skip an order that already exists
        if order_id in existing_ids:
            continue

        customer_id = random.choice(customer_ids)
        warehouse_id = random.choice(warehouse_ids)

        # Generate order date
        order_date = start_date + timedelta(
            days=random.randint(0, 240)
        )

        # Required delivery
        delivery_days = random.randint(5, 20)

        required_delivery = order_date + timedelta(
            days=delivery_days
        )

        # Service level
        service_level = random.choice([
            "Standard",
            "Standard",
            "Standard",
            "Premium",
        ])

        # Priority
        if service_level == "Premium":
            priority = random.choice([
                "High",
                "High",
                "Medium",
            ])
        else:
            priority = random.choice([
                "Low",
                "Medium",
                "Medium",
                "High",
            ])

        # Order status
        status = random.choice([
            "Confirmed",
            "Confirmed",
            "Processing",
            "Shipped",
        ])

        orders.append((
            order_id,
            customer_id,
            order_date.strftime("%Y-%m-%d"),
            required_delivery.strftime("%Y-%m-%d"),
            random.choice([
                "09:00",
                "10:00",
                "12:00",
                "14:00",
                "16:00",
            ]),
            service_level,
            priority,
            status,
            warehouse_id,
        ))

    # Insert orders
    cursor.executemany("""
        INSERT INTO orders (
            order_id,
            customer_id,
            order_date,
            required_delivery_date,
            required_delivery_time,
            service_level,
            priority,
            status,
            warehouse_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, orders)

    connection.commit()

    logger.info(
        f"✓ {len(orders):,} new orders generated"
    )


# ==================================================
# GENERATE ORDER ITEMS
# ==================================================

def generate_order_items(connection):
    """Generate 1–3 products for each order."""

    cursor = connection.cursor()

    # Get all existing orders
    cursor.execute("""
        SELECT order_id
        FROM orders
        ORDER BY order_id
    """)

    orders = [
        row["order_id"]
        for row in cursor.fetchall()
    ]

    # Get products and their unit values
    cursor.execute("""
        SELECT product_id, unit_value
        FROM products
        WHERE active = 1
    """)

    products = cursor.fetchall()

    # Find orders that already have items
    cursor.execute("""
        SELECT DISTINCT order_id
        FROM order_items
    """)

    existing_orders = {
        row["order_id"]
        for row in cursor.fetchall()
    }

    # Find the highest existing item ID
    cursor.execute("""
        SELECT order_item_id
        FROM order_items
        ORDER BY order_item_id DESC
        LIMIT 1
    """)

    last_item = cursor.fetchone()

    if last_item:
        last_number = int(
            last_item["order_item_id"].split("-")[1]
        )
    else:
        last_number = 0

    new_items = []

    for order_id in orders:

        # Skip orders that already have items
        if order_id in existing_orders:
            continue

        # Each order contains 1–3 different products
        number_of_items = random.randint(1, 3)

        selected_products = random.sample(
            products,
            number_of_items
        )

        for product in selected_products:

            product_id = product["product_id"]
            unit_value = product["unit_value"]

            # Higher-value products are generally
            # ordered in smaller quantities.
            if unit_value >= 100:
                quantity = random.randint(50, 500)

            elif unit_value >= 50:
                quantity = random.randint(100, 800)

            elif unit_value >= 30:
                quantity = random.randint(200, 1200)

            else:
                quantity = random.randint(300, 2000)

            # Add small commercial price variation
            unit_price = round(
                unit_value * random.uniform(0.95, 1.05),
                2
            )

            last_number += 1
            order_item_id = f"ITEM-{last_number:05d}"

            new_items.append((
                order_item_id,
                order_id,
                product_id,
                quantity,
                unit_price
            ))

    # Insert generated items
    if new_items:

        cursor.executemany("""
            INSERT INTO order_items (
                order_item_id,
                order_id,
                product_id,
                quantity,
                unit_price
            )
            VALUES (?, ?, ?, ?, ?)
        """, new_items)

        connection.commit()

        logger.info(
            f"✓ Added {len(new_items):,} order items"
        )

    else:
        logger.info(
            "✓ Order items already exist for all orders"
        )


# ==================================================
# GENERATE INVENTORY
# ==================================================

def generate_inventory(connection):
    """Generate inventory records for each product and warehouse."""

    cursor = connection.cursor()

    # Get all active products
    cursor.execute("""
        SELECT product_id, reorder_point, safety_stock
        FROM products
        WHERE active = 1
    """)

    products = cursor.fetchall()

    # Get all warehouses
    cursor.execute("""
        SELECT warehouse_id
        FROM warehouses
    """)

    warehouses = cursor.fetchall()

    # Check whether inventory already exists
    cursor.execute("""
        SELECT COUNT(*) AS count
        FROM inventory
    """)

    existing_count = cursor.fetchone()["count"]

    expected_count = len(products) * len(warehouses)

    if existing_count >= expected_count:
        logger.info(
            f"✓ Inventory already contains "
            f"{existing_count:,} records"
        )
        return

    # Find the next inventory ID
    cursor.execute("""
        SELECT inventory_id
        FROM inventory
        ORDER BY inventory_id DESC
        LIMIT 1
    """)

    last_inventory = cursor.fetchone()

    if last_inventory:
        next_id = last_inventory["inventory_id"] + 1
    else:
        next_id = 1

    new_inventory = []

    # Create inventory for every product
    # at every warehouse
    for product in products:

        product_id = product["product_id"]
        reorder_point = product["reorder_point"]
        safety_stock = product["safety_stock"]

        for warehouse in warehouses:

            warehouse_id = warehouse["warehouse_id"]

            # Generate realistic stock levels
            quantity_on_hand = random.randint(
                safety_stock,
                reorder_point * 4
            )

            # Some inventory is already reserved
            quantity_reserved = random.randint(
                0,
                max(
                    1,
                    int(quantity_on_hand * 0.4)
                )
            )

            quantity_available = (
                quantity_on_hand
                - quantity_reserved
            )

            # Determine inventory status
            if quantity_available <= safety_stock:
                inventory_status = "Critical"

            elif quantity_available <= reorder_point:
                inventory_status = "Low"

            elif quantity_available >= reorder_point * 3:
                inventory_status = "Overstocked"

            else:
                inventory_status = "Healthy"

            new_inventory.append((
                next_id,
                product_id,
                warehouse_id,
                quantity_on_hand,
                quantity_reserved,
                quantity_available,
                reorder_point,
                safety_stock,
                inventory_status,
                "2026-09-10 12:00:00"
            ))

            next_id += 1

    # Insert inventory records
    cursor.executemany("""
        INSERT INTO inventory (
            inventory_id,
            product_id,
            warehouse_id,
            quantity_on_hand,
            quantity_reserved,
            quantity_available,
            reorder_point,
            safety_stock,
            inventory_status,
            last_updated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, new_inventory)

    connection.commit()

    logger.info(
        f"✓ Added {len(new_inventory):,} inventory records"
    )

# ==================================================
# GENERATE SHIPMENTS
# ==================================================

def generate_shipments(connection, number_of_shipments=5000):
    cursor = connection.cursor()

    # --------------------------------------------------
    # CHECK EXISTING SHIPMENTS
    # --------------------------------------------------

    cursor.execute("SELECT COUNT(*) FROM shipments")
    existing_count = cursor.fetchone()[0]

    if existing_count >= number_of_shipments:
        logger.info(
            f"✓ Shipments already contain "
            f"{existing_count:,} records"
        )
        return

    # --------------------------------------------------
    # LOAD ORDERS
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            order_id,
            order_date,
            required_delivery_date,
            priority,
            warehouse_id
        FROM orders
        ORDER BY order_id
        LIMIT ?
    """, (number_of_shipments,))

    orders = cursor.fetchall()

    if not orders:
        logger.warning("⚠ No orders found. Generate orders first.")
        return

    # --------------------------------------------------
    # LOAD ORDER ITEMS
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            oi.order_id,
            oi.quantity,
            p.unit_weight_kg,
            p.unit_volume_m3
        FROM order_items oi
        JOIN products p
            ON oi.product_id = p.product_id
    """)

    order_items = cursor.fetchall()

    items_by_order = {}

    for item in order_items:

        order_id = item["order_id"]

        if order_id not in items_by_order:
            items_by_order[order_id] = []

        items_by_order[order_id].append(item)

    # --------------------------------------------------
    # LOAD CARRIERS
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            carrier_id,
            carrier_name,
            transport_modes,
            reliability_score
        FROM carriers
    """)

    carriers = cursor.fetchall()

    # --------------------------------------------------
    # TRANSPORT PROFILES
    # --------------------------------------------------

    transport_profiles = {

        "Sea": {
            "transit_days": (25, 40),
            "cost_per_km_kg": 0.03
        },

        "Air": {
            "transit_days": (3, 8),
            "cost_per_km_kg": 0.22
        },

        "Road": {
            "transit_days": (2, 6),
            "cost_per_km_kg": 0.10
        },

        "Rail": {
            "transit_days": (12, 20),
            "cost_per_km_kg": 0.07
        }
    }

    # --------------------------------------------------
    # ORIGINS
    # --------------------------------------------------

    origins = [
        "Shenzhen",
        "Shanghai",
        "Singapore",
        "Seoul",
        "Tokyo"
    ]

    # --------------------------------------------------
    # DISTANCE RANGES
    # --------------------------------------------------

    distance_ranges = {

        "Shenzhen": (8500, 10000),
        "Shanghai": (8500, 10000),
        "Singapore": (10000, 12000),
        "Seoul": (8500, 10500),
        "Tokyo": (9500, 11500)
    }

    # --------------------------------------------------
    # STARTING SHIPMENT ID
    # --------------------------------------------------

    cursor.execute("""
        SELECT shipment_id
        FROM shipments
        ORDER BY shipment_id DESC
        LIMIT 1
    """)

    last_shipment = cursor.fetchone()

    if last_shipment:

        try:

            last_number = int(
                last_shipment["shipment_id"].split("-")[1]
            )

        except (ValueError, IndexError):

            last_number = 0

    else:

        last_number = 0

    # --------------------------------------------------
    # GENERATE SHIPMENTS
    # --------------------------------------------------

    shipment_records = []

    for index, order in enumerate(orders, start=1):

        order_id = order["order_id"]

        # --------------------------------------------------
        # DATES
        # --------------------------------------------------

        order_date = datetime.strptime(
            order["order_date"],
            "%Y-%m-%d"
        )

        required_delivery_date = datetime.strptime(
            order["required_delivery_date"],
            "%Y-%m-%d"
        )

        priority = order["priority"]
        warehouse_id = order["warehouse_id"]

        # --------------------------------------------------
        # DESTINATION
        # --------------------------------------------------

        cursor.execute("""
            SELECT city
            FROM warehouses
            WHERE warehouse_id = ?
        """, (warehouse_id,))

        warehouse = cursor.fetchone()

        if warehouse:

            destination = warehouse["city"]

        else:

            destination = random.choice([
                "Frankfurt",
                "Hamburg",
                "Rotterdam",
                "Milan",
                "Paris"
            ])

        # --------------------------------------------------
        # ORIGIN
        # --------------------------------------------------

        origin = random.choice(origins)

        distance_min, distance_max = distance_ranges[origin]

        distance_km = random.randint(
            distance_min,
            distance_max
        )

        # --------------------------------------------------
        # AVAILABLE DELIVERY WINDOW
        # --------------------------------------------------

        available_days = (
            required_delivery_date - order_date
        ).days

        # --------------------------------------------------
        # TRANSPORT MODE
        # --------------------------------------------------

        if priority == "High":

            preferred_modes = [
                "Air",
                "Road",
                "Sea",
                "Rail"
            ]

            weights = [
                35,
                25,
                25,
                15
            ]

        else:

            preferred_modes = [
                "Sea",
                "Road",
                "Air",
                "Rail"
            ]

            weights = [
                45,
                25,
                15,
                15
            ]

        transport_mode = random.choices(
            preferred_modes,
            weights=weights,
            k=1
        )[0]

        profile = transport_profiles[transport_mode]

        # --------------------------------------------------
        # CHECK WHETHER MODE FITS DELIVERY WINDOW
        # --------------------------------------------------

        minimum_transit = profile["transit_days"][0]

        if available_days <= minimum_transit + 3:

            # Tight delivery window:
            # choose a faster transport mode.

            if available_days <= 8:

                transport_mode = random.choice([
                    "Air",
                    "Road"
                ])

            elif available_days <= 15:

                transport_mode = random.choice([
                    "Air",
                    "Road",
                    "Rail"
                ])

            else:

                transport_mode = random.choice([
                    "Air",
                    "Road",
                    "Rail",
                    "Sea"
                ])

            profile = transport_profiles[transport_mode]

        # --------------------------------------------------
        # TRANSIT TIME
        # --------------------------------------------------

        transit_days = random.randint(
            profile["transit_days"][0],
            profile["transit_days"][1]
        )

        # --------------------------------------------------
        # PREPARATION TIME
        # --------------------------------------------------

        preparation_days = random.randint(1, 3)

        earliest_departure = (
            order_date
            + timedelta(days=preparation_days)
        )

        # --------------------------------------------------
        # PLAN TO ARRIVE BEFORE COMMITMENT
        # --------------------------------------------------

        target_arrival = (
            required_delivery_date
            - timedelta(days=random.randint(2, 5))
        )

        planned_departure = (
            target_arrival
            - timedelta(days=transit_days)
        )

        # Shipment cannot depart before order preparation.

        if planned_departure < earliest_departure:

            planned_departure = earliest_departure

            planned_arrival = (
                planned_departure
                + timedelta(days=transit_days)
            )

        else:

            planned_arrival = target_arrival

        # --------------------------------------------------
        # WEIGHT / VOLUME / QUANTITY
        # --------------------------------------------------

        total_quantity = 0
        total_weight = 0
        total_volume = 0

        for item in items_by_order.get(order_id, []):

            quantity = item["quantity"]

            unit_weight = item["unit_weight_kg"] or 0
            unit_volume = item["unit_volume_m3"] or 0

            total_quantity += quantity
            total_weight += quantity * unit_weight
            total_volume += quantity * unit_volume

        total_quantity = max(
            total_quantity,
            1
        )

        total_weight = max(
            total_weight,
            1
        )

        total_volume = max(
            total_volume,
            0.01
        )

        # --------------------------------------------------
        # CARRIER
        # --------------------------------------------------

        compatible_carriers = [

            carrier

            for carrier in carriers

            if transport_mode.lower()
            in carrier["transport_modes"].lower()
        ]

        if compatible_carriers:

            carrier = random.choice(
                compatible_carriers
            )

        else:

            carrier = random.choice(
                carriers
            )

        carrier_id = carrier["carrier_id"]

        reliability = carrier["reliability_score"]

        # --------------------------------------------------
        # DELAY PROBABILITY
        # --------------------------------------------------

        delay_probability = (
            0.18
            - (reliability * 0.0005)
        )

        # Sea has slightly greater operational exposure.

        if transport_mode == "Sea":

            delay_probability += 0.05

        # High-priority shipments receive
        # stronger operational protection.

        if priority == "High":

            delay_probability *= 0.65

        delay_probability = max(
            0.08,
            min(
                0.25,
                delay_probability
            )
        )

        is_delayed = (
            random.random()
            < delay_probability
        )

        # --------------------------------------------------
        # ARRIVAL OUTCOME
        # --------------------------------------------------

        if is_delayed:

            delay_days = random.choices(
                [1, 2, 3, 4, 5, 6, 7, 8],
                weights=[
                    25,
                    22,
                    18,
                    12,
                    9,
                    6,
                    5,
                    3
                ],
                k=1
            )[0]

            estimated_arrival = (
                planned_arrival
                + timedelta(days=delay_days)
            )

            actual_arrival = None

            status = "Delayed"

        else:

            if random.random() < 0.40:

                actual_arrival = (
                    planned_arrival
                    + timedelta(
                        days=random.choice([
                            -1,
                            0,
                            0,
                            1
                        ])
                    )
                )

                estimated_arrival = actual_arrival

                status = "Delivered"

            else:

                estimated_arrival = (
                    planned_arrival
                    + timedelta(
                        days=random.choice([
                            -1,
                            0,
                            0,
                            1
                        ])
                    )
                )

                actual_arrival = None

                status = "In Transit"

        # --------------------------------------------------
        # ACTUAL DEPARTURE
        # --------------------------------------------------

        actual_departure = (
            planned_departure
            + timedelta(
                days=random.choice([
                    0,
                    0,
                    0,
                    1
                ])
            )
        )

        if actual_departure <= order_date:

            actual_departure = (
                order_date
                + timedelta(days=1)
            )

        # --------------------------------------------------
        # CURRENT LOCATION
        # --------------------------------------------------

        if status == "Delivered":

            current_location = destination

        elif status == "Delayed":

            current_location = random.choice([
                origin,
                "Transit Hub",
                "Customs",
                "European Hub"
            ])

        else:

            current_location = random.choice([
                origin,
                "Transit Hub",
                "En Route",
                "European Hub"
            ])

        # --------------------------------------------------
        # SHIPPING COST
        # --------------------------------------------------

        base_cost = (
            distance_km
            * profile["cost_per_km_kg"]
            * total_weight
        )

        shipping_cost = round(
            base_cost
            * random.uniform(0.85, 1.15),
            2
        )

        # --------------------------------------------------
        # SHIPMENT ID
        # --------------------------------------------------

        shipment_number = (
            last_number + index
        )

        shipment_id = (
            f"SHP-{shipment_number:05d}"
        )

        # --------------------------------------------------
        # RECORD
        # --------------------------------------------------

        shipment_records.append((
            shipment_id,
            order_id,
            carrier_id,
            origin,
            destination,
            transport_mode,
            total_quantity,
            round(total_weight, 2),
            round(total_volume, 3),
            priority,
            planned_departure.strftime(
                "%Y-%m-%d"
            ),
            actual_departure.strftime(
                "%Y-%m-%d"
            ),
            planned_arrival.strftime(
                "%Y-%m-%d"
            ),
            estimated_arrival.strftime(
                "%Y-%m-%d"
            ),
            actual_arrival.strftime(
                "%Y-%m-%d"
            )
            if actual_arrival
            else None,
            status,
            shipping_cost,
            distance_km,
            current_location,
            "2026-09-10 12:00:00"
        ))

    # --------------------------------------------------
    # INSERT SHIPMENTS
    # --------------------------------------------------

    cursor.executemany("""
        INSERT INTO shipments (
            shipment_id,
            order_id,
            carrier_id,
            origin,
            destination,
            transport_mode,
            quantity,
            weight_kg,
            volume_m3,
            priority,
            planned_departure,
            actual_departure,
            planned_arrival,
            estimated_arrival,
            actual_arrival,
            status,
            shipping_cost,
            distance_km,
            current_location,
            last_updated
        )
        VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, shipment_records)

    connection.commit()

    logger.info(
        f"✓ Added "
        f"{len(shipment_records):,} shipments"
    )

def generate_shipment_events(connection):
    cursor = connection.cursor()

    # --------------------------------------------------
    # CHECK EXISTING EVENTS
    # --------------------------------------------------
    cursor.execute("SELECT COUNT(*) FROM shipment_events")
    existing_count = cursor.fetchone()[0]

    if existing_count > 0:
        logger.info(
            f"✓ Shipment events already contain "
            f"{existing_count:,} records"
        )
        return

    # --------------------------------------------------
    # LOAD SHIPMENTS
    # --------------------------------------------------
    cursor.execute("""
        SELECT
            shipment_id,
            origin,
            destination,
            transport_mode,
            planned_departure,
            planned_arrival,
            estimated_arrival,
            status
        FROM shipments
        ORDER BY shipment_id
    """)

    shipments = cursor.fetchall()

    if not shipments:
        logger.warning("⚠ No shipments found. Generate shipments first.")
        return

    # --------------------------------------------------
    # EVENT TYPES
    # --------------------------------------------------
    event_records = []

    event_id = 1

    for shipment in shipments:

        shipment_id = shipment["shipment_id"]
        origin = shipment["origin"]
        destination = shipment["destination"]
        transport_mode = shipment["transport_mode"]

        planned_departure = datetime.strptime(
            shipment["planned_departure"],
            "%Y-%m-%d"
        )

        planned_arrival = datetime.strptime(
            shipment["planned_arrival"],
            "%Y-%m-%d"
        )

        estimated_arrival = datetime.strptime(
            shipment["estimated_arrival"],
            "%Y-%m-%d"
        )

        status = shipment["status"]

        # --------------------------------------------------
        # 1. SHIPMENT CREATED
        # --------------------------------------------------
        created_time = (
            planned_departure
            - timedelta(days=random.randint(1, 3))
        )

        event_records.append((
            f"EVT-{event_id:06d}",
            shipment_id,
            "Shipment Created",
            created_time.strftime("%Y-%m-%d %H:%M:%S"),
            origin,
            "Shipment created and scheduled for transportation."
        ))

        event_id += 1

        # --------------------------------------------------
        # 2. DEPARTED ORIGIN
        # --------------------------------------------------
        departure_time = planned_departure

        event_records.append((
            f"EVT-{event_id:06d}",
            shipment_id,
            "Departed Origin",
            departure_time.strftime("%Y-%m-%d %H:%M:%S"),
            origin,
            f"Shipment departed {origin} by {transport_mode}."
        ))

        event_id += 1

        # --------------------------------------------------
        # 3. TRANSIT / HUB EVENT
        # --------------------------------------------------
        transit_days = max(
            1,
            (planned_arrival - planned_departure).days
        )

        hub_offset = max(
            1,
            int(transit_days * 0.35)
        )

        hub_time = (
            planned_departure
            + timedelta(days=hub_offset)
        )

        event_records.append((
            f"EVT-{event_id:06d}",
            shipment_id,
            "Transit Hub",
            hub_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Transit Hub",
            "Shipment processed through an intermediate logistics hub."
        ))

        event_id += 1

        # --------------------------------------------------
        # 4. CUSTOMS / BORDER EVENT
        # --------------------------------------------------
        customs_offset = max(
            hub_offset + 1,
            int(transit_days * 0.65)
        )

        customs_time = (
            planned_departure
            + timedelta(days=customs_offset)
        )

        event_records.append((
            f"EVT-{event_id:06d}",
            shipment_id,
            "Customs Processing",
            customs_time.strftime("%Y-%m-%d %H:%M:%S"),
            "European Customs",
            "Shipment entered customs processing."
        ))

        event_id += 1

        # --------------------------------------------------
        # 5. DELAY EVENT
        # --------------------------------------------------
        if status == "Delayed":

            delay_days = max(
                1,
                (estimated_arrival - planned_arrival).days
            )

            delay_time = (
                planned_arrival
                - timedelta(days=delay_days)
            )

            event_records.append((
                f"EVT-{event_id:06d}",
                shipment_id,
                "Delay Detected",
                delay_time.strftime("%Y-%m-%d %H:%M:%S"),
                "European Customs",
                f"Shipment delayed. Estimated arrival moved "
                f"by {delay_days} day(s)."
            ))

            event_id += 1

        # --------------------------------------------------
        # 6. ARRIVAL EVENT
        # --------------------------------------------------
        if status == "Delivered":

            arrival_time = estimated_arrival

            event_records.append((
                f"EVT-{event_id:06d}",
                shipment_id,
                "Delivered",
                arrival_time.strftime("%Y-%m-%d %H:%M:%S"),
                destination,
                f"Shipment delivered to {destination}."
            ))

            event_id += 1

        elif status == "In Transit":

            event_records.append((
                f"EVT-{event_id:06d}",
                shipment_id,
                "In Transit",
                estimated_arrival.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "En Route",
                "Shipment remains in transit toward destination."
            ))

            event_id += 1

        elif status == "Delayed":

            event_records.append((
                f"EVT-{event_id:06d}",
                shipment_id,
                "Arrival Forecast Revised",
                estimated_arrival.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "European Hub",
                "Estimated arrival updated following shipment delay."
            ))

            event_id += 1

    # --------------------------------------------------
    # INSERT EVENTS
    # --------------------------------------------------
    cursor.executemany("""
        INSERT INTO shipment_events (
            event_id,
            shipment_id,
            event_type,
            event_timestamp,
            location,
            description
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, event_records)

    connection.commit()

    logger.info(
        f"✓ Added {len(event_records):,} shipment events"
    )

# ==================================================
# MAIN EXECUTION
# ==================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    connection = get_connection()

    try:
        insert_master_data(connection)
        generate_orders(connection, number_of_orders=5000)
        generate_order_items(connection)
        generate_inventory(connection)
        generate_shipments(connection, number_of_shipments=5000)
        generate_shipment_events(connection)

    finally:
        connection.close()

    logger.info("Data generation complete.")