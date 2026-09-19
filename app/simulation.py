"""
Controlled data-arrival simulation.

Represents a development/demo arrival scenario: one new
shipment with its shipment events, deliberately delayed
past the customer's required delivery date.

The simulation creates ARRIVAL DATA ONLY. It never creates
exceptions, recovery options, recommendations or recovery
actions: those are produced exclusively by the existing
operational pipeline (detect_exceptions →
generate_recovery_options → generate_workflow_actions)
when the user runs Refresh Operations Pipeline.

Determinism rules:

- No randomness and no wall-clock time: every value is
  derived from the baseline order's required delivery
  date and the simulation configuration.
- Shipment IDs follow SHP-SIM-%, event IDs EVT-SIM-%,
  sequenced from repository-backed lookups so repeated
  simulations continue safely without collisions with
  bootstrap data or each other.
- Existing operational records are never modified.

The arrival write is atomic: shipment and events are
committed together or not at all. The transaction ends
before the operational pipeline is triggered by the user.
"""

import logging
from datetime import datetime, timedelta

from app.config import SIMULATION_TIMESTAMP
from app.repositories import shipments_repo

logger = logging.getLogger(__name__)


# --------------------------------------------------
# ARRIVAL SCENARIO PARAMETERS
# --------------------------------------------------

# The simulated shipment is delayed by a fixed number of
# days past the order's required delivery date.

ARRIVAL_DELAY_DAYS = 6


def create_simulated_arrival(connection):
    """
    Create one deterministic simulated shipment arrival.

    The shipment reuses the first existing order/carrier
    combination by order_id, carries a Medium priority and
    an estimated arrival six days past the order's required
    delivery date, and is recorded with two credible events
    (creation and delay). The data satisfies the existing
    detection rules; the detector itself calculates the
    resulting exception.

    Returns the arrival summary dictionary, or None when
    the database contains no operational data to derive
    the scenario from.
    """

    baseline = shipments_repo.get_arrival_scenario_context(
        connection,
    )

    if baseline is None:
        logger.warning(
            "⚠ No operational data found. "
            "Generate the baseline dataset first."
        )
        return None

    shipment_number = (
        shipments_repo.get_next_simulation_shipment_number(
            connection,
        )
    )

    event_number = (
        shipments_repo.get_max_simulation_event_number(
            connection,
        )
        + 1
    )

    shipment_id = f"SHP-SIM-{shipment_number:04d}"

    required_delivery_date = datetime.strptime(
        baseline["required_delivery_date"],
        "%Y-%m-%d",
    ).date()

    # --------------------------------------------------
    # DETERMINISTIC SCENARIO DATES
    # --------------------------------------------------
    #
    # required delivery + 6 days  -> estimated arrival
    #   (the delay the detector will observe)
    #
    # required delivery - 4 days  -> planned departure
    # required delivery - 1 day   -> planned arrival
    #
    # The plan is placed so the workflow engine's later
    # execution timing resolves deterministically when a
    # recovery action for this shipment is executed.
    #

    estimated_arrival = required_delivery_date + timedelta(
        days=ARRIVAL_DELAY_DAYS,
    )

    planned_departure = required_delivery_date - timedelta(
        days=4,
    )

    planned_arrival = required_delivery_date - timedelta(
        days=1,
    )

    # --------------------------------------------------
    # SHIPMENT RECORD
    # --------------------------------------------------

    shipment_record = (
        shipment_id,
        baseline["order_id"],
        baseline["carrier_id"],
        baseline["origin"],
        baseline["destination"],
        "Sea",
        120,
        900.0,
        4.0,
        "Medium",
        planned_departure.strftime("%Y-%m-%d"),
        None,
        planned_arrival.strftime("%Y-%m-%d"),
        estimated_arrival.strftime("%Y-%m-%d"),
        None,
        "In Transit",
        600.0,
        1500.0,
        "At sea",
        SIMULATION_TIMESTAMP,
    )

    # --------------------------------------------------
    # SHIPMENT EVENTS
    # --------------------------------------------------

    event_records = [
        (
            f"EVT-SIM-{event_number:04d}",
            shipment_id,
            "Shipment Created",
            planned_departure.strftime("%Y-%m-%d %H:%M:%S"),
            baseline["origin"],
            (
                "Simulated shipment created and scheduled "
                "for transportation."
            ),
        ),
        (
            f"EVT-SIM-{event_number + 1:04d}",
            shipment_id,
            "Delay Detected",
            estimated_arrival.strftime("%Y-%m-%d %H:%M:%S"),
            "At sea",
            (
                f"Simulated shipment delayed. Estimated "
                f"arrival moved to "
                f"{estimated_arrival.strftime('%Y-%m-%d')} "
                f"({ARRIVAL_DELAY_DAYS} day(s) past the "
                f"required delivery date)."
            ),
        ),
    ]

    # --------------------------------------------------
    # ATOMIC ARRIVAL TRANSACTION
    # --------------------------------------------------
    #
    # Shipment and events commit together: a failed insert
    # must not leave a half-created arrival. The rollback
    # re-raises, so failures stay visible to the caller.
    #

    try:
        shipments_repo.insert_shipment(
            connection,
            shipment_record,
        )

        shipments_repo.insert_shipment_events(
            connection,
            event_records,
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    logger.info(
        f"✓ Simulated arrival {shipment_id} created "
        f"({len(event_records)} events)"
    )

    return {
        "shipment_id": shipment_id,
        "order_id": baseline["order_id"],
        "carrier_id": baseline["carrier_id"],
        "event_count": len(event_records),
        "required_delivery": baseline["required_delivery_date"],
        "estimated_arrival": estimated_arrival.strftime(
            "%Y-%m-%d"
        ),
        "delay_days": ARRIVAL_DELAY_DAYS,
    }
