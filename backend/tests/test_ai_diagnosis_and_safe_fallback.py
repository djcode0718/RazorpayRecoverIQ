import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.providers import DiagnosisContext, DiagnosisProvider
from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.main import create_app
from app.models import AuditEvent, RecoveryDecision, RevenueOpportunity


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = os.environ.get("TEST_RAZORPAY_WEBHOOK_SECRET", "mock_webhook_secret_key_01")
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase5.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app()), secret


def _post_failed_webhook(client: TestClient, *, secret: str, event_id: str, payment_id: str):
    payload = {
        "id": event_id,
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": 1724300900,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": "order_phase5_001",
                    "amount": 255000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = _sign(raw, secret)
    return client.post(
        "/api/v1/webhooks/razorpay",
        content=raw,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )


class _InvalidSchemaProvider(DiagnosisProvider):
    name = "invalid-mock"
    model_name = "invalid-v1"

    def generate_diagnosis(self, context: DiagnosisContext):
        return {
            "diagnosis": "short",
            "failure_category": context.failure_category,
            "recommended_action": "RETRY",
            "recovery_probability": "75",
            "confidence": 80,
            "evidence": [],
            "provider_metadata": {},
        }


def test_failed_payment_generates_structured_ai_recovery_decision(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    response = _post_failed_webhook(client, secret=secret, event_id="evt_phase5_001", payment_id="pay_phase5_001")
    assert response.status_code == 200

    session = get_session_local()()
    try:
        opportunity = session.execute(
            select(RevenueOpportunity).where(RevenueOpportunity.payment_id.is_not(None))
        ).scalars().first()
        assert opportunity is not None

        decision = session.execute(
            select(RecoveryDecision).where(RecoveryDecision.opportunity_id == opportunity.id)
        ).scalar_one()
        assert decision.decision_source == "AI"
        assert decision.provider == "mock"
        assert decision.recommended_action in {
            "CREATE_PAYMENT_LINK",
            "RETRY",
            "DELAYED_RETRY",
            "RECOVERY_PROMPT",
            "ESCALATE",
        }

        audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == "ai.decision.created")
            .where(AuditEvent.entity_id == "evt_phase5_001")
        ).scalars().all()
        assert len(audits) == 1
    finally:
        session.close()


def test_schema_validation_failure_escalates_safely(tmp_path: Path, monkeypatch) -> None:
    from app import recovery_intelligence

    monkeypatch.setattr(recovery_intelligence, "get_provider", lambda: _InvalidSchemaProvider())

    client, secret = _build_client(tmp_path)
    response = _post_failed_webhook(client, secret=secret, event_id="evt_phase5_002", payment_id="pay_phase5_002")
    assert response.status_code == 200

    session = get_session_local()()
    try:
        decision = session.execute(select(RecoveryDecision).order_by(RecoveryDecision.id.desc())).scalar_one()
        assert decision.decision_source == "AI_FALLBACK"
        assert decision.recommended_action == "ESCALATE"

        audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == "ai.decision.escalated_safe")
            .where(AuditEvent.entity_id == "evt_phase5_002")
        ).scalars().all()
        assert len(audits) == 1
        assert "ai_diagnosis_failed" in (audits[0].reason or "")
    finally:
        session.close()

