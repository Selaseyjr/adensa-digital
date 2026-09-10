import sqlite3
from pathlib import Path


# --------------------------------------------------
# DATABASE CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "adensa.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------

def analyze_recovery_options(connection):

    cursor = connection.cursor()

    print("Recovery Options Analysis")
    print("=" * 45)

    # Total options
    total = cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM recovery_options
        """
    ).fetchone()["count"]

    print(f"Total recovery options: {total}")

    # Feasibility
    print("\nFeasibility")
    print("=" * 45)

    feasibility = cursor.execute(
        """
        SELECT
            CASE
                WHEN feasible = 1 THEN 'Feasible'
                ELSE 'Not Feasible'
            END AS status,
            COUNT(*) AS count
        FROM recovery_options
        GROUP BY feasible
        ORDER BY feasible DESC
        """
    ).fetchall()

    for row in feasibility:
        print(f"{row['status']}: {row['count']}")

    # Transport mode
    print("\nRecovery Options by Transport Mode")
    print("=" * 45)

    modes = cursor.execute(
        """
        SELECT
            transport_mode,
            COUNT(*) AS count
        FROM recovery_options
        GROUP BY transport_mode
        ORDER BY count DESC
        """
    ).fetchall()

    for row in modes:
        print(f"{row['transport_mode']}: {row['count']}")

    # Average cost
    print("\nAverage Recovery Cost")
    print("=" * 45)

    average_cost = cursor.execute(
        """
        SELECT
            ROUND(AVG(estimated_cost), 2) AS average_cost
        FROM recovery_options
        """
    ).fetchone()["average_cost"]

    print(f"€{average_cost:,.2f}")

    # Average transit
    average_transit = cursor.execute(
        """
        SELECT
            ROUND(AVG(estimated_transit_days), 2) AS average_days
        FROM recovery_options
        """
    ).fetchone()["average_days"]

    print(f"Average recovery transit: {average_transit} days")

    # Risk
    print("\nRisk Distribution")
    print("=" * 45)

    risk = cursor.execute(
        """
        SELECT
            CASE
                WHEN risk_score < 25 THEN 'Low'
                WHEN risk_score < 50 THEN 'Medium'
                WHEN risk_score < 75 THEN 'High'
                ELSE 'Very High'
            END AS risk_level,
            COUNT(*) AS count
        FROM recovery_options
        GROUP BY risk_level
        ORDER BY
            CASE risk_level
                WHEN 'Low' THEN 1
                WHEN 'Medium' THEN 2
                WHEN 'High' THEN 3
                WHEN 'Very High' THEN 4
            END
        """
    ).fetchall()

    for row in risk:
        print(f"{row['risk_level']}: {row['count']}")

    # Exceptions with no feasible options
    print("\nExceptions With No Feasible Recovery Option")
    print("=" * 45)

    no_feasible = cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM exceptions e
        WHERE e.resolution_status = 'Open'
        AND e.severity != 'Low'
        AND NOT EXISTS (
            SELECT 1
            FROM recovery_options r
            WHERE r.exception_id = e.exception_id
            AND r.feasible = 1
        )
        """
    ).fetchone()["count"]

    print(f"{no_feasible}")


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":

    connection = get_connection()

    try:
        analyze_recovery_options(connection)

    finally:
        connection.close()