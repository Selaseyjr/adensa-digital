import inspect

from app import cli
from app import execution_engine


print("=== EXECUTION ENGINE CONTRACT ===")

print(
    "execute_recovery_action:",
    inspect.signature(
        execution_engine.execute_recovery_action
    ),
)

print(
    "show_execution_result:",
    inspect.signature(
        cli.show_execution_result
    ),
)