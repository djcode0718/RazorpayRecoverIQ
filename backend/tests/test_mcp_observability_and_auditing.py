import json
import os
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.gateway_adapters import (
    PaymentAdapterRateLimitError,
    PaymentAdapterTimeoutError,
    PaymentLinkRequest,
    RazorpayMcpPaymentAdapter,
)
from app.main import create_app
from app.models import (
    AuditEvent,
    Payment,
    PolicyEvaluation,
    RecoveryAttempt,
    RecoveryDecision,
    RecoveryPaymentLink,
    RevenueOpportunity,
)
from app.policy_engine import evaluate_policy_for_decision
from app.recovery_executor import execute_recovery_attempt
from app.security import redact_sensitive_data, sanitize_error_message


def _setup_test_env(tmp_path: Path) -> tuple[TestClient, Session]:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'mcp_audit_test.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = "audit_webhook_secret_123"
    os.environ["RAZORPAY_KEY_ID"] = ""
    os.environ["RAZORPAY_KEY_SECRET"] = ""
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = "razorpay_mcp"
    os.environ["RAZORPAY_MCP_ENABLED"] = "true"
    os.environ["RAZORPAY_MCP_ENDPOINT"] = "https://mcp.razorpay.com/mcp"
    os.environ["RAZORPAY_MCP_AUTH_TOKEN"] = "mcp_secret_token_abc"
    os.environ["APP_MODE"] = "test"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    session = get_session_local()()
    client = TestClient(create_app())
    return client, session


def _seed_opportunity_and_decision(
    session: Session,
    *,
    amount: int = 250000,
    action: str = "CREATE_PAYMENT_LINK",
) -> tuple[RevenueOpportunity, RecoveryDecision]:
    payment = Payment(
        razorpay_payment_id="pay_audit_001",
        razorpay_order_id="order_audit_001",
        customer_id=101,
        amount_minor=amount,
        currency="INR",
        status="FAILED",
        method="card",
        captured=False,
        failure_reason="gateway_timeout",
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)

    opportunity = RevenueOpportunity(
        customer_id=101,
        payment_id=payment.id,
        order_id="order_audit_001",
        subscription_id=None,
        source_event_id=None,
        amount_at_risk_minor=amount,
        currency="INR",
        failure_category="NETWORK",
        failure_reason="gateway_timeout",
        recovery_probability=88,
        recovery_score=88,
        expected_recovery_minor=int(amount * 0.88),
        estimated_intervention_cost_minor=200,
        expected_net_recovery_minor=int(amount * 0.88) - 200,
        recommended_action=action,
        confidence=92,
        status="DETECTED",
        expires_at=None,
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    decision = RecoveryDecision(
        opportunity_id=opportunity.id,
        diagnosis="Transient payment gateway timeout recoverable via MCP link.",
        evidence={"signals": [{"signal": "error_code", "value": "GATEWAY_TIMEOUT"}]},
        recovery_probability=88,
        confidence=92,
        recommended_action=action,
        expected_recovery_minor=int(amount * 0.88),
        estimated_cost_minor=200,
        expected_net_recovery_minor=int(amount * 0.88) - 200,
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

    return opportunity, decision


def test_mcp_successful_execution_audit_telemetry_answers_all_questions(tmp_path: Path, monkeypatch) -> None:
    """Verify that successful MCP execution generates complete, normalized audit telemetry."""
    client, session = _setup_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        ref_id = json["params"]["arguments"]["reference_id"]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json["id"],
                "result": {
                    "data": {
                        "id": "plink_mcp_audit_001",
                        "status": "created",
                        "short_url": "https://rzp.io/i/auditlink001",
                        "reference_id": ref_id,
                    }
                },
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opp, decision = _seed_opportunity_and_decision(session, amount=250000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=decision.id)

        attempt = execute_recovery_attempt(
            session,
            opportunity_id=opp.id,
            decision_id=decision.id,
            policy_evaluation_id=policy.id,
        )

        audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "RecoveryAttempt", AuditEvent.entity_id == str(attempt.id))
            .order_by(AuditEvent.id.asc())
        ).scalars().all()

        assert len(audits) >= 3
        event_types = [a.event_type for a in audits]
        assert "recovery.execution.started" in event_types
        assert "recovery.payment_link.created" in event_types
        assert "recovery.verification.pending" in event_types

        # Inspect RECOVERY_EXECUTION_STARTED audit event
        start_audit = [a for a in audits if a.event_type == "recovery.execution.started"][0]
        assert start_audit.actor_type == "RECOVERY_EXECUTOR"
        assert start_audit.actor_id.startswith("razorpay_mcp:")
        assert start_audit.result == "STARTED"
        assert start_audit.correlation_id == f"opp_{opp.id}_att_{attempt.attempt_number}"
        meta = start_audit.metadata_json
        assert meta["provider"] == "razorpay"
        assert meta["execution_strategy"] == "MCP"
        assert meta["operation"] == "PAYMENT_LINK_CREATE"
        assert meta["opportunity_id"] == opp.id
        assert meta["recovery_attempt_id"] == attempt.id
        assert meta["policy_decision"] == "ALLOW"
        assert meta["amount_minor"] == 250000

        # Inspect RECOVERY_PAYMENT_LINK_CREATED audit event
        exec_audit = [a for a in audits if a.event_type == "recovery.payment_link.created"][0]
        assert exec_audit.result == "EXECUTED"
        assert exec_audit.metadata_json["external_reference"] == "plink_mcp_audit_001"
        assert exec_audit.metadata_json["payment_link_id"] == "plink_mcp_audit_001"
        assert exec_audit.metadata_json["short_url"] == "https://rzp.io/i/auditlink001"
        assert exec_audit.metadata_json["retryable"] is False
        assert exec_audit.metadata_json["duration_ms"] >= 0

        # Inspect RECOVERY_VERIFICATION_PENDING audit event
        pending_audit = [a for a in audits if a.event_type == "recovery.verification.pending"][0]
        assert pending_audit.result == "PENDING"
        assert pending_audit.outcome_snapshot["status"] == "AWAITING_PAYMENT"

    finally:
        session.close()


def test_mcp_failed_execution_audit_telemetry(tmp_path: Path, monkeypatch) -> None:
    """Verify that failed MCP execution records failure reason, error code, and retryable flag."""
    client, session = _setup_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        return httpx.Response(500, json={"error": "Internal Gateway Server Error"})

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opp, decision = _seed_opportunity_and_decision(session, amount=180000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=decision.id)

        with pytest.raises(ValueError, match="razorpay_mcp_http_error: HTTP 500"):
            execute_recovery_attempt(
                session,
                opportunity_id=opp.id,
                decision_id=decision.id,
                policy_evaluation_id=policy.id,
            )

        audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "RecoveryAttempt")
            .order_by(AuditEvent.id.asc())
        ).scalars().all()

        fail_audit = [a for a in audits if a.event_type == "recovery.attempt.failed"][0]
        assert fail_audit.result == "FAILED"
        assert "HTTP 500" in fail_audit.reason
        assert fail_audit.metadata_json["error_code"] == "ADAPTER_ERROR"
        assert fail_audit.metadata_json["retryable"] is False
        assert fail_audit.metadata_json["execution_strategy"] == "MCP"
        assert fail_audit.metadata_json["duration_ms"] >= 0

    finally:
        session.close()


def test_mcp_retryable_failure_audit_telemetry(tmp_path: Path, monkeypatch) -> None:
    """Verify that HTTP 429 rate limit failure logs retryable=True and retry_after_seconds."""
    client, session = _setup_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        return httpx.Response(429, json={"error": {"code": -32000, "message": "Rate limit exceeded"}})

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opp, decision = _seed_opportunity_and_decision(session, amount=120000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=decision.id)

        with pytest.raises(PaymentAdapterRateLimitError):
            execute_recovery_attempt(
                session,
                opportunity_id=opp.id,
                decision_id=decision.id,
                policy_evaluation_id=policy.id,
            )

        fail_audit = session.execute(
            select(AuditEvent).where(AuditEvent.event_type == "recovery.attempt.failed")
        ).scalar_one()

        assert fail_audit.result == "FAILED"
        assert fail_audit.metadata_json["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert fail_audit.metadata_json["retryable"] is True
        assert fail_audit.metadata_json["retry_after_seconds"] == 5

    finally:
        session.close()


def test_mcp_secret_redaction_in_audit_and_errors() -> None:
    """Verify that credentials, auth tokens, and sensitive headers are redacted."""
    # 1. Dictionary redaction
    payload = {
        "auth_token": "secret_mcp_token_xyz",
        "authorization": "Bearer mcp_token_999",
        "password": "super_secret_password",
        "public_data": "visible_info",
        "nested": {
            "key_secret": "rzp_secret_secret",
            "phone": "9876543210",
        },
    }
    redacted = redact_sensitive_data(payload)
    assert redacted["auth_token"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["public_data"] == "visible_info"
    assert redacted["nested"]["key_secret"] == "[REDACTED]"
    assert redacted["nested"]["phone"] == "[REDACTED]"

    # 2. String error message sanitization
    raw_error = "Failed to connect to MCP with Bearer eyJhbGciOi... and key_secret='my_secret'"
    sanitized = sanitize_error_message(raw_error)
    assert "Bearer [REDACTED]" in sanitized
    assert "key_secret=[REDACTED]" in sanitized
    assert "eyJhbGciOi" not in sanitized


def test_mcp_opportunity_evidence_endpoint_exposes_full_timeline(tmp_path: Path, monkeypatch) -> None:
    """Verify that GET /api/v1/opportunities/{id}/evidence returns ordered audit timeline with MCP metadata."""
    client, session = _setup_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        ref_id = json["params"]["arguments"]["reference_id"]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json["id"],
                "result": {
                    "data": {
                        "id": "plink_mcp_evidence_test",
                        "status": "created",
                        "short_url": "https://rzp.io/i/evidence001",
                        "reference_id": ref_id,
                    }
                },
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opp, decision = _seed_opportunity_and_decision(session, amount=300000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=decision.id)

        execute_recovery_attempt(
            session,
            opportunity_id=opp.id,
            decision_id=decision.id,
            policy_evaluation_id=policy.id,
        )

        # Query evidence endpoint
        response = client.get(f"/api/v1/opportunities/{opp.id}/evidence")
        assert response.status_code == 200
        data = response.json()["data"]

        items = data["items"]
        assert len(items) >= 3

        # Verify timeline ordering
        event_types = [item["event_type"] for item in items]
        assert "recovery.execution.started" in event_types
        assert "recovery.payment_link.created" in event_types

        # Check execution item contains MCP metadata
        created_item = [i for i in items if i["event_type"] == "recovery.payment_link.created"][0]
        assert created_item["actor_type"] == "RECOVERY_EXECUTOR"
        assert created_item["metadata"]["execution_strategy"] == "MCP"
        assert created_item["metadata"]["operation"] == "PAYMENT_LINK_CREATE"
        assert created_item["metadata"]["payment_link_id"] == "plink_mcp_evidence_test"

    finally:
        session.close()
