import sqlite3

connection = sqlite3.connect("data/adensa.db")

connection.row_factory = sqlite3.Row

# --------------------------------------------------
# BASIC VALIDATION
# --------------------------------------------------

checks = [
    (
        "Shipments",
        "SELECT COUNT(*) FROM shipments"
    ),
    (
        "Departure before order",
        """
        SELECT COUNT(*)
        FROM shipments s
        JOIN orders o
            ON s.order_id = o.order_id
        WHERE datetime(s.planned_departure) < datetime(o.order_date)
        """
    ),
    (
        "Arrival before departure",
        """
        SELECT COUNT(*)
        FROM shipments
        WHERE datetime(planned_arrival) < datetime(planned_departure)
        """
    ),
    (
        "Delayed shipments",
        """
        SELECT COUNT(*)
        FROM shipments
        WHERE status = 'Delayed'
        """
    ),
    (
        "Delivered without actual arrival",
        """
        SELECT COUNT(*)
        FROM shipments
        WHERE status = 'Delivered'
        AND actual_arrival IS NULL
        """
    )
]

print("\nShipment Validation")
print("=" * 40)

for name, query in checks:
    result = connection.execute(query).fetchone()[0]
    print(f"{name}: {result}")

# --------------------------------------------------
# SHOW EXAMPLES OF INVALID DATES
# --------------------------------------------------

print("\nExamples of invalid shipment dates")
print("=" * 40)

query = """
SELECT
    s.shipment_id,
    s.order_id,
    o.order_date,
    s.planned_departure,
    s.planned_arrival,
    o.required_delivery_date,
    s.transport_mode,
    s.status
FROM shipments s
JOIN orders o
    ON s.order_id = o.order_id
WHERE datetime(s.planned_departure) < datetime(o.order_date)
LIMIT 5
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['shipment_id']} | "
        f"Order: {row['order_date']} | "
        f"Departure: {row['planned_departure']} | "
        f"Arrival: {row['planned_arrival']} | "
        f"Required: {row['required_delivery_date']} | "
        f"Mode: {row['transport_mode']} | "
        f"Status: {row['status']}"
    )

connection.close()