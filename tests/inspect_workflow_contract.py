import inspect

from app import workflow_engine
from app.database import get_connection


print("=== WORKFLOW FUNCTION SIGNATURES ===")

print(
    "create_recovery_action:",
    inspect.signature(
        workflow_engine.create_recovery_action
    ),
)

print(
    "generate_workflow_actions:",
    inspect.signature(
        workflow_engine.generate_workflow_actions
    ),
)

print(
    "approve_action:",
    inspect.signature(
        workflow_engine.approve_action
    ),
)

print(
    "reject_action:",
    inspect.signature(
        workflow_engine.reject_action
    ),
)


print("\n=== SAMPLE RECOVERY ACTIONS ===")

connection = get_connection()

rows = connection.execute(
    """
    SELECT
        action_id,
        exception_id,
        option_id,
        action_type,
        status,
        approved_by,
        approved_at,
        executed_at
    FROM recovery_actions
    ORDER BY action_id
    LIMIT 5
    """
).fetchall()

for row in rows:
    print(dict(row))

connection.close()