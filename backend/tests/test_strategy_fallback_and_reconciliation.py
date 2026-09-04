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
    PaymentAdapterAccountLimitError,
    PaymentAdapterConfigurationError,
    PaymentAdapterError,
    PaymentAdapterRateLimitError,
    PaymentAdapterTimeoutError,
    PaymentLinkRequest,
    PaymentLinkResult,
    RazorpayMcpPaymentAdapter,
    RazorpayPaymentAdapter,
    get_execution_strategy_adapters,
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


def _setup_test_env(tmp_path: Path, mode: str = "rest_primary") -> tuple[TestClient, Session]:
    db_file = tmp_path / f"fallback_{mode}.db"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{db_file}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = "whsec_test_secret_123"
    os.environ["RAZORPAY_KEY_ID"] = "rzp_test_fallbackKey123"
    os.environ["RAZORPAY_KEY_SECRET"] = "fallbackSecret456"
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = mode
    os.environ["RAZORPAY_MCP_ENABLED"] = "true"
    os.environ["RAZORPAY_MCP_ENDPOINT"] = "https://mcp.razorpay.com/mcp"
    os.environ["RAZORPAY_MCP_AUTH_TOKEN"] = "mcp_token_secret_123"
    os.environ["APP_MODE"] = "test"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    session = get_session_local()()
    client = TestClient(create_app())
    return client, session


def _seed_opportunity(
    session: Session,
    *,
    amount: int = 120000,
    action: str = "CREATE_PAYMENT_LINK",
    status: str = "DETECTED",
) -> tuple[RevenueOpportunity, RecoveryDecision]:
    payment = Payment(
        razorpay_payment_id=f"pay_fb_{amount}",
        razorpay_order_id="order_fb_001",
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

    opp = RevenueOpportunity(
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
    session.add(opp)
    session.commit()
    session.refresh(opp)

    decision = RecoveryDecision(
        opportunity_id=opp.id,
        diagnosis="Automated network recovery.",
        evidence={"signals": [{"signal": "network_failure", "value": True}]},
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
    return opp, decision


def test_01_rest_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=100000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "plink_rest_001",
                "reference_id": f"recoveriq_{opp.id}_1",
                "status": "created",
                "short_url": "https://rzp.io/i/rest001",
                "amount": 100000,
                "currency": "INR",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"
    assert attempt.external_reference == "plink_rest_001"
    session.refresh(opp)
    assert opp.status == "PAYMENT_LINK_CREATED"

    link = session.scalar(select(RecoveryPaymentLink).where(RecoveryPaymentLink.opportunity_id == opp.id))
    assert link is not None
    assert link.payment_link_id == "plink_rest_001"
    assert "direct_rest" in link.external_response_reference.lower() or "razorpay_test" in link.external_response_reference.lower()


def test_02_mcp_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session = _setup_test_env(tmp_path, mode="mcp_primary")
    opp, dec = _seed_opportunity(session, amount=200000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        req_json = kwargs.get("json", {})
        return httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": req_json.get("id", "req-1"),
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "id": "plink_mcp_002",
                                "reference_id": f"recoveriq_{opp.id}_1",
                                "status": "created",
                                "short_url": "https://rzp.io/i/mcp002",
                                "amount": 200000,
                                "currency": "INR",
                            }),
                        }
                    ],
                    "data": {
                        "id": "plink_mcp_002",
                        "reference_id": f"recoveriq_{opp.id}_1",
                        "status": "created",
                        "short_url": "https://rzp.io/i/mcp002",
                    },
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"
    assert attempt.external_reference == "plink_mcp_002"

    link = session.scalar(select(RecoveryPaymentLink).where(RecoveryPaymentLink.opportunity_id == opp.id))
    assert link is not None
    assert link.payment_link_id == "plink_mcp_002"
    assert "mcp" in link.external_response_reference.lower()


def test_03_rest_unavailable_mcp_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=300000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    # REST fails with 500 API error, MCP succeeds
    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "api.razorpay.com" in url:
            return httpx.Response(
                status_code=500,
                json={"error": {"code": "SERVER_ERROR", "description": "Internal gateway error"}},
                request=httpx.Request("POST", url),
            )
        # MCP call
        return httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "req-fb",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "id": "plink_fb_mcp_003",
                                "reference_id": f"recoveriq_{opp.id}_1",
                                "status": "created",
                                "short_url": "https://rzp.io/i/fbmcp003",
                                "amount": 300000,
                                "currency": "INR",
                            }),
                        }
                    ],
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"
    assert attempt.external_reference == "plink_fb_mcp_003"

    # Check fallback audit event
    fallback_event = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.fallback.triggered")
    )
    assert fallback_event is not None
    assert fallback_event.metadata_json.get("primary_adapter") == "razorpay_test"
    assert fallback_event.metadata_json.get("fallback_adapter") == "razorpay_mcp"


def test_04_mcp_unavailable_rest_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session = _setup_test_env(tmp_path, mode="mcp_primary")
    opp, dec = _seed_opportunity(session, amount=400000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    # MCP fails with 503, REST succeeds
    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "mcp.razorpay.com" in url:
            return httpx.Response(
                status_code=503,
                json={"error": {"code": -32603, "message": "MCP server temporarily overloaded"}},
                request=httpx.Request("POST", url),
            )
        # REST call
        return httpx.Response(
            status_code=200,
            json={
                "id": "plink_fb_rest_004",
                "reference_id": f"recoveriq_{opp.id}_1",
                "status": "created",
                "short_url": "https://rzp.io/i/fbrest004",
                "amount": 400000,
                "currency": "INR",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"
    assert attempt.external_reference == "plink_fb_rest_004"

    fallback_event = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.fallback.triggered")
    )
    assert fallback_event is not None
    assert fallback_event.metadata_json.get("primary_adapter") == "razorpay_mcp"
    assert fallback_event.metadata_json.get("fallback_adapter") == "razorpay_test"


def test_05_rest_rate_limit_safe_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=500000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    # REST returns 429, MCP succeeds
    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "api.razorpay.com" in url:
            return httpx.Response(
                status_code=429,
                json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Too Many Requests"}},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "req-fb-ratelimit",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "id": "plink_fb_ratelimit_mcp",
                                "reference_id": f"recoveriq_{opp.id}_1",
                                "status": "created",
                                "short_url": "https://rzp.io/i/ratelimit005",
                                "amount": 500000,
                                "currency": "INR",
                            }),
                        }
                    ],
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"
    assert attempt.external_reference == "plink_fb_ratelimit_mcp"


def test_06_mcp_rate_limit_safe_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session = _setup_test_env(tmp_path, mode="mcp_primary")
    opp, dec = _seed_opportunity(session, amount=600000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    # MCP returns 429, REST succeeds
    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "mcp.razorpay.com" in url:
            return httpx.Response(
                status_code=429,
                json={"error": {"code": -32029, "message": "Rate limit exceeded on MCP server"}},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            status_code=200,
            json={
                "id": "plink_fb_ratelimit_rest",
                "reference_id": f"recoveriq_{opp.id}_1",
                "status": "created",
                "short_url": "https://rzp.io/i/ratelimit006",
                "amount": 600000,
                "currency": "INR",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"
    assert attempt.external_reference == "plink_fb_ratelimit_rest"


def test_07_timeout_reconciliation_existing_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Critical Safety Test: Primary times out -> reconciliation checks gateway -> finds link -> adopts without duplicate execution."""
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=170000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        raise httpx.ReadTimeout("Socket timeout while waiting for Razorpay response")

    def mock_get(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        # Reconciliation GET finds existing link with matching reference_id
        return httpx.Response(
            status_code=200,
            json={
                "payment_links": [
                    {
                        "id": "plink_reconciled_existing_007",
                        "reference_id": f"recoveriq_{opp.id}_1",
                        "status": "created",
                        "short_url": "https://rzp.io/i/reconciled007",
                        "amount": 170000,
                        "currency": "INR",
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)
    monkeypatch.setattr("app.gateway_adapters.httpx.get", mock_get)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"
    assert attempt.external_reference == "plink_reconciled_existing_007"

    # Verify reconciliation audit events
    recon_attempted = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.reconciliation.attempted")
    )
    assert recon_attempted is not None

    recon_resolved = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.reconciliation.resolved")
    )
    assert recon_resolved is not None
    assert recon_resolved.metadata_json.get("payment_link_id") == "plink_reconciled_existing_007"

    # Fallback should NOT have been triggered
    fallback_event = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.fallback.triggered")
    )
    assert fallback_event is None


def test_08_ambiguous_outcome_no_duplicate_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Critical Safety Test: Primary times out -> reconciliation checks gateway -> NOT found -> AMBIGUOUS -> fallback strictly BLOCKED."""
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=180000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        raise httpx.ReadTimeout("Network connection lost during creation")

    def mock_get(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        # Reconciliation returns empty items
        return httpx.Response(
            status_code=200,
            json={"payment_links": []},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)
    monkeypatch.setattr("app.gateway_adapters.httpx.get", mock_get)

    with pytest.raises(ValueError, match="adapter_timeout"):
        execute_recovery_attempt(
            session,
            opportunity_id=opp.id,
            decision_id=dec.id,
            policy_evaluation_id=policy.id,
        )

    # Verify reconciliation blocked audit
    recon_blocked = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.reconciliation.blocked")
    )
    assert recon_blocked is not None
    assert recon_blocked.metadata_json.get("fallback_prevented") is True

    # Check attempt is marked failure
    attempt = session.scalar(select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opp.id))
    assert attempt is not None
    assert attempt.status == "FAILED"
    assert attempt.failure_code == "ADAPTER_TIMEOUT"

    failed_audit = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.attempt.failed")
    )
    assert failed_audit is not None
    assert failed_audit.metadata_json.get("retryable") is True

    # No recovery payment link should have been created
    link_count = session.query(RecoveryPaymentLink).filter_by(opportunity_id=opp.id).count()
    assert link_count == 0


def test_09_policy_blocked_no_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Policy Gate rejection (BLOCK/ESCALATE) must halt recovery immediately without calling any adapter or fallback."""
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    # Amount 1,000,000 exceeds max_amount_cap (900,000) -> Hard Policy BLOCK
    opp, dec = _seed_opportunity(session, amount=1000000)

    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "BLOCK"

    with pytest.raises(ValueError, match="policy_not_allow"):
        execute_recovery_attempt(
            session,
            opportunity_id=opp.id,
            decision_id=dec.id,
            policy_evaluation_id=policy.id,
        )

    # No recovery attempt or fallback event should exist
    attempt = session.scalar(select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opp.id))
    assert attempt is None

    fallback_event = session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "recovery.fallback.triggered")
    )
    assert fallback_event is None


def test_10_duplicate_execution_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Duplicate execution on already active or executed opportunity returns existing attempt without calling adapters twice."""
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=190000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    call_count = 0

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code=200,
            json={
                "id": "plink_idempotent_010",
                "reference_id": f"recoveriq_{opp.id}_1",
                "status": "created",
                "short_url": "https://rzp.io/i/idempotent010",
                "amount": 190000,
                "currency": "INR",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt1 = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt1.status == "EXECUTED"
    assert call_count == 1

    # Second call for the same opportunity
    attempt2 = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt2.id == attempt1.id
    assert call_count == 1  # No second adapter call was made!


def test_11_both_adapters_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When primary and fallback both fail with non-recoverable error, system fails cleanly."""
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=195000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            status_code=500,
            json={"error": {"code": "SERVICE_UNAVAILABLE", "description": "All systems down"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    with pytest.raises(ValueError):
        execute_recovery_attempt(
            session,
            opportunity_id=opp.id,
            decision_id=dec.id,
            policy_evaluation_id=policy.id,
        )

    attempt = session.scalar(select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opp.id))
    assert attempt is not None
    assert attempt.status == "FAILED"


def test_12_successful_fallback_audit_trail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify complete audit trail fields during fallback."""
    client, session = _setup_test_env(tmp_path, mode="rest_primary")
    opp, dec = _seed_opportunity(session, amount=199000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
    assert policy.result == "ALLOW"

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "api.razorpay.com" in url:
            return httpx.Response(
                status_code=429,
                json={"error": {"code": "TOO_MANY_REQUESTS", "description": "Rate limit"}},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "req-audit",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "id": "plink_audit_012",
                                "reference_id": f"recoveriq_{opp.id}_1",
                                "status": "created",
                                "short_url": "https://rzp.io/i/audit012",
                                "amount": 199000,
                                "currency": "INR",
                            }),
                        }
                    ],
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    attempt = execute_recovery_attempt(
        session,
        opportunity_id=opp.id,
        decision_id=dec.id,
        policy_evaluation_id=policy.id,
    )
    assert attempt.status == "EXECUTED"

    events = session.scalars(
        select(AuditEvent).where(AuditEvent.entity_id == str(attempt.id)).order_by(AuditEvent.id)
    ).all()
    event_types = [e.event_type for e in events]

    assert "recovery.execution.started" in event_types
    assert "recovery.fallback.triggered" in event_types
    assert "recovery.payment_link.created" in event_types
    assert "recovery.verification.pending" in event_types

    created_event = next(e for e in events if e.event_type == "recovery.payment_link.created")
    assert created_event.metadata_json.get("used_fallback") is True
    assert created_event.metadata_json.get("original_strategy") == "REST_PRIMARY"
    assert created_event.metadata_json.get("execution_strategy") == "MCP"
