"""
Test-only Streamlit entry point (Checkpoint K).

Runs the real application UI (app.main.main) against the
temporary database whose path is supplied through the
ADENSA_TEST_DB_PATH environment variable.

The production entry point (streamlit_app.py) is untouched:
this file exists so Streamlit AppTest can execute the real
UI against an isolated temporary database. It duplicates no
application initialization logic — it re-points the
database path and calls the existing production
initializer, exactly like the test fixtures do.
"""

import os
from pathlib import Path

import app.database as database

database.DATABASE_PATH = Path(
    os.environ["ADENSA_TEST_DB_PATH"]
)
database.initialize_database()

from app.main import main

main()
