import sqlite3

connection = sqlite3.connect("data/adensa.db")
connection.row_factory = sqlite3.Row


checks = [
    (
        "Total shipment events",
        """
        SELECT COUNT(*)
        FROM shipment_events
        """
    ),
    (
        "Events without valid shipment",
        """
        SELECT COUNT(*)
        FROM shipment_events se
        LEFT JOIN shipments s
            ON se.shipment_id = s.shipment_id
        WHERE s.shipment_id IS NULL
        """
    ),
    (
        "Delayed shipments without delay event",
        """
        SELECT COUNT(*)
        FROM shipments s
        LEFT JOIN shipment_events se
            ON s.shipment_id = se.shipment_id
            AND se.event_type = 'Delay Detected'
        WHERE s.status = 'Delayed'
        AND se.event_id IS NULL
        """
    ),
    (
        "Delivered shipments without delivered event",
        """
        SELECT COUNT(*)
        FROM shipments s
        LEFT JOIN shipment_events se
            ON s.shipment_id = se.shipment_id
            AND se.event_type = 'Delivered'
        WHERE s.status = 'Delivered'
        AND se.event_id IS NULL
        """
    ),
    (
        "Shipments with no events",
        """
        SELECT COUNT(*)
        FROM shipments s
        LEFT JOIN shipment_events se
            ON s.shipment_id = se.shipment_id
        WHERE se.event_id IS NULL
        """
    )
]


print("\nShipment Event Validation")
print("=" * 45)


for name, query in checks:

    result = connection.execute(query).fetchone()[0]

    print(f"{name}: {result}")


# --------------------------------------------------
# EVENT TYPE DISTRIBUTION
# --------------------------------------------------

print("\nEvent Type Distribution")
print("=" * 45)

query = """
SELECT
    event_type,
    COUNT(*) AS event_count
FROM shipment_events
GROUP BY event_type
ORDER BY event_count DESC
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['event_type']}: "
        f"{row['event_count']:,}"
    )


# --------------------------------------------------
# EVENTS PER SHIPMENT
# --------------------------------------------------

print("\nEvents Per Shipment")
print("=" * 45)

query = """
SELECT
    MIN(event_count),
    MAX(event_count),
    ROUND(AVG(event_count), 2)
FROM (
    SELECT
        shipment_id,
        COUNT(*) AS event_count
    FROM shipment_events
    GROUP BY shipment_id
)
"""

minimum, maximum, average = connection.execute(query).fetchone()

print(f"Minimum events: {minimum}")
print(f"Maximum events: {maximum}")
print(f"Average events: {average}")


connection.close()