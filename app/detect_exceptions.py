import logging
from datetime import datetime

from app.config import SIMULATION_TIMESTAMP
from app.database import get_connection
from app.repositories import exceptions_repo
from app.repositories import shipments_repo

logger = logging.getLogger(__name__)


# --------------------------------------------------
# EXCEPTION DETECTION
# --------------------------------------------------

def detect_exceptions(connection):

    # --------------------------------------------------
    # ENTITY-LEVEL IDEMPOTENCY
    # --------------------------------------------------

    # Shipments that are already represented by an
    # exception are skipped, so repeated detection runs
    # (and newly arrived shipments) can be processed on
    # a populated database without duplicating
    # exceptions.

    existing_shipment_ids = (
        exceptions_repo.get_shipment_ids_with_exceptions(
            connection
        )
    )

    # --------------------------------------------------
    # LOAD SHIPMENT + ORDER INFORMATION
    # --------------------------------------------------

    shipments = shipments_repo.get_shipments_with_required_delivery(
        connection
    )

    if not shipments:
        logger.warning("⚠ No shipments found.")
        return

    # --------------------------------------------------
    # DETECT EXCEPTIONS
    # --------------------------------------------------

    exception_records = []

    exception_number = exceptions_repo.get_next_exception_number(
        connection
    )

    for shipment in shipments:

        shipment_id = shipment["shipment_id"]

        if shipment_id in existing_shipment_ids:
            continue

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

        exceptions_repo.insert_exceptions(
            connection,
            exception_records,
        )

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