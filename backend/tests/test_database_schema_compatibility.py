import os
import sqlite3
from pathlib import Path

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.models import AuditEvent, PolicyEvaluation


def test_init_db_heals_missing_policy_evaluations_evaluated_rules(tmp_path: Path) -> None:
    db_path = tmp_path / "schema_drift.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE policy_evaluations (
                id INTEGER PRIMARY KEY,
                opportunity_id INTEGER NOT NULL,
                decision_id INTEGER NOT NULL,
                result VARCHAR(16) NOT NULL,
                reason_codes JSON NOT NULL,
                max_amount_check BOOLEAN NOT NULL DEFAULT 0,
                confidence_check BOOLEAN NOT NULL DEFAULT 0,
                retry_limit_check BOOLEAN NOT NULL DEFAULT 0,
                economic_check BOOLEAN NOT NULL DEFAULT 0,
                duplicate_check BOOLEAN NOT NULL DEFAULT 0,
                environment_check BOOLEAN NOT NULL DEFAULT 0,
                evaluated_at DATETIME NOT NULL,
                policy_version VARCHAR(32) NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()

    session = get_session_local()()
    try:
        row = PolicyEvaluation(
            opportunity_id=1,
            decision_id=1,
            result="ALLOW",
            reason_codes={"failed": [], "passed": ["POLICY_TEST_PASS"]},
            evaluated_rules={"test": {"passed": True}},
            max_amount_check=True,
            confidence_check=True,
            retry_limit_check=True,
            economic_check=True,
            duplicate_check=True,
            environment_check=True,
            policy_version="phase6-v1",
        )
        session.add(row)
        session.commit()

        saved = session.query(PolicyEvaluation).first()
        assert saved is not None
        assert saved.evaluated_rules["test"]["passed"] is True
    finally:
        session.close()


def test_init_db_heals_missing_audit_events_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "schema_drift_audit.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                event_type VARCHAR(128) NOT NULL,
                actor_type VARCHAR(64) NOT NULL,
                entity_type VARCHAR(64) NOT NULL,
                entity_id VARCHAR(128) NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()

    session = get_session_local()()
    try:
        session.add(
            AuditEvent(
                event_type="workflow.stage.policy",
                actor_type="SYSTEM",
                entity_type="RecoveryWorkflow",
                entity_id="payment:pay_demo_001",
                result="success",
                metadata_json={"k": "v"},
                input_snapshot={"x": 1},
                decision_snapshot={"y": 2},
                policy_snapshot={"z": 3},
                outcome_snapshot={"status": "allow"},
                reason="schema-heal-test",
            )
        )
        session.commit()

        saved = session.query(AuditEvent).first()
        assert saved is not None
        assert saved.result == "success"
        assert saved.metadata_json == {"k": "v"}
    finally:
        session.close()

