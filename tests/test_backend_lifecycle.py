from app.database import get_connection
from app.decision_engine import get_recommendation
from app.workflow_engine import (
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
)


def test_backend_lifecycle():
    """
    Validate that the major Adensa Digital backend layers
    are connected correctly.

    This test is read-only.
    It does not approve, execute, or modify any records.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # --------------------------------------------------
        # 1. Confirm open exceptions exist
        # --------------------------------------------------

        open_exceptions = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM exceptions
            WHERE resolution_status = 'Open'
            """
        ).fetchone()["count"]

        assert open_exceptions > 0

        print(
            f"✓ Open exceptions available: "
            f"{open_exceptions}"
        )

        # --------------------------------------------------
        # 2. Find an open exception with a recommendation
        # --------------------------------------------------

        candidate = None
        selected_exception_id = None

        exception_rows = cursor.execute(
            """
            SELECT exception_id
            FROM exceptions
            WHERE resolution_status = 'Open'
            ORDER BY exception_id
            """
        ).fetchall()

        for row in exception_rows:

            recommendation = get_recommendation(
                connection,
                row["exception_id"],
            )

            if recommendation is not None:

                candidate = recommendation
                selected_exception_id = row[
                    "exception_id"
                ]

                break

        assert candidate is not None

        print(
            f"✓ Decision engine recommendation available: "
            f"{selected_exception_id}"
        )

        # --------------------------------------------------
        # 3. Inspect the recommendation structure
        # --------------------------------------------------

        assert isinstance(candidate, dict)

        print(
            "✓ Decision engine returned a valid "
            "recommendation object."
        )

        # --------------------------------------------------
        # 4. Confirm a recovery action exists
        # --------------------------------------------------

        action = cursor.execute(
            """
            SELECT
                action_id,
                exception_id,
                option_id,
                status
            FROM recovery_actions
            WHERE exception_id = ?
            ORDER BY action_id
            LIMIT 1
            """,
            (selected_exception_id,),
        ).fetchone()

        assert action is not None

        print(
            f"✓ Recovery action connected: "
            f"{action['action_id']}"
        )

        # --------------------------------------------------
        # 5. Validate workflow state
        # --------------------------------------------------

        assert action["status"] in {
            PENDING_APPROVAL,
            APPROVED,
            EXECUTED,
        }

        print(
            f"✓ Valid workflow state: "
            f"{action['status']}"
        )

        # --------------------------------------------------
        # 6. Confirm recovery option exists
        # --------------------------------------------------

        option = cursor.execute(
            """
            SELECT
                option_id,
                exception_id,
                transport_mode,
                estimated_cost,
                estimated_transit_days,
                risk_score,
                feasible
            FROM recovery_options
            WHERE option_id = ?
            """,
            (action["option_id"],),
        ).fetchone()

        assert option is not None

        print(
            f"✓ Recovery option connected: "
            f"{option['option_id']}"
        )

        # --------------------------------------------------
        # 7. Confirm option belongs to exception
        # --------------------------------------------------

        assert (
            option["exception_id"]
            == action["exception_id"]
        )

        print(
            "✓ Exception → Recovery Option "
            "relationship valid."
        )

        # --------------------------------------------------
        # 8. Confirm shipment relationship
        # --------------------------------------------------

        shipment = cursor.execute(
            """
            SELECT
                s.shipment_id,
                s.order_id,
                e.exception_id
            FROM shipments s

            JOIN exceptions e
                ON s.shipment_id = e.shipment_id

            WHERE e.exception_id = ?
            """,
            (selected_exception_id,),
        ).fetchone()

        assert shipment is not None

        print(
            f"✓ Exception → Shipment relationship valid: "
            f"{shipment['shipment_id']}"
        )

        # --------------------------------------------------
        # 9. Confirm order relationship
        # --------------------------------------------------

        order = cursor.execute(
            """
            SELECT
                o.order_id,
                o.required_delivery_date,
                s.shipment_id
            FROM orders o

            JOIN shipments s
                ON o.order_id = s.order_id

            JOIN exceptions e
                ON s.shipment_id = e.shipment_id

            WHERE e.exception_id = ?
            """,
            (selected_exception_id,),
        ).fetchone()

        assert order is not None

        print(
            f"✓ Shipment → Order relationship valid: "
            f"{order['order_id']}"
        )

        # --------------------------------------------------
        # Final result
        # --------------------------------------------------

        print(
            "\nBackend lifecycle validation complete."
        )

        print(
            "✓ Database → Exception → Decision → "
            "Recovery → Workflow chain is connected."
        )

        print(
            "✓ No database records were modified."
        )

    finally:
        connection.close()


if __name__ == "__main__":
    test_backend_lifecycle()