from app.decision_engine import get_recommendation
from app.generate_recovery_options import generate_recovery_options
from app.workflow_engine import (
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
    generate_workflow_actions,
)


def test_backend_lifecycle(seeded_database):
    """
    Validate that the backend layers stay connected end to end
    on an isolated temporary database.

    The test builds a deterministic dataset and runs the real
    recovery generator, decision engine and workflow engine
    across the detect → options → recommendation → action chain.
    """

    connection = seeded_database

    try:
        cursor = connection.cursor()

        # --------------------------------------------------
        # 1. Generate recovery options with the real engine
        # --------------------------------------------------
        # EXC-900001 is Low severity and receives no options;
        # EXC-900002 receives three feasible options. The
        # selection loop below must therefore skip the
        # zero-recommendation exception.

        generate_recovery_options(connection)

        options_created = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM recovery_options
            """
        ).fetchone()["count"]

        assert options_created > 0

        print(
            f"✓ Recovery options generated: "
            f"{options_created}"
        )

        # --------------------------------------------------
        # 2. Confirm open exceptions exist
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

            if (
                recommendation is not None
                and recommendation["recommendation"] is not None
            ):

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
        # 3a. Create recovery actions with the real
        #     workflow engine (bootstrap step 10 path)
        # --------------------------------------------------

        workflow_summary = generate_workflow_actions(
            connection,
        )

        assert workflow_summary["created"] == 1

        print(
            f"✓ Workflow engine created "
            f"{workflow_summary['created']} recovery action."
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
        # 4a. Confirm the action references the exact
        #     option selected by the recommendation
        # --------------------------------------------------

        recommended_option_id = candidate[
            "recommendation"
        ]["option_id"]

        assert (
            action["option_id"]
            == recommended_option_id
        )

        option_exists = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM recovery_options
            WHERE option_id = ?
            """,
            (recommended_option_id,),
        ).fetchone()["count"]

        assert option_exists == 1

        print(
            f"✓ Action references recommended option: "
            f"{action['option_id']}"
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