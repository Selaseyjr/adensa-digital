from app.database import get_connection


ACTION_ID = "ACT-000004"


connection = get_connection()

row = connection.execute(
    """
    SELECT
        action_id,
        exception_id,
        option_id,
        status,
        approved_by,
        approved_at,
        executed_at
    FROM recovery_actions
    WHERE action_id = ?
    """,
    (ACTION_ID,),
).fetchone()


if row:
    print("Recovery Action")
    print("================")
    print(dict(row))
else:
    print(f"Action {ACTION_ID} was not found.")


connection.close()