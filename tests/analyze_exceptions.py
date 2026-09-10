import sqlite3


connection = sqlite3.connect("data/adensa.db")
connection.row_factory = sqlite3.Row


# --------------------------------------------------
# 1. EXCEPTION SEVERITY
# --------------------------------------------------

print("\nException Severity")
print("=" * 45)

query = """
SELECT
    severity,
    COUNT(*) AS exception_count
FROM exceptions
GROUP BY severity
ORDER BY exception_count DESC
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['severity']}: "
        f"{row['exception_count']:,}"
    )


# --------------------------------------------------
# 2. EXCEPTIONS BY TRANSPORT MODE
# --------------------------------------------------

print("\nExceptions by Transport Mode")
print("=" * 45)

query = """
SELECT
    s.transport_mode,
    COUNT(*) AS exception_count
FROM exceptions e
JOIN shipments s
    ON e.shipment_id = s.shipment_id
GROUP BY s.transport_mode
ORDER BY exception_count DESC
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['transport_mode']}: "
        f"{row['exception_count']:,}"
    )


# --------------------------------------------------
# 3. EXCEPTIONS BY PRIORITY
# --------------------------------------------------

print("\nExceptions by Shipment Priority")
print("=" * 45)

query = """
SELECT
    s.priority,
    COUNT(*) AS exception_count
FROM exceptions e
JOIN shipments s
    ON e.shipment_id = s.shipment_id
GROUP BY s.priority
ORDER BY exception_count DESC
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['priority']}: "
        f"{row['exception_count']:,}"
    )


# --------------------------------------------------
# 4. EXCEPTIONS BY ORIGIN
# --------------------------------------------------

print("\nExceptions by Origin")
print("=" * 45)

query = """
SELECT
    s.origin,
    COUNT(*) AS exception_count
FROM exceptions e
JOIN shipments s
    ON e.shipment_id = s.shipment_id
GROUP BY s.origin
ORDER BY exception_count DESC
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['origin']}: "
        f"{row['exception_count']:,}"
    )


# --------------------------------------------------
# 5. EXCEPTIONS BY CARRIER
# --------------------------------------------------

print("\nExceptions by Carrier")
print("=" * 45)

query = """
SELECT
    c.carrier_name,
    COUNT(*) AS exception_count
FROM exceptions e
JOIN shipments s
    ON e.shipment_id = s.shipment_id
JOIN carriers c
    ON s.carrier_id = c.carrier_id
GROUP BY c.carrier_name
ORDER BY exception_count DESC
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['carrier_name']}: "
        f"{row['exception_count']:,}"
    )


# --------------------------------------------------
# 6. AVERAGE DELAY
# --------------------------------------------------

print("\nAverage Delivery Delay")
print("=" * 45)

query = """
SELECT
    ROUND(
        AVG(
            julianday(s.estimated_arrival)
            - julianday(o.required_delivery_date)
        ),
        2
    ) AS average_delay_days
FROM exceptions e
JOIN shipments s
    ON e.shipment_id = s.shipment_id
JOIN orders o
    ON s.order_id = o.order_id
"""

average_delay = connection.execute(query).fetchone()[0]

print(
    f"Average delay: "
    f"{average_delay} days"
)


# --------------------------------------------------
# 7. TOP HIGH-RISK SHIPMENTS
# --------------------------------------------------

print("\nHigh-Risk Shipment Examples")
print("=" * 45)

query = """
SELECT
    e.exception_id,
    e.shipment_id,
    e.severity,
    s.priority,
    s.transport_mode,
    s.origin,
    s.destination,
    o.required_delivery_date,
    s.estimated_arrival
FROM exceptions e
JOIN shipments s
    ON e.shipment_id = s.shipment_id
JOIN orders o
    ON s.order_id = o.order_id
WHERE e.severity IN ('Critical', 'High')
ORDER BY
    CASE e.severity
        WHEN 'Critical' THEN 1
        WHEN 'High' THEN 2
        ELSE 3
    END,
    s.estimated_arrival DESC
LIMIT 10
"""

rows = connection.execute(query).fetchall()

for row in rows:
    print(
        f"{row['exception_id']} | "
        f"{row['shipment_id']} | "
        f"{row['severity']} | "
        f"Priority: {row['priority']} | "
        f"Mode: {row['transport_mode']} | "
        f"{row['origin']} → {row['destination']} | "
        f"Required: {row['required_delivery_date']} | "
        f"ETA: {row['estimated_arrival']}"
    )


connection.close()