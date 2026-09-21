"""
Streamlit AppTest coverage for the Adensa operational UI
(Checkpoint K).

These tests execute the REAL user interface — the same
app.main.main() the production entry point runs — through
Streamlit's AppTest harness, against isolated temporary
databases built with the production initializer and the
existing deterministic fixtures.

What is asserted is user-visible behavior only: rendered
text, widget labels/keys and metric values. No element
indexes, no styling, no implementation details. The real
service layer, engines and repositories run underneath;
business logic is never mocked.

Each lifecycle scenario uses a fresh AppTest instance (and
a fresh temporary database), because AppTest instances must
not be reused across transitions that destroy widgets.

The development database is never opened: every scenario
activates its own temporary database through
tests/ui_entry.py before the UI runs.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

UI_ENTRY = REPO_ROOT / "tests" / "ui_entry.py"


# ==================================================
# HELPERS
# ==================================================

def _build_database(with_pipeline=False):
    """
    Create and seed an isolated temporary database with the
    production initializer and the shared deterministic
    fixture dataset; optionally run the real operational
    pipeline (options -> workflow actions).

    Returns (TemporaryDirectory, db_path).
    """

    import app.database as database
    from tests.conftest import seed_minimal_supply_chain

    tmp = tempfile.TemporaryDirectory(
        prefix="adensa_ui_test_"
    )
    db_path = Path(tmp.name) / "ui_test.db"

    database.DATABASE_PATH = db_path
    database.initialize_database()

    connection = database.get_connection()

    seed_minimal_supply_chain(connection)

    if with_pipeline:

        from app.generate_recovery_options import (
            generate_recovery_options,
        )
        from app.workflow_engine import (
            generate_workflow_actions,
        )

        generate_recovery_options(connection)
        generate_workflow_actions(connection)

    connection.close()

    return tmp, db_path


def _open_ui(db_path):
    """Open the real UI against the temporary database."""

    os.environ["ADENSA_TEST_DB_PATH"] = str(db_path)

    app_test = AppTest.from_file(str(UI_ENTRY))
    app_test.run(timeout=120)

    assert not app_test.exception, (
        app_test.exception[0].value
        if len(app_test.exception)
        else "unknown UI exception"
    )

    return app_test


def _inbox_selectbox(app_test):
    """The exception-inbox selection widget."""

    return [
        selectbox
        for selectbox in app_test.selectbox
        if "investigate" in selectbox.label.lower()
    ][0]


def _select_exception(app_test, exception_id):
    """Select an exception in the inbox by its label."""

    inbox = _inbox_selectbox(app_test)

    label = [
        option
        for option in inbox.options
        if exception_id in option
    ][0]

    inbox.set_value(label).run()

    assert not app_test.exception

    return inbox


def _metric(app_test, label):
    """The rendered value of a dashboard metric."""

    return [
        metric.value
        for metric in app_test.metric
        if metric.label == label
    ][0]


def _widget(app_test, kind, key_prefix):
    """First widget of a kind whose key starts with a prefix."""

    return [
        widget
        for widget in getattr(app_test, kind)
        if widget.key is not None
        and widget.key.startswith(key_prefix)
    ][0]


def _text_values(elements):
    """Rendered text values of a Streamlit element list."""

    return [element.value for element in elements]


# ==================================================
# SCENARIO 1 — INITIAL CONTROL-TOWER RENDER
# ==================================================

def test_initial_control_tower_render():
    """
    The application loads the real UI over a populated
    database: the control-tower metrics, the operational
    sections and the inbox triage labels render without a
    script exception.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        assert app_test.title[0].value == "🌍 Adensa Digital"

        header_values = _text_values(app_test.header)

        for section in (
            "Exception Inbox",
            "Decision Engine",
            "Workflow Action",
            "Operational History",
        ):
            assert section in header_values

        # The control-tower KPI row (Checkpoint J).
        assert _metric(app_test, "Open Exceptions") == "2"
        assert _metric(app_test, "Actionable") == "1"
        assert _metric(app_test, "Monitoring") == "1"
        assert _metric(app_test, "Pending Decisions") == "1"
        assert _metric(app_test, "Awaiting Execution") == "0"
        assert _metric(app_test, "Critical Open") == "0"
        assert _metric(app_test, "Recently Resolved") == "0"

        # Inbox triage labels (Checkpoint E).
        options = list(_inbox_selectbox(app_test).options)

        assert any(
            "EXC-900002" in option and "Actionable" in option
            for option in options
        )
        assert any(
            "EXC-900001" in option
            and "No feasible recovery" in option
            for option in options
        )

    finally:
        tmp.cleanup()


def test_quiet_database_renders_safely():
    """
    Scenario 9: with no pipeline activity the UI still
    renders safely — the master-data-only fixture produces
    no exceptions, so the app reaches its calm
    nothing-requires-attention state without raising.
    """

    tmp, db_path = _build_database(with_pipeline=False)

    try:
        connection_path = db_path

        # Seed ONLY master data (no operational rows): the
        # smallest deterministic quiet state.
        import sqlite3

        connection = sqlite3.connect(connection_path)

        connection.execute(
            "DELETE FROM exceptions"
        )
        connection.execute(
            "DELETE FROM shipment_events"
        )
        connection.execute(
            "DELETE FROM shipments"
        )
        connection.commit()
        connection.close()

        app_test = _open_ui(connection_path)

        assert _metric(app_test, "Open Exceptions") == "0"
        assert _metric(app_test, "Actionable") == "0"

        assert any(
            "No open shipment exceptions" in value
            for value in _text_values(app_test.success)
        )

    finally:
        tmp.cleanup()


# ==================================================
# SCENARIO 2 — ACTIONABLE EXCEPTION
# ==================================================

def test_actionable_exception_renders_recommendation():
    """
    Selecting the actionable exception renders the recovery
    assessment, the recommendation and its comparison table,
    with the pending-decision workflow controls available.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        subheaders = _text_values(app_test.subheader)

        assert "Recommended Recovery" in subheaders
        assert "Recovery Options Comparison" in subheaders

        # The recommendation comparison table, the
        # Checkpoint T rationale factor-breakdown table, the
        # Checkpoint V sustainability table and the Checkpoint
        # R operational-history table.
        assert len(app_test.dataframe) == 4

        # Checkpoint Q: the investigation view opens with the
        # recorded issue and shows the decision factors.
        issue_notes = [
            note.value
            for note in app_test.info
            if "five days late" in (note.value or "")
        ]
        assert issue_notes, (
            "the recorded exception issue must be surfaced"
        )

        assert any(
            "Decision required" in (info.value or "")
            for info in app_test.info
        ), "the pending state must state the next action"

        comparison_table = [
            frame.value
            for frame in app_test.dataframe
            if "Option" in frame.value.columns
        ][0]

        # The engine's per-option factor scores are shown
        # alongside the raw option data, so the planner can
        # see WHY the recommendation wins — without the UI
        # recomputing anything.
        for factor_column in (
            "Cost fit",
            "Transit fit",
            "Risk fit",
            "Priority fit",
            "Score",
        ):
            assert factor_column in comparison_table.columns

        verdicts = comparison_table["Option"].tolist()
        assert verdicts[0] == "Recommended"
        assert "Alternative" in verdicts

        # Checkpoint T: the rationale section exposes the
        # policy weights, the per-factor breakdown and the
        # confidence basis - all from the service projection.
        assert "Recommendation Rationale" in subheaders

        factor_table = [
            frame.value
            for frame in app_test.dataframe
            if "Factor" in frame.value.columns
        ][0]

        assert (
            factor_table["Factor"].tolist()
            == [
                "Cost fit",
                "Transit fit",
                "Risk fit",
                "Priority fit",
            ]
        )

        for column in (
            "Recommended score",
            "Recommended weighted",
            "Alternative 1 score",
            "Alternative 1 weighted",
            "Weight",
        ):
            assert column in factor_table.columns

        weight_texts = _text_values(app_test.caption)

        assert any(
            "Decision policy" in (text or "")
            and "Cost 25%" in (text or "")
            and "Transit 30%" in (text or "")
            for text in weight_texts
        ), "policy weights must be shown from configuration"

        assert any(
            "Recommendation confidence" in (text or "")
            and "not a probability of success" in (text or "")
            for text in weight_texts
        ), "confidence basis must accompany the label"

        # Checkpoint V: the sustainability section estimates
        # emissions for every feasible option and states the
        # prototype methodology, without touching the decision.
        assert "Sustainability Impact" in subheaders

        sustainability_table = [
            frame.value
            for frame in app_test.dataframe
            if "Estimated CO₂e (kg)" in frame.value.columns
        ][0]

        assert (
            sustainability_table["Option"].tolist()
            == ["Recommended", "Alternative", "Alternative"]
        )

        co2_values = sustainability_table[
            "Estimated CO₂e (kg)"
        ].tolist()

        assert all(
            value != "Not available" for value in co2_values
        ), "fixture data supports estimates for all three modes"

        assert any(
            "Prototype sustainability estimate" in (c or "")
            for c in _text_values(app_test.caption)
        ), "methodology/assumption note must be visible"

        assert _widget(
            app_test, "text_input", "approver_"
        ) is not None
        assert _widget(
            app_test, "button", "approve_"
        ) is not None
        assert _widget(
            app_test, "button", "reject_"
        ) is not None

    finally:
        tmp.cleanup()


# ==================================================
# SCENARIO 3 — APPROVAL -> EXECUTION
# ==================================================

def test_approval_then_execution_reaches_outcome():
    """
    Approving through the UI reruns the app into the
    approved state; executing then renders the operational
    outcome from Adensa's own state.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        _widget(app_test, "text_input", "approver_").set_value(
            "UI Planner"
        )

        _widget(app_test, "button", "approve_").click().run()

        assert not app_test.exception

        # The decision is recorded: the pending count drops,
        # the execution offer appears.
        assert _metric(
            app_test, "Pending Decisions"
        ) == "0"
        assert _metric(
            app_test, "Awaiting Execution"
        ) == "1"
        assert _widget(
            app_test, "button", "execute_"
        ) is not None

        _widget(app_test, "button", "execute_").click().run()

        assert not app_test.exception

        # The outcome section renders Adensa's execution
        # result (the fixture scenario stays open).
        assert any(
            "Latest Workflow Outcome" in value
            for value in _text_values(app_test.header)
        )
        assert any(
            "Recovery executed successfully" in value
            for value in _text_values(app_test.success)
        )

    finally:
        tmp.cleanup()


# ==================================================
# SCENARIO 4 — EXECUTED BUT STILL OPEN
# ==================================================

def test_executed_but_still_open_is_not_reported_resolved():
    """
    The fixture's timing leaves the shipment past its
    required delivery after execution: the UI must present
    the still-open reality, never a false resolution.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        _widget(app_test, "text_input", "approver_").set_value(
            "UI Planner"
        )
        _widget(app_test, "button", "approve_").click().run()
        _widget(app_test, "button", "execute_").click().run()

        assert not app_test.exception

        # The execution outcome banner states the shipment
        # still requires recovery.
        assert any(
            "still requires further recovery" in value
            for value in _text_values(app_test.warning)
        )

        # The exception remains in the open inbox: it was
        # not resolved by this execution.
        options = list(_inbox_selectbox(app_test).options)

        assert any(
            "EXC-900002" in option for option in options
        )

        # The Recently Resolved surface stays empty.
        assert _metric(
            app_test, "Recently Resolved"
        ) == "0"

    finally:
        tmp.cleanup()


# ==================================================
# SCENARIO 5 — REJECTION
# ==================================================

def test_rejection_records_terminal_state():
    """
    Rejecting a pending action records the terminal
    rejected state; execution is no longer offered.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        _widget(app_test, "text_input", "approver_").set_value(
            "UI Rejecter"
        )

        _widget(app_test, "button", "reject_").click().run()

        assert not app_test.exception

        # Terminal rejected state with the recorded actor.
        assert any(
            "This recovery action was rejected" in value
            for value in _text_values(app_test.warning)
        )

        # The execution control is gone for a rejected
        # action. (Fresh app instance — this transition
        # destroyed the approval widgets.)
        fresh = _open_ui(db_path)
        _select_exception(fresh, "EXC-900002")

        assert not [
            button
            for button in fresh.button
            if button.key.startswith("execute_")
        ]

    finally:
        tmp.cleanup()


# ==================================================
# SCENARIOS 6-7 — MANUAL RESOLUTION
# ==================================================

def _record_manual_intervention(
    app_test,
    exception_id,
    outcome,
):
    """Fill and save the manual-resolution form."""

    _select_exception(app_test, exception_id)

    _widget(
        app_test, "selectbox", "intervention_type_"
    ).set_value("Carrier call")

    _widget(
        app_test, "text_input", "intervention_party_"
    ).set_value("External Carrier Desk")

    _widget(
        app_test, "text_area", "intervention_resolution_"
    ).set_value("Carrier agreed to expedite the delivery.")

    _widget(
        app_test, "selectbox", "intervention_outcome_"
    ).set_value(outcome)

    _widget(
        app_test, "text_input", "intervention_recorder_"
    ).set_value("UI Planner")

    _widget(
        app_test, "button", "intervention_save_"
    ).click().run()

    assert not app_test.exception


def test_manual_resolution_makes_exception_resolved():
    """
    Scenario 6: a manually resolved intervention resolves
    the exception, and the UI reflects the manual
    resolution path in the Recently Resolved surface.
    """

    tmp, db_path = _build_database(with_pipeline=False)

    try:
        app_test = _open_ui(db_path)

        _record_manual_intervention(
            app_test,
            "EXC-900001",
            "Resolved",
        )

        # The exception left the open population.
        assert _metric(app_test, "Open Exceptions") == "1"

        # The confirmation and the resolved-exception
        # context are rendered.
        assert any(
            "Manual resolution recorded" in value
            for value in _text_values(app_test.success)
        )
        assert any(
            "Resolved through manual intervention" in value
            for value in _text_values(app_test.info)
        )

        # The Recently Resolved surface now carries the
        # manually resolved exception (fresh read).
        fresh = _open_ui(db_path)

        assert _metric(
            fresh, "Recently Resolved"
        ) == "1"

        resolved_rows = fresh.dataframe[0].value

        row = resolved_rows.iloc[0]

        assert row["Exception"] == "EXC-900001"
        assert row["Resolution Path"] == "Manually resolved"

    finally:
        tmp.cleanup()


def test_manual_still_open_keeps_exception_open():
    """
    Scenario 7: a Still-Open intervention records the
    external activity without resolving the exception —
    and never displays a false resolution.
    """

    tmp, db_path = _build_database(with_pipeline=False)

    try:
        app_test = _open_ui(db_path)

        _record_manual_intervention(
            app_test,
            "EXC-900001",
            "Still Open",
        )

        # The exception stays in the open population.
        assert _metric(app_test, "Open Exceptions") == "2"

        # The intervention is recorded but the exception
        # remains monitored: no resolution is displayed.
        assert any(
            "remains open and monitored" in value
            for value in _text_values(app_test.warning)
        )

        fresh = _open_ui(db_path)

        assert _metric(
            fresh, "Recently Resolved"
        ) == "0"

    finally:
        tmp.cleanup()


# ==================================================
# SCENARIO 8 — RECENTLY RESOLVED / HISTORY
# ==================================================

def test_history_renders_factual_lifecycle_events():
    """
    The Operational History section renders the exception's
    chronological lifecycle: detection and, after the real
    workflow, the human decision and execution.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        # Detection is history before any human acts.
        history_caption = _text_values(app_test.caption)

        assert any(
            "Chronological record built from real persisted"
            in value
            for value in history_caption
        )

        # Drive the real workflow to enrich the history.
        _widget(app_test, "text_input", "approver_").set_value(
            "History Planner"
        )
        _widget(app_test, "button", "approve_").click().run()

        assert _metric(app_test, "Awaiting Execution") == "1"

        _widget(app_test, "button", "execute_").click().run()

        assert not app_test.exception

        # The executed action's history carries the decision
        # and the execution with the recorded actor: read the
        # rendered history table fresh after the transitions
        # (a same-run st.rerun() short-circuits the script, so
        # post-transition state is read on a fresh instance).
        fresh = _open_ui(db_path)
        _select_exception(fresh, "EXC-900002")

        assert "Operational History" in _text_values(
            fresh.header
        )

        # The history table is identified by its columns,
        # not by its position among the page's dataframes.
        history_table = [
            frame.value
            for frame in fresh.dataframe
            if "Event" in frame.value.columns
        ][0]

        history_events = history_table["Event"].tolist()

        assert "Recovery approved" in history_events
        assert "Recovery executed" in history_events

        assert "History Planner" in history_table[
            "Actor"
        ].tolist()

    finally:
        tmp.cleanup()


def test_recently_resolved_survives_resolution():
    """
    Scenario 8 (resolved visibility): a system-resolved
    exception leaves the open inbox but remains visible in
    the Recently Resolved surface with the factual path.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        # Resolve through the real system path BEFORE the
        # UI run: the execution resolves when the required
        # delivery admits it (established pattern).
        import app.database as database
        from app import services

        connection = database.get_connection()

        services.approve_recovery(
            connection,
            "ACT-000001",
            "UI Planner",
        )

        connection.execute(
            """
            UPDATE orders
            SET required_delivery_date = '2026-09-20'
            WHERE order_id = 'ORD-900001'
            """
        )
        connection.commit()

        outcome = services.execute_approved_recovery(
            connection,
            "ACT-000001",
        )

        assert outcome["exception_status"] == "Resolved"

        connection.close()

        app_test = _open_ui(db_path)

        # The resolved exception is gone from the open
        # inbox...
        options = list(_inbox_selectbox(app_test).options)

        assert not any(
            "EXC-900002" in option for option in options
        )

        # ...and visible in the Recently Resolved surface
        # with the system-executed path.
        assert _metric(
            app_test, "Recently Resolved"
        ) == "1"

        resolved_rows = app_test.dataframe[0].value

        row = resolved_rows.iloc[0]

        assert row["Exception"] == "EXC-900002"
        assert row["Resolution Path"] == (
            "System-executed recovery"
        )

    finally:
        tmp.cleanup()


# ==================================================
# CHECKPOINT R — HISTORY TRACEABILITY IN THE UI
# ==================================================

def test_history_visible_for_monitoring_exception():
    """
    The Operational History section renders for every
    investigated exception — including one with no feasible
    recovery (the Human Intervention branch) — so the
    planner can trace it too.
    """

    tmp, db_path = _build_database(with_pipeline=False)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900001")

        headers = _text_values(app_test.header)

        assert "Operational History" in headers

        history_table = [
            frame.value
            for frame in app_test.dataframe
            if "Event" in frame.value.columns
        ][0]

        events = history_table["Event"].tolist()

        # Persisted events, not fabricated ones: detection
        # is recorded; no options, decision or execution
        # ever happened for this exception.
        assert "Exception detected" in events
        assert "Recommendation generated" not in events
        assert "Recovery executed" not in events
        assert events[-1] == "Exception still open"

    finally:
        tmp.cleanup()


def test_history_shows_executed_still_open_honestly():
    """
    After the real UI workflow executes a recovery that
    cannot fix the delivery date, the rendered history
    contains the execution AND the still-open outcome —
    with the persisted ETA evidence — and never a resolved
    label.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        _widget(app_test, "text_input", "approver_").set_value(
            "Trace Planner"
        )
        _widget(app_test, "button", "approve_").click().run()
        _widget(app_test, "button", "execute_").click().run()

        assert not app_test.exception

        history_table = [
            frame.value
            for frame in app_test.dataframe
            if "Event" in frame.value.columns
        ][0]

        events = history_table["Event"].tolist()

        assert events == [
            "Exception detected",
            "Recovery options evaluated",
            "Recommendation generated",
            "Recovery approved",
            "Recovery executed",
            "Exception still open",
        ]

        outcome_detail = history_table["Detail"].tolist()[-1]

        # The still-open outcome carries the persisted
        # evidence: recorded arrival vs required delivery.
        assert "still misses required delivery" in outcome_detail

        # Chronological display order matches the persisted
        # story — execution precedes the outcome.
        assert events.index("Recovery executed") < events.index(
            "Exception still open"
        )

    finally:
        tmp.cleanup()


# ==================================================
# CHECKPOINT S — FOLLOW-UP & MONITORING IN THE UI
# ==================================================

def test_follow_up_metric_and_section_render():
    """
    After a recovery is executed without resolving the
    exception, the control tower reports the follow-up
    population and renders the Follow-up Required section
    with the factual persisted evidence.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        # Before execution nothing requires follow-up and
        # the section is not rendered.
        assert _metric(app_test, "Follow-up Required") == "0"
        assert "Follow-up Required" not in (
            _text_values(app_test.header)
        )

        _select_exception(app_test, "EXC-900002")

        _widget(app_test, "text_input", "approver_").set_value(
            "Follow-up Planner"
        )
        _widget(app_test, "button", "approve_").click().run()
        _widget(app_test, "button", "execute_").click().run()

        assert not app_test.exception

        # The follow-up count is a full-population metric.
        assert _metric(app_test, "Follow-up Required") == "1"

        # The bounded Follow-up Required section renders with
        # the persisted evidence, not a vague verdict.
        assert "Follow-up Required" in (
            _text_values(app_test.header)
        )

        follow_up_table = [
            frame.value
            for frame in app_test.dataframe
            if "Evidence" in frame.value.columns
        ][0]

        row = follow_up_table.iloc[0]

        assert row["Exception"] == "EXC-900002"
        assert row["Action"] == "ACT-000001"
        assert "2026-09-17" in row["Evidence"]
        assert "2026-09-15" in row["Evidence"]
        assert "remains later than required delivery" in (
            row["Evidence"]
        )

    finally:
        tmp.cleanup()


def test_investigation_shows_executed_still_open_state():
    """
    Re-opening an executed-but-still-open exception states
    the operational state plainly: Executed — still open,
    with the recorded arrival versus required delivery as
    the reason. It is never presented as resolved.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        _widget(app_test, "text_input", "approver_").set_value(
            "State Planner"
        )
        _widget(app_test, "button", "approve_").click().run()
        _widget(app_test, "button", "execute_").click().run()

        assert not app_test.exception

        warnings = _text_values(app_test.warning)

        assert any(
            "Executed — still open" in (value or "")
            for value in warnings
        ), "the executed-still-open state must be stated"

        evidence = [
            value
            for value in warnings
            if "remains later than required delivery" in (value or "")
        ]
        assert evidence, (
            "the state banner must carry the persisted evidence"
        )
        assert "2026-09-17" in evidence[0]
        assert "2026-09-15" in evidence[0]

        # The triage label in the inbox marks the exception
        # as follow-up work rather than plain actionable.
        options = list(_inbox_selectbox(app_test).options)

        assert any(
            "EXC-900002" in option
            and "Follow-up required" in option
            for option in options
        )

    finally:
        tmp.cleanup()


# ==================================================
# SCENARIO 15 — AI DECISION BRIEF (ADVISORY)
# ==================================================

def test_ai_decision_brief_is_advisory_and_preserves_determinism():
    """
    Checkpoint U: the investigation view offers an explicit,
    planner-triggered AI decision brief. The brief is clearly
    labelled advisory and grounded in the deterministic
    evidence; when the AI layer is unavailable the honest
    message is shown and the deterministic recommendation and
    rationale remain untouched. No brief is generated merely by
    opening the investigation view.
    """

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        subheaders = _text_values(app_test.subheader)

        # The section exists, sits beside the deterministic
        # sections, and starts with no brief generated.
        assert "AI Decision Brief" in subheaders

        captions = _text_values(app_test.caption)

        assert any(
            "Optional AI-assisted interpretation" in (c or "")
            for c in captions
        ), "no automatic AI call on view: idle state shown"

        # Explicit planner action generates the brief through
        # the real service layer and the built-in provider.
        _widget(
            app_test, "button", "ai_brief_"
        ).click().run()

        assert not app_test.exception

        subheaders = _text_values(app_test.subheader)

        assert "AI Decision Brief" in subheaders

        # Advisory labelling and grounded content.
        captions = _text_values(app_test.caption)

        assert any(
            "AI-assisted · Advisory only" in (c or "")
            for c in captions
        ), "the brief must be labelled advisory"

        writes = _text_values(app_test.markdown)

        assert any(
            "Situation" in (w or "") for w in writes
        ), "brief sections render"

        assert any(
            "EXC-900002" in (w or "") for w in writes
        ), "the brief quotes the real exception identifier"

        assert any(
            "does not approve, execute, or resolve" in (c or "")
            for c in captions
        ), "the advisory disclaimer is shown in the brief"

        # The deterministic sections remain visibly intact
        # alongside the advisory brief.
        assert "Recommended Recovery" in subheaders
        assert "Recommendation Rationale" in subheaders

        # The workflow boundary is untouched: approval still
        # requires the real workflow controls.
        assert _widget(
            app_test, "text_input", "approver_"
        ) is not None
        assert _widget(
            app_test, "button", "approve_"
        ) is not None

    finally:
        tmp.cleanup()


def test_ai_decision_brief_unavailable_keeps_deterministic_view():
    """
    When the AI layer fails, the UI shows the honest unavailable
    message and the deterministic recommendation, rationale and
    workflow controls remain fully available.
    """

    import app.ai_support as ai_support
    import app.services as services

    tmp, db_path = _build_database(with_pipeline=True)

    try:
        app_test = _open_ui(db_path)

        _select_exception(app_test, "EXC-900002")

        # AppTest executes the real UI in-process, so the
        # provider seam the service reads at call time can be
        # replaced with a failing provider: the planner clicks
        # the real button and the real failure path renders.
        class _FailingProvider:
            def __call__(self, evidence):
                raise ai_support.AiProviderError(
                    "simulated provider outage"
                )

        original = services.DEFAULT_PROVIDER
        services.DEFAULT_PROVIDER = _FailingProvider()

        try:
            _widget(
                app_test, "button", "ai_brief_"
            ).click().run()
        finally:
            services.DEFAULT_PROVIDER = original

        assert not app_test.exception

        infos = _text_values(app_test.info)

        assert any(
            "AI decision brief unavailable" in (i or "")
            for i in infos
        ), "the unavailable state must be shown honestly"

        subheaders = _text_values(app_test.subheader)

        # Deterministic decision support is unaffected.
        assert "Recommended Recovery" in subheaders
        assert "Recommendation Rationale" in subheaders
        assert "Recovery Options Comparison" in subheaders

        assert _widget(
            app_test, "button", "approve_"
        ) is not None

    finally:
        tmp.cleanup()
