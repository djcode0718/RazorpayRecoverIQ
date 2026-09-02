import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.main import create_app
from app.models import AuditEvent, Payment, PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RevenueOpportunity
from app.outcome_verifier import verify_recovery_attempt_outcome


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = os.environ.get("TEST_RAZORPAY_WEBHOOK_SECRET", "mock_webhook_secret_key_03")
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase6_verifier.db'}"
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


def _seed_attempt_for_verifier(session: Session, *, payment_status: str) -> int:
    payment = Payment(
        razorpay_payment_id=f"pay_verifier_{payment_status}",
        razorpay_order_id="order_verifier",
        customer_id=None,
        amount_minor=180000,
        currency="INR",
        status=payment_status,
        method="card",
        captured=payment_status == "CAPTURED",
        failure_reason="network",
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)

    opportunity = RevenueOpportunity(
        customer_id=None,
        payment_id=payment.id,
        order_id=None,
        subscription_id=None,
        source_event_id=None,
        amount_at_risk_minor=180000,
        currency="INR",
        failure_category="NETWORK",
        failure_reason="network",
        recovery_probability=70,
        recovery_score=70,
        expected_recovery_minor=126000,
        estimated_intervention_cost_minor=200,
        expected_net_recovery_minor=125800,
        recommended_action="RETRY",
        confidence=80,
        status="DETECTED",
        expires_at=None,
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    decision = RecoveryDecision(
        opportunity_id=opportunity.id,
        diagnosis="Deterministic verifier test diagnosis with enough characters.",
        evidence={"signals": [{"signal": "failure_reason", "value": "network"}]},
        recovery_probability=70,
        confidence=80,
        recommended_action="RETRY",
        expected_recovery_minor=126000,
        estimated_cost_minor=200,
        expected_net_recovery_minor=125800,
        decision_source="AI",
        provider="mock",
        model="mock-v1",
        model_version="mock-v1",
        prompt_version="v1.0",
        schema_version="v1",
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)

    evaluation = PolicyEvaluation(
        opportunity_id=opportunity.id,
        decision_id=decision.id,
        result="ALLOW",
        reason_codes={"failed": [], "passed": ["all"]},
        evaluated_rules={"seeded": {"passed": True}},
        max_amount_check=True,
        confidence_check=True,
        retry_limit_check=True,
        economic_check=True,
        duplicate_check=True,
        environment_check=True,
        policy_version="v1.0",
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)

    attempt = RecoveryAttempt(
        opportunity_id=opportunity.id,
        action="RETRY",
        attempt_number=1,
        policy_evaluation_id=evaluation.id,
        status="EXECUTED",
        amount_minor=180000,
        currency="INR",
        external_reference="sim_exec_seed",
        recovered_amount_minor=0,
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt.id


def test_verifier_sets_success_only_after_captured_state(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)

    failed_payload = {
        "id": "evt_phase6_failed_001",
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": 1724301000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_phase6_001",
                    "order_id": "order_phase6_001",
                    "amount": 210000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    first = _post_webhook(client, failed_payload, secret)
    assert first.status_code == 200

    session = get_session_local()()
    try:
        attempt_before = session.execute(select(RecoveryAttempt).order_by(RecoveryAttempt.id.desc())).scalar_one()
        assert attempt_before.recovered_amount_minor == 0
        assert attempt_before.verified_outcome is None
    finally:
        session.close()

    captured_payload = {
        "id": "evt_phase6_captured_001",
        "event": "payment.captured",
        "account_id": "acc_test_001",
        "created_at": 1724301100,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_phase6_001",
                    "order_id": "order_phase6_001",
                    "amount": 210000,
                    "currency": "INR",
                    "method": "card",
                    "captured": True,
                }
            }
        },
    }
    second = _post_webhook(client, captured_payload, secret)
    assert second.status_code == 200
    assert second.json()["data"]["processing_status"] == "processed"

    session = get_session_local()()
    try:
        attempt_after = session.execute(select(RecoveryAttempt).order_by(RecoveryAttempt.id.desc())).scalar_one()
        assert attempt_after.verified_outcome == "VERIFIED_SUCCESS"
        assert attempt_after.recovered_amount_minor == 210000

        audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == "recovery.verification.completed")
            .where(AuditEvent.entity_id == "evt_phase6_captured_001")
        ).scalars().all()
        assert len(audits) == 1
    finally:
        session.close()


def test_verifier_marks_failure_with_zero_recovery(tmp_path: Path) -> None:
    _build_client(tmp_path)
    session = get_session_local()()
    try:
        attempt_id = _seed_attempt_for_verifier(session, payment_status="FAILED")
        verified = verify_recovery_attempt_outcome(session, attempt_id=attempt_id)

        assert verified is not None
        assert verified.verified_outcome == "VERIFIED_FAILURE"
        assert verified.recovered_amount_minor == 0
    finally:
        session.close()

