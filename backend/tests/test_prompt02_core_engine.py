import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.main import create_app
from app.models import AuditEvent, PolicyEvaluation, RecoveryAttempt, RecoveryOutcome, RevenueOpportunity
from app.state_machine import can_transition_recovery


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = "whsec_prompt02"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'prompt02.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    os.environ["APP_MODE"] = "simulation"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app()), secret


def _post(client: TestClient, payload: dict, secret: str):
    raw = json.dumps(payload).encode("utf-8")
    return client.post(
        "/api/v1/webhooks/razorpay",
        content=raw,
        headers={"x-razorpay-signature": _sign(raw, secret), "content-type": "application/json"},
    )


def test_recovery_state_machine_blocks_invalid_transitions() -> None:
    assert can_transition_recovery("IDENTIFIED", "ANALYZED") is True
    assert can_transition_recovery("IDENTIFIED", "VERIFIED_RECOVERED") is False
    assert can_transition_recovery("POLICY_BLOCKED", "PAYMENT_LINK_CREATED") is False


def test_policy_can_escalate_and_persist_rules(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = {
        "id": "evt_prompt02_escalate_001",
        "event": "payment.failed",
        "account_id": "acc_prompt02",
        "created_at": 1724302600,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_prompt02_escalate_001",
                    "order_id": "order_prompt02_escalate_001",
                    "amount": 980000,
                    "currency": "INR",
                    "captured": False,
                    "error_reason": "unknown_reason",
                }
            }
        },
    }

    response = _post(client, payload, secret)
    assert response.status_code == 200

    session = get_session_local()()
    try:
        policy = session.execute(select(PolicyEvaluation).order_by(PolicyEvaluation.id.desc())).scalar_one()
        assert policy.result == "ESCALATE"
        assert policy.evaluated_rules["allowlisted_action"]["passed"] is False
    finally:
        session.close()


def test_verified_recovery_only_after_captured_event(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)

    failed = {
        "id": "evt_prompt02_success_001",
        "event": "payment.failed",
        "account_id": "acc_prompt02",
        "created_at": 1724302700,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_prompt02_success_001",
                    "order_id": "order_prompt02_success_001",
                    "amount": 210000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    captured = {
        "id": "evt_prompt02_success_002",
        "event": "payment.captured",
        "account_id": "acc_prompt02",
        "created_at": 1724302710,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_prompt02_success_001",
                    "order_id": "order_prompt02_success_001",
                    "amount": 210000,
                    "currency": "INR",
                    "method": "card",
                    "captured": True,
                }
            }
        },
    }

    first = _post(client, failed, secret)
    assert first.status_code == 200

    session = get_session_local()()
    try:
        attempt = session.execute(select(RecoveryAttempt).order_by(RecoveryAttempt.id.desc())).scalar_one()
        assert attempt.recovered_amount_minor == 0
        assert attempt.verified_outcome is None
    finally:
        session.close()

    second = _post(client, captured, secret)
    assert second.status_code == 200

    session = get_session_local()()
    try:
        attempt = session.execute(select(RecoveryAttempt).order_by(RecoveryAttempt.id.desc())).scalar_one()
        assert attempt.verified_outcome == "VERIFIED_SUCCESS"
        assert attempt.recovered_amount_minor == 210000

        opportunity = session.execute(select(RevenueOpportunity).order_by(RevenueOpportunity.id.desc())).scalar_one()
        assert opportunity.status == "VERIFIED_RECOVERED"

        outcomes = session.execute(
            select(RecoveryOutcome).where(RecoveryOutcome.attempt_id == attempt.id)
        ).scalars().all()
        assert len(outcomes) >= 1

        events = session.execute(
            select(AuditEvent.event_type)
            .where(AuditEvent.entity_type == "RecoveryWorkflow")
            .where(AuditEvent.entity_id == "payment:pay_prompt02_success_001")
        ).scalars().all()
        assert "outcome.verified" in events
    finally:
        session.close()


def test_demo_seed_creates_minimum_twelve_opportunities_and_duplicate_event(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)
    response = client.post("/api/v1/demo/seed-core-recovery")
    assert response.status_code == 200
    payload = response.json()["data"]

    assert payload["seeded_opportunities"] >= 12
    assert payload["duplicate_events"] >= 1
    assert payload["policy_counts"]["allow"] >= 1
    assert payload["policy_counts"]["block"] >= 1
    assert payload["policy_counts"]["escalate"] >= 1
