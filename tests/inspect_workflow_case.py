import sqlite3

connection = sqlite3.connect("data/adensa.db")
connection.row_factory = sqlite3.Row

row = connection.execute(
    """
    SELECT
        s.shipment_id,
        s.order_id,
        s.planned_departure,
        s.planned_arrival,
        s.estimated_arrival,
        s.actual_arrival,
        o.order_date,
        o.required_delivery_date
    FROM shipments s
    JOIN orders o
        ON s.order_id = o.order_id
    WHERE s.shipment_id = (
        SELECT shipment_id
        FROM exceptions
        WHERE exception_id = 'EXC-000001'
    )
    """
).fetchone()

print("Workflow Test Case")
print("=" * 50)

for key in row.keys():
    print(f"{key}: {row[key]}")

connection.close()