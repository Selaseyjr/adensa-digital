import logging
from datetime import datetime

from app.config import SIMULATION_TIMESTAMP
from app.database import get_connection

logger = logging.getLogger(__name__)


# --------------------------------------------------
# EXCEPTION DETECTION
# --------------------------------------------------

def detect_exceptions(connection):

    cursor = connection.cursor()

    # --------------------------------------------------
    # CHECK EXISTING EXCEPTIONS
    # --------------------------------------------------

    cursor.execute("""
        SELECT COUNT(*)
        FROM exceptions
    """)

    existing_count = cursor.fetchone()[0]

    if existing_count > 0:
        logger.info(
            f"✓ Exceptions already contain "
            f"{existing_count:,} records"
        )
        return

    # --------------------------------------------------
    # LOAD SHIPMENT + ORDER INFORMATION
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            s.shipment_id,
            s.planned_arrival,
            s.estimated_arrival,
            s.status,
            s.priority,
            o.required_delivery_date
        FROM shipments s
        JOIN orders o
            ON s.order_id = o.order_id
        ORDER BY s.shipment_id
    """)

    shipments = cursor.fetchall()

    if not shipments:
        logger.warning("⚠ No shipments found.")
        return

    # --------------------------------------------------
    # DETECT EXCEPTIONS
    # --------------------------------------------------

    exception_records = []

    exception_number = 1

    for shipment in shipments:

        shipment_id = shipment["shipment_id"]

        estimated_arrival = datetime.strptime(
            shipment["estimated_arrival"],
            "%Y-%m-%d"
        )

        required_delivery_date = datetime.strptime(
            shipment["required_delivery_date"],
            "%Y-%m-%d"
        )

        priority = shipment["priority"]
        status = shipment["status"]

        # --------------------------------------------------
        # RULE 1 — DELIVERY DELAY
        # --------------------------------------------------

        if estimated_arrival > required_delivery_date:

            delay_days = (
                estimated_arrival
                - required_delivery_date
            ).days

            # --------------------------------------------------
            # SEVERITY
            # --------------------------------------------------

            if priority == "High" and delay_days >= 3:

                severity = "Critical"

            elif priority == "High" or delay_days >= 5:

                severity = "High"

            elif delay_days >= 3:

                severity = "Medium"

            else:

                severity = "Low"

            # --------------------------------------------------
            # IMPACT
            # --------------------------------------------------

            estimated_impact = (
                f"Estimated delivery delay of "
                f"{delay_days} day(s). "
                f"Customer delivery commitment at risk."
            )

            # --------------------------------------------------
            # EXCEPTION RECORD
            # --------------------------------------------------

            exception_records.append((
                f"EXC-{exception_number:06d}",
                shipment_id,
                "Delivery Delay",
                severity,
                SIMULATION_TIMESTAMP,
                (
                    f"Estimated arrival "
                    f"{estimated_arrival.strftime('%Y-%m-%d')} "
                    f"is later than required delivery date "
                    f"{required_delivery_date.strftime('%Y-%m-%d')}."
                ),
                estimated_impact,
                "Open",
                None
            ))

            exception_number += 1

    # --------------------------------------------------
    # INSERT EXCEPTIONS
    # --------------------------------------------------

    if exception_records:

        cursor.executemany("""
            INSERT INTO exceptions (
                exception_id,
                shipment_id,
                exception_type,
                severity,
                detected_at,
                description,
                estimated_impact,
                resolution_status,
                resolved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, exception_records)

        connection.commit()

        logger.info(
            f"✓ Detected and created "
            f"{len(exception_records):,} exceptions"
        )

    else:

        logger.info("✓ No exceptions detected.")


# --------------------------------------------------
# MAIN EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    connection = get_connection()

    try:

        detect_exceptions(connection)

    finally:

        connection.close()