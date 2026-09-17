import logging
from datetime import datetime

from app.config import SIMULATION_DATE
from app.database import get_connection

logger = logging.getLogger(__name__)


# --------------------------------------------------
# RECOVERY TRANSPORT PROFILES
# --------------------------------------------------

TRANSPORT_PROFILES = {
    "Air": {
        "normal_transit_days": 6,
        "recovery_transit_days": 2,
        "base_rate": 0.22,
        "risk_score": 15,
        "mode_premium": 750,
    },
    "Road": {
        "normal_transit_days": 5,
        "recovery_transit_days": 4,
        "base_rate": 0.10,
        "risk_score": 25,
        "mode_premium": 300,
    },
    "Rail": {
        "normal_transit_days": 14,
        "recovery_transit_days": 10,
        "base_rate": 0.07,
        "risk_score": 30,
        "mode_premium": 200,
    },
    "Sea": {
        "normal_transit_days": 30,
        "recovery_transit_days": 25,
        "base_rate": 0.03,
        "risk_score": 45,
        "mode_premium": 100,
    },
}


# --------------------------------------------------
# OPTION ID GENERATION
# --------------------------------------------------

def get_next_option_number(connection):
    """
    Determine the next recovery-option number from the
    existing database records.

    This keeps option IDs deterministic and unique,
    mirroring the action-ID approach in the workflow
    engine, so every recovery option carries a stable
    identity that decisions, actions and execution can
    reference.
    """

    cursor = connection.cursor()

    options = cursor.execute(
        """
        SELECT option_id
        FROM recovery_options
        WHERE option_id LIKE 'OPT-%'
        """
    ).fetchall()

    numbers = []

    for option in options:

        option_id = option["option_id"]

        try:
            number = int(
                option_id.replace("OPT-", "")
            )

            numbers.append(number)

        except ValueError:
            continue

    if not numbers:
        return 1

    return max(numbers) + 1


# --------------------------------------------------
# RECOVERY ENGINE
# --------------------------------------------------

def generate_recovery_options(connection):
    """
    Generate recovery alternatives for open shipment exceptions.

    V1 focuses on:
    - current shipment delay
    - time that can potentially be recovered
    - alternative transport modes
    - shipment weight
    - shipment priority
    - carrier reliability
    - incremental recovery cost
    - operational risk
    - feasibility
    """

    cursor = connection.cursor()

    # --------------------------------------------------
    # DUPLICATE PROTECTION
    # --------------------------------------------------

    existing_options = cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM recovery_options
        """
    ).fetchone()["count"]

    if existing_options > 0:
        logger.info(
            f"Recovery options already exist "
            f"({existing_options} records)."
        )
        logger.info(
            "Clear the recovery_options table "
            "before regenerating."
        )
        return

    # --------------------------------------------------
    # LOAD OPEN EXCEPTIONS
    # --------------------------------------------------

    exceptions = cursor.execute(
        """
        SELECT
            e.exception_id,
            e.shipment_id,
            e.exception_type,
            e.severity,
            e.description,

            s.origin,
            s.destination,
            s.transport_mode,
            s.quantity,
            s.weight_kg,
            s.distance_km,
            s.priority,
            s.estimated_arrival,

            o.required_delivery_date

        FROM exceptions e

        JOIN shipments s
            ON e.shipment_id = s.shipment_id

        JOIN orders o
            ON s.order_id = o.order_id

        WHERE e.resolution_status = 'Open'

        ORDER BY e.exception_id
        """
    ).fetchall()

    # --------------------------------------------------
    # LOAD CARRIERS
    # --------------------------------------------------

    carriers = cursor.execute(
        """
        SELECT
            carrier_id,
            carrier_name,
            reliability_score,
            transport_modes

        FROM carriers
        """
    ).fetchall()

    if not exceptions:
        logger.info("No open exceptions found.")
        return

    if not carriers:
        logger.info("No carriers found.")
        return

    # --------------------------------------------------
    # RECOVERY PLANNING DATE
    # --------------------------------------------------
    #
    # Our synthetic dataset is currently aligned to
    # September 10, 2026.
    #
    # Later this can become:
    # datetime.now().date()
    #
    # or, preferably, a real event timestamp from the
    # operational system.
    #

    recovery_start_date = datetime.strptime(
        SIMULATION_DATE,
        "%Y-%m-%d"
    ).date()

    options_created = 0

    # --------------------------------------------------
    # DETERMINISTIC OPTION IDS
    # --------------------------------------------------

    next_option_number = get_next_option_number(
        connection
    )

    # --------------------------------------------------
    # PROCESS EACH EXCEPTION
    # --------------------------------------------------

    for exception in exceptions:

        severity = exception["severity"]
        current_mode = exception["transport_mode"]

        # Low-severity exceptions are monitored rather
        # than immediately generating recovery actions.
        if severity == "Low":
            continue

        weight = float(exception["weight_kg"])
        distance = float(exception["distance_km"])

        required_date = datetime.strptime(
            exception["required_delivery_date"],
            "%Y-%m-%d"
        ).date()

        estimated_arrival = datetime.strptime(
            exception["estimated_arrival"],
            "%Y-%m-%d"
        ).date()

        # --------------------------------------------------
        # CURRENT DELAY
        # --------------------------------------------------

        days_late = max(
            0,
            (estimated_arrival - required_date).days
        )

        # --------------------------------------------------
        # REMAINING DELIVERY WINDOW
        # --------------------------------------------------
        #
        # How many calendar days remain before the
        # customer's required delivery date?
        #

        remaining_delivery_days = max(
            0,
            (required_date - recovery_start_date).days
        )

        # --------------------------------------------------
        # CURRENT MODE TRANSIT
        # --------------------------------------------------

        current_profile = TRANSPORT_PROFILES.get(
            current_mode
        )

        if current_profile:
            current_transit_days = (
                current_profile["normal_transit_days"]
            )
        else:
            current_transit_days = 10

        # --------------------------------------------------
        # EVALUATE ALTERNATIVE MODES
        # --------------------------------------------------

        for mode, profile in TRANSPORT_PROFILES.items():

            # Do not recommend the current transport mode
            # as a recovery alternative.
            if mode == current_mode:
                continue

            recovery_transit_days = (
                profile["recovery_transit_days"]
            )

            # --------------------------------------------------
            # TIME SAVED
            # --------------------------------------------------
            #
            # Example:
            #
            # Current mode = Sea
            # Normal transit = 30 days
            #
            # Recovery mode = Air
            # Recovery transit = 3 days
            #
            # Potential time saving = 27 days
            #
            # We cap the useful saving at the current delay.
            #

            potential_time_saved = max(
                0,
                current_transit_days
                - recovery_transit_days
            )

            recoverable_delay = min(
                days_late,
                potential_time_saved
            )

            remaining_delay = max(
                0,
                days_late - potential_time_saved
            )

            # --------------------------------------------------
            # FEASIBILITY
            # --------------------------------------------------
            #
            # A recovery option is feasible when it can
            # eliminate the shipment's current delay.
            #
            # OR, when there is still delivery time available,
            # the recovery movement can complete inside that
            # remaining window.
            #

            delay_recovered = (
                potential_time_saved >= days_late
            )

            delivery_window_available = (
                recovery_transit_days
                <= remaining_delivery_days
            )

            feasible = (
                delay_recovered
                or delivery_window_available
            )

            # --------------------------------------------------
            # PRIORITY CONSTRAINTS
            # --------------------------------------------------

            if exception["priority"] == "High":
                feasible = (
                    feasible
                    and mode in ["Air", "Road", "Rail"]
                )

            if severity == "Critical":
                feasible = (
                    feasible
                    and mode in ["Air", "Road"]
                )

            # --------------------------------------------------
            # RECOVERY COST
            # --------------------------------------------------
            #
            # We are estimating the incremental intervention,
            # not the entire original freight journey.
            #
            # Cost =
            # handling
            # + mode-switch premium
            # + weight component
            # + urgency
            # + delay pressure
            #

            base_handling = 250

            weight_component = weight * 2.50

            mode_premium = profile["mode_premium"]

            if severity == "Critical":
                urgency_component = 1500
            elif severity == "High":
                urgency_component = 900
            else:
                urgency_component = 400

            delay_component = min(
                days_late * 100,
                1500
            )

            estimated_cost = (
                base_handling
                + weight_component
                + mode_premium
                + urgency_component
                + delay_component
            )

            # Emergency air recovery generally involves
            # additional booking/handling cost.
            if mode == "Air":
                estimated_cost += 750

            estimated_cost = round(
                estimated_cost,
                2
            )

            # --------------------------------------------------
            # CARRIER SELECTION
            # --------------------------------------------------

            compatible_carriers = []

            for carrier in carriers:

                carrier_modes = (
                    carrier["transport_modes"] or ""
                ).lower()

                if mode.lower() in carrier_modes:
                    compatible_carriers.append(carrier)

            # Higher reliability_score means better reliability.
            if compatible_carriers:

                selected_carrier = max(
                    compatible_carriers,
                    key=lambda carrier:
                    carrier["reliability_score"]
                )

            else:

                selected_carrier = max(
                    carriers,
                    key=lambda carrier:
                    carrier["reliability_score"]
                )

            # --------------------------------------------------
            # RISK SCORE
            # --------------------------------------------------

            risk_score = profile["risk_score"]

            reliability_penalty = max(
                0,
                100 - selected_carrier["reliability_score"]
            )

            risk_score += int(
                reliability_penalty * 0.20
            )

            # Tight delivery windows increase operational risk.
            if remaining_delivery_days <= 2:
                risk_score += 10

            elif remaining_delivery_days <= 5:
                risk_score += 5

            # If some delay remains even after recovery,
            # risk increases.
            if remaining_delay > 0:
                risk_score += min(
                    remaining_delay * 3,
                    15
                )

            if severity == "Critical":
                risk_score += 10

            risk_score = max(
                0,
                min(100, risk_score)
            )

            # --------------------------------------------------
            # CAPACITY
            # --------------------------------------------------
            #
            # V1 assumption:
            # recovery capacity exists.
            #
            # Later:
            # carrier capacity + lane capacity + warehouse
            # capacity can be integrated here.
            #

            capacity_available = 1

            # --------------------------------------------------
            # INSERT RECOVERY OPTION
            # --------------------------------------------------

            option_id = f"OPT-{next_option_number:06d}"

            next_option_number += 1

            cursor.execute(
                """
                INSERT INTO recovery_options (
                    option_id,
                    exception_id,
                    transport_mode,
                    carrier_id,
                    estimated_cost,
                    estimated_transit_days,
                    capacity_available,
                    risk_score,
                    feasible
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    option_id,
                    exception["exception_id"],
                    mode,
                    selected_carrier["carrier_id"],
                    estimated_cost,
                    recovery_transit_days,
                    capacity_available,
                    risk_score,
                    1 if feasible else 0,
                )
            )

            options_created += 1

    connection.commit()

    logger.info(
        f"✓ Created {options_created} recovery options"
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    connection = get_connection()

    try:
        generate_recovery_options(connection)

    finally:
        connection.close()