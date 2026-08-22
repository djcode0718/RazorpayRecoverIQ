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
from app.models import AuditEvent, Payment, PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RevenueOpportunity


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = "whsec_phase7"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase7.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app()), secret


def _post_webhook(client: TestClient, payload: dict, secret: str):
    raw = json.dumps(payload).encode("utf-8")
    signature = _sign(raw, secret)
    return client.post(
        "/api/v1/webhooks/razorpay",
        content=raw,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )


def _failed_payload(*, event_id: str, payment_id: str, created_at: int, amount: int) -> dict:
    return {
        "id": event_id,
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": created_at,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": "order_phase7_001",
                    "amount": amount,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }


def _captured_payload(*, event_id: str, payment_id: str, created_at: int, amount: int) -> dict:
    return {
        "id": event_id,
        "event": "payment.captured",
        "account_id": "acc_test_001",
        "created_at": created_at,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": "order_phase7_001",
                    "amount": amount,
                    "currency": "INR",
                    "method": "card",
                    "captured": True,
                }
            }
        },
    }


def test_phase7_detection_to_verification_flow_persists_full_chain(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)

    failed_response = _post_webhook(
        client,
        _failed_payload(event_id="evt_phase7_001", payment_id="pay_phase7_001", created_at=1724301200, amount=210000),
        secret,
    )
    captured_response = _post_webhook(
        client,
        _captured_payload(event_id="evt_phase7_002", payment_id="pay_phase7_001", created_at=1724301300, amount=210000),
        secret,
    )

    assert failed_response.status_code == 200
    assert captured_response.status_code == 200
    assert captured_response.json()["data"]["processing_status"] == "processed"

    session = get_session_local()()
    try:
        payment = session.execute(
            select(Payment).where(Payment.razorpay_payment_id == "pay_phase7_001")
        ).scalar_one()
        assert payment.status == "CAPTURED"

        opportunity = session.execute(
            select(RevenueOpportunity).where(RevenueOpportunity.payment_id == payment.id)
        ).scalar_one()
        decision = session.execute(
            select(RecoveryDecision).where(RecoveryDecision.opportunity_id == opportunity.id)
        ).scalar_one()
        policy = session.execute(
            select(PolicyEvaluation).where(PolicyEvaluation.decision_id == decision.id)
        ).scalar_one()
        attempt = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)
        ).scalar_one()

        assert policy.result == "ALLOW"
        assert attempt.verified_outcome == "VERIFIED_SUCCESS"
        assert attempt.recovered_amount_minor == 210000

        workflow_chain_id = "payment:pay_phase7_001"
        stage_audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "RecoveryWorkflow")
            .where(AuditEvent.entity_id == workflow_chain_id)
            .order_by(AuditEvent.id.asc())
        ).scalars().all()
        stage_event_types = [audit.event_type for audit in stage_audits]

        assert "workflow.stage.detection" in stage_event_types
        assert "workflow.stage.diagnosis" in stage_event_types
        assert "workflow.stage.policy" in stage_event_types
        assert "workflow.stage.execution" in stage_event_types
        assert "workflow.stage.verification" in stage_event_types

        business_events = session.execute(
            select(AuditEvent.event_type)
            .where(AuditEvent.entity_type == "RecoveryWorkflow")
            .where(AuditEvent.entity_id == workflow_chain_id)
        ).scalars().all()
        assert "opportunity.created" in business_events
        assert "analysis.completed" in business_events
        assert "policy.evaluated" in business_events
        assert "recovery.executed" in business_events
        assert "outcome.verified" in business_events
    finally:
        session.close()


def test_phase7_policy_block_still_persists_chain_and_blocks_execution(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)

    failed_response = _post_webhook(
        client,
        _failed_payload(event_id="evt_phase7_003", payment_id="pay_phase7_002", created_at=1724301400, amount=1_500_000),
        secret,
    )
    assert failed_response.status_code == 200

    session = get_session_local()()
    try:
        payment = session.execute(
            select(Payment).where(Payment.razorpay_payment_id == "pay_phase7_002")
        ).scalar_one()
        opportunity = session.execute(
            select(RevenueOpportunity).where(RevenueOpportunity.payment_id == payment.id)
        ).scalar_one()
        decision = session.execute(
            select(RecoveryDecision).where(RecoveryDecision.opportunity_id == opportunity.id)
        ).scalar_one()
        policy = session.execute(
            select(PolicyEvaluation).where(PolicyEvaluation.decision_id == decision.id)
        ).scalar_one()

        assert policy.result == "BLOCK"
        assert "POLICY_max_amount_FAILED" in policy.reason_codes["failed"]

        attempts = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)
        ).scalars().all()
        assert attempts == []

        workflow_chain_id = "payment:pay_phase7_002"
        execution_audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "RecoveryWorkflow")
            .where(AuditEvent.entity_id == workflow_chain_id)
            .where(AuditEvent.event_type == "workflow.stage.execution")
        ).scalars().all()
        assert len(execution_audits) == 1
        assert execution_audits[0].outcome_snapshot["status"] == "blocked_by_policy"
    finally:
        session.close()
