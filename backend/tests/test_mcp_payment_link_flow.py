import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any
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
    get_payment_adapter,
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


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _setup_mcp_test_env(tmp_path: Path) -> tuple[TestClient, Session, str]:
    secret = "mcp_test_webhook_secret_xyz"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'mcp_flow_test.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["RAZORPAY_KEY_ID"] = ""
    os.environ["RAZORPAY_KEY_SECRET"] = ""
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = "razorpay_mcp"
    os.environ["RAZORPAY_MCP_ENABLED"] = "true"
    os.environ["RAZORPAY_MCP_ENDPOINT"] = "https://mcp.razorpay.com/mcp"
    os.environ["RAZORPAY_MCP_AUTH_TOKEN"] = "mcp_test_auth_token_secret"
    os.environ["APP_MODE"] = "test"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    session = get_session_local()()
    client = TestClient(create_app())
    return client, session, secret


def _seed_opportunity_and_decision(
    session: Session,
    *,
    amount: int = 150000,
    action: str = "CREATE_PAYMENT_LINK",
    status: str = "DETECTED",
) -> tuple[RevenueOpportunity, RecoveryDecision]:
    payment = Payment(
        razorpay_payment_id=f"pay_mcp_{amount}",
        razorpay_order_id="order_mcp_001",
        customer_id=None,
        amount_minor=amount,
        currency="INR",
        status="FAILED",
        method="card",
        captured=False,
        failure_reason="network_error",
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
        amount_at_risk_minor=amount,
        currency="INR",
        failure_category="NETWORK",
        failure_reason="network_error",
        recovery_probability=85,
        recovery_score=85,
        expected_recovery_minor=int(amount * 0.85),
        estimated_intervention_cost_minor=200,
        expected_net_recovery_minor=int(amount * 0.85) - 200,
        recommended_action=action,
        confidence=90,
        status=status,
        expires_at=None,
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    decision = RecoveryDecision(
        opportunity_id=opportunity.id,
        diagnosis="Automated network recovery via Razorpay MCP Payment Link.",
        evidence={"signals": [{"signal": "gateway_timeout", "value": True}]},
        recovery_probability=85,
        confidence=90,
        recommended_action=action,
        expected_recovery_minor=int(amount * 0.85),
        estimated_cost_minor=200,
        expected_net_recovery_minor=int(amount * 0.85) - 200,
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


def test_mcp_payment_link_governed_execution_full_flow(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: Governed Opportunity -> Policy ALLOW -> MCP create_payment_link -> Attempt EXECUTED -> Webhook -> Realized."""
    client, session, webhook_secret = _setup_mcp_test_env(tmp_path)

    mcp_call_count = 0
    captured_payloads = []

    def _mock_mcp_post(url, *, json, headers, timeout):
        nonlocal mcp_call_count
        mcp_call_count += 1
        captured_payloads.append(json)
        assert json["method"] == "tools/call"
        assert json["params"]["name"] == "create_payment_link"
        args = json["params"]["arguments"]
        assert args["amount"] == 150000
        assert args["currency"] == "INR"
        assert "recoveriq_" in args["reference_id"]
        assert args["notes"]["recoveriq_opportunity_id"] is not None

        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                '{"id": "plink_mcp_test_abc123", "status": "created", '
                                '"short_url": "https://rzp.io/i/mcplink123", '
                                f'"reference_id": "{args["reference_id"]}", '
                                '"amount": 150000, "currency": "INR"}'
                            ),
                        }
                    ],
                    "data": {
                        "id": "plink_mcp_test_abc123",
                        "status": "created",
                        "short_url": "https://rzp.io/i/mcplink123",
                        "reference_id": args["reference_id"],
                    },
                },
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opportunity, decision = _seed_opportunity_and_decision(session, amount=150000)

        # 1. Policy Engine evaluation
        policy = evaluate_policy_for_decision(session, opportunity_id=opportunity.id, decision_id=decision.id)
        assert policy.result == "ALLOW"

        # 2. Governed execution via MCP
        attempt = execute_recovery_attempt(
            session,
            opportunity_id=opportunity.id,
            decision_id=decision.id,
            policy_evaluation_id=policy.id,
        )

        assert mcp_call_count == 1
        assert attempt.status == "EXECUTED"
        assert attempt.external_reference == "plink_mcp_test_abc123"
        assert attempt.recovered_amount_minor == 0  # NOT realized yet!

        session.refresh(opportunity)
        assert opportunity.status == "PAYMENT_LINK_CREATED"  # NOT RESOLVED yet!

        # 3. Verify Payment Link persistence
        link = session.execute(
            select(RecoveryPaymentLink).where(RecoveryPaymentLink.recovery_attempt_id == attempt.id)
        ).scalar_one()
        assert link.payment_link_id == "plink_mcp_test_abc123"
        assert link.status == "CREATED"
        metadata = json.loads(link.external_response_reference)
        assert metadata["adapter"] == "razorpay_mcp"
        assert metadata["short_url"] == "https://rzp.io/i/mcplink123"

        # 4. Verify AuditEvent creation
        audit_events = session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "RecoveryAttempt", AuditEvent.entity_id == str(attempt.id))
        ).scalars().all()
        assert len(audit_events) >= 1
        exec_audit = [e for e in audit_events if e.event_type == "recovery.payment_link.created"][0]
        assert exec_audit.result == "EXECUTED"
        assert exec_audit.metadata_json["adapter"] == "razorpay_mcp"
        assert exec_audit.metadata_json["operation"] in {"create_payment_link", "PAYMENT_LINK_CREATE"}
        assert exec_audit.metadata_json["payment_link_id"] == "plink_mcp_test_abc123"

        # 5. Simulate Webhook payment.captured / payment_link.paid
        webhook_payload = {
            "id": "evt_mcp_paid_001",
            "event": "payment_link.paid",
            "account_id": "acc_test_001",
            "created_at": 1724301500,
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": "plink_mcp_test_abc123",
                        "status": "paid",
                        "amount": 150000,
                        "currency": "INR",
                        "reference_id": link.payment_link_reference_id,
                    }
                },
                "payment": {
                    "entity": {
                        "id": "pay_mcp_captured_999",
                        "status": "captured",
                        "amount": 150000,
                        "currency": "INR",
                        "captured": True,
                    }
                },
            },
        }
        raw_body = json.dumps(webhook_payload).encode("utf-8")
        sig = _sign(raw_body, webhook_secret)
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={"x-razorpay-signature": sig, "content-type": "application/json"},
        )
        assert response.status_code == 200

        # 6. Verify Realized Recovery outcome
        session.refresh(attempt)
        session.refresh(opportunity)
        assert attempt.status == "VERIFIED"
        assert attempt.verified_outcome == "VERIFIED_SUCCESS"
        assert attempt.recovered_amount_minor == 150000
        assert opportunity.status in {"VERIFIED_RECOVERED", "RESOLVED"}

    finally:
        session.close()


def test_mcp_payment_link_policy_gate_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    """Policy Gate rejection (BLOCK) must never invoke MCP tool."""
    client, session, _ = _setup_mcp_test_env(tmp_path)

    mcp_called = False

    def _mock_mcp_post(url, *, json, headers, timeout):
        nonlocal mcp_called
        mcp_called = True
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "1", "result": {}})

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opportunity, decision = _seed_opportunity_and_decision(session, amount=150000)

        # Seed a blocking policy evaluation
        policy = PolicyEvaluation(
            opportunity_id=opportunity.id,
            decision_id=decision.id,
            result="BLOCK",
            reason_codes={"failed": ["excessive_daily_attempts"], "passed": []},
            evaluated_rules={"max_attempts": {"passed": False}},
            max_amount_check=True,
            confidence_check=True,
            retry_limit_check=False,
            economic_check=True,
            duplicate_check=True,
            environment_check=True,
            policy_version="v1.0",
        )
        session.add(policy)
        session.commit()
        session.refresh(policy)

        # Attempt execution via API endpoint
        response = client.post(f"/api/v1/opportunities/{opportunity.id}/execute")
        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "POLICY_NOT_ALLOW"

        # Directly calling recovery_executor must also fail closed
        with pytest.raises(ValueError, match="policy_not_allow"):
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity.id,
                decision_id=decision.id,
                policy_evaluation_id=policy.id,
            )

        assert mcp_called is False
        attempts = session.execute(select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)).scalars().all()
        assert len(attempts) == 0

    finally:
        session.close()


def test_mcp_payment_link_duplicate_prevention_idempotency(tmp_path: Path, monkeypatch) -> None:
    """Duplicate execution requests must reuse existing attempt without invoking MCP twice."""
    client, session, _ = _setup_mcp_test_env(tmp_path)

    mcp_call_count = 0

    def _mock_mcp_post(url, *, json, headers, timeout):
        nonlocal mcp_call_count
        mcp_call_count += 1
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json["id"],
                "result": {
                    "data": {
                        "id": "plink_mcp_idemp_111",
                        "status": "created",
                        "short_url": "https://rzp.io/i/idemp111",
                        "reference_id": "recoveriq_idemp",
                    }
                },
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opportunity, decision = _seed_opportunity_and_decision(session, amount=200000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opportunity.id, decision_id=decision.id)

        first_attempt = execute_recovery_attempt(
            session,
            opportunity_id=opportunity.id,
            decision_id=decision.id,
            policy_evaluation_id=policy.id,
        )
        assert first_attempt.status == "EXECUTED"
        assert mcp_call_count == 1

        # Second execution on same opportunity
        second_attempt = execute_recovery_attempt(
            session,
            opportunity_id=opportunity.id,
            decision_id=decision.id,
            policy_evaluation_id=policy.id,
        )
        assert second_attempt.id == first_attempt.id
        assert mcp_call_count == 1  # MCP was NOT called again

    finally:
        session.close()


def test_mcp_payment_link_server_unavailable_handling(tmp_path: Path, monkeypatch) -> None:
    """MCP server outage (503/network error) maps to ADAPTER_ERROR and creates audit event."""
    client, session, _ = _setup_mcp_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        return httpx.Response(503, json={"error": "Service Unavailable"})

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opportunity, decision = _seed_opportunity_and_decision(session, amount=100000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opportunity.id, decision_id=decision.id)

        with pytest.raises(ValueError, match="razorpay_mcp_http_error: HTTP 503"):
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity.id,
                decision_id=decision.id,
                policy_evaluation_id=policy.id,
            )

        attempts = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].status == "FAILED"
        assert attempts[0].failure_code == "ADAPTER_ERROR"

        audit_events = session.execute(
            select(AuditEvent).where(AuditEvent.entity_type == "RecoveryAttempt", AuditEvent.entity_id == str(attempts[0].id))
        ).scalars().all()
        assert any(e.event_type == "recovery.attempt.failed" for e in audit_events)

    finally:
        session.close()


def test_mcp_payment_link_malformed_response_handling(tmp_path: Path, monkeypatch) -> None:
    """Malformed MCP response (missing ID) fails safely without persisting broken payment link."""
    client, session, _ = _setup_mcp_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json["id"],
                "result": {"data": {"status": "created"}},  # Missing 'id'
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opportunity, decision = _seed_opportunity_and_decision(session, amount=100000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opportunity.id, decision_id=decision.id)

        with pytest.raises(ValueError, match="razorpay_mcp_payment_link_missing_id"):
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity.id,
                decision_id=decision.id,
                policy_evaluation_id=policy.id,
            )

        links = session.execute(
            select(RecoveryPaymentLink).where(RecoveryPaymentLink.opportunity_id == opportunity.id)
        ).scalars().all()
        assert len(links) == 0

        attempts = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].status == "FAILED"

    finally:
        session.close()


def test_mcp_payment_link_rate_limit_429_handling(tmp_path: Path, monkeypatch) -> None:
    """MCP HTTP 429 rate limit raises PaymentAdapterRateLimitError and records RATE_LIMIT_EXCEEDED."""
    client, session, _ = _setup_mcp_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        return httpx.Response(429, json={"error": {"code": -32000, "message": "Rate limit exceeded"}})

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opportunity, decision = _seed_opportunity_and_decision(session, amount=100000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opportunity.id, decision_id=decision.id)

        with pytest.raises(PaymentAdapterRateLimitError) as exc_info:
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity.id,
                decision_id=decision.id,
                policy_evaluation_id=policy.id,
            )
        assert exc_info.value.retry_after_seconds == 5

        attempts = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].status == "FAILED"
        assert attempts[0].failure_code == "RATE_LIMIT_EXCEEDED"

    finally:
        session.close()


def test_mcp_payment_link_timeout_ambiguous_outcome_handling(tmp_path: Path, monkeypatch) -> None:
    """MCP network timeout raises PaymentAdapterTimeoutError, marks attempt FAILED, does not duplicate."""
    client, session, _ = _setup_mcp_test_env(tmp_path)

    def _mock_mcp_post(url, *, json, headers, timeout):
        raise httpx.TimeoutException("MCP connection timed out")

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_mcp_post)

    try:
        opportunity, decision = _seed_opportunity_and_decision(session, amount=100000)
        policy = evaluate_policy_for_decision(session, opportunity_id=opportunity.id, decision_id=decision.id)

        with pytest.raises(ValueError, match="adapter_timeout"):
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity.id,
                decision_id=decision.id,
                policy_evaluation_id=policy.id,
            )

        attempts = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].status == "FAILED"
        assert attempts[0].failure_code == "ADAPTER_TIMEOUT"

        links = session.execute(
            select(RecoveryPaymentLink).where(RecoveryPaymentLink.opportunity_id == opportunity.id)
        ).scalars().all()
        assert len(links) == 0

    finally:
        session.close()
