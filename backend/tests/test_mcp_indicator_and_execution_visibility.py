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
from app.main import create_app
from app.models import (
    Payment,
    PolicyEvaluation,
    RecoveryAttempt,
    RecoveryDecision,
    RecoveryPaymentLink,
    RevenueOpportunity,
    WebhookEvent,
)
from app.policy_engine import evaluate_policy_for_decision
from app.recovery_executor import execute_recovery_attempt


def _setup_env(tmp_path: Path, mode: str = "rest_primary", mcp_enabled: bool = True) -> tuple[TestClient, Session]:
    db_file = tmp_path / f"ui_test_{mode}_{mcp_enabled}.db"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{db_file}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = "whsec_test_secret_123"
    os.environ["RAZORPAY_KEY_ID"] = "rzp_test_mockKey123"
    os.environ["RAZORPAY_KEY_SECRET"] = "mockSecret456"
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = mode
    os.environ["RAZORPAY_MCP_ENABLED"] = "true" if mcp_enabled else "false"
    os.environ["RAZORPAY_MCP_ENDPOINT"] = "https://mcp.razorpay.com/mcp" if mcp_enabled else ""
    os.environ["RAZORPAY_MCP_AUTH_TOKEN"] = "mcp_token_secret_123" if mcp_enabled else ""
    os.environ["APP_MODE"] = "test"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    session = get_session_local()()
    client = TestClient(create_app())
    return client, session


def _seed_opp(session: Session, amount: int = 150000) -> tuple[RevenueOpportunity, RecoveryDecision]:
    payment = Payment(
        razorpay_payment_id=f"pay_ui_{amount}",
        razorpay_order_id="order_ui_001",
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
        recommended_action="CREATE_PAYMENT_LINK",
        confidence=90,
        status="DETECTED",
        expires_at=None,
    )
    session.add(opp)
    session.commit()
    session.refresh(opp)

    dec = RecoveryDecision(
        opportunity_id=opp.id,
        diagnosis="Automated network recovery.",
        evidence={"signals": [{"signal": "network_failure", "value": True}]},
        recovery_probability=85,
        confidence=90,
        recommended_action="CREATE_PAYMENT_LINK",
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
    session.add(dec)
    session.commit()
    session.refresh(dec)
    return opp, dec


def test_01_mcp_indicator_available(tmp_path: Path) -> None:
    """When MCP is configured and test mode is active with REST_PRIMARY strategy, status is AVAILABLE."""
    client, session = _setup_env(tmp_path, mode="rest_primary", mcp_enabled=True)
    res = client.get("/api/v1/dashboard/summary")
    assert res.status_code == 200
    data = res.json()["data"]
    op_status = data["operating_status"]
    assert op_status["mcp_status"] == "AVAILABLE"
    assert "available as fallback" in op_status["mcp_note"].lower()
    assert op_status["payment_environment"] == "RAZORPAY TEST"


def test_02_mcp_indicator_active(tmp_path: Path) -> None:
    """When MCP is configured and strategy is MCP_PRIMARY / MCP_ONLY, status is ACTIVE."""
    client, session = _setup_env(tmp_path, mode="mcp_primary", mcp_enabled=True)
    res = client.get("/api/v1/dashboard/summary")
    assert res.status_code == 200
    data = res.json()["data"]
    op_status = data["operating_status"]
    assert op_status["mcp_status"] == "ACTIVE"
    assert "mcp active" in op_status["mcp_note"].lower()


def test_03_mcp_indicator_not_configured(tmp_path: Path) -> None:
    """When MCP is disabled, status is NOT_CONFIGURED."""
    client, session = _setup_env(tmp_path, mode="rest_only", mcp_enabled=False)
    res = client.get("/api/v1/dashboard/summary")
    assert res.status_code == 200
    data = res.json()["data"]
    op_status = data["operating_status"]
    assert op_status["mcp_status"] == "NOT_CONFIGURED"


def test_04_mcp_indicator_unavailable_on_live_keys(tmp_path: Path) -> None:
    """When live keys are detected, MCP status is UNAVAILABLE (hard-blocked)."""
    client, session = _setup_env(tmp_path, mode="rest_primary", mcp_enabled=True)
    os.environ["RAZORPAY_KEY_ID"] = "rzp_live_forbiddenKey"
    get_settings.cache_clear()

    res = client.get("/api/v1/dashboard/summary")
    assert res.status_code == 200
    data = res.json()["data"]
    op_status = data["operating_status"]
    assert op_status["mcp_status"] == "UNAVAILABLE"
    assert "live mode" in op_status["mcp_note"].lower()


def test_05_execution_strategy_direct_rest_visibility(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When an opportunity is executed via Direct REST, opportunity detail returns execution_strategy='DIRECT_REST'."""
    client, session = _setup_env(tmp_path, mode="rest_primary", mcp_enabled=True)
    opp, dec = _seed_opp(session, amount=120000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "id": "plink_ui_rest_001",
                "reference_id": f"recoveriq_{opp.id}_1",
                "status": "created",
                "short_url": "https://rzp.io/i/uirest001",
                "amount": 120000,
                "currency": "INR",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    execute_recovery_attempt(session, opportunity_id=opp.id, decision_id=dec.id, policy_evaluation_id=policy.id)

    detail_res = client.get(f"/api/v1/opportunities/{opp.id}")
    assert detail_res.status_code == 200
    data = detail_res.json()["data"]

    action_trace = data["action_traceability"]
    assert action_trace["execution_strategy"] == "DIRECT_REST"
    assert action_trace["used_fallback"] is False

    payment_link = data["attempts"][0]["payment_link"]
    assert payment_link is not None
    assert payment_link["execution_strategy"] == "DIRECT_REST"
    assert payment_link["used_fallback"] is False


def test_06_execution_strategy_mcp_visibility(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When an opportunity is executed via MCP, opportunity detail returns execution_strategy='MCP'."""
    client, session = _setup_env(tmp_path, mode="mcp_primary", mcp_enabled=True)
    opp, dec = _seed_opp(session, amount=130000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)

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
                                "id": "plink_ui_mcp_002",
                                "reference_id": f"recoveriq_{opp.id}_1",
                                "status": "created",
                                "short_url": "https://rzp.io/i/uimcp002",
                                "amount": 130000,
                                "currency": "INR",
                            }),
                        }
                    ],
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    execute_recovery_attempt(session, opportunity_id=opp.id, decision_id=dec.id, policy_evaluation_id=policy.id)

    detail_res = client.get(f"/api/v1/opportunities/{opp.id}")
    assert detail_res.status_code == 200
    data = detail_res.json()["data"]

    action_trace = data["action_traceability"]
    assert action_trace["execution_strategy"] == "MCP"
    assert action_trace["used_fallback"] is False

    payment_link = data["attempts"][0]["payment_link"]
    assert payment_link is not None
    assert payment_link["execution_strategy"] == "MCP"
    assert payment_link["used_fallback"] is False


def test_07_fallback_state_rest_to_mcp_visibility(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When REST rate limit forces fallback to MCP, opportunity detail reflects execution_strategy='MCP' and used_fallback=True."""
    client, session = _setup_env(tmp_path, mode="rest_primary", mcp_enabled=True)
    opp, dec = _seed_opp(session, amount=140000)
    policy = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        if "api.razorpay.com" in url:
            return httpx.Response(
                status_code=429,
                json={"error": {"code": "TOO_MANY_REQUESTS", "description": "Rate limit exceeded"}},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "req-fb-ui",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "id": "plink_ui_fb_mcp",
                                "reference_id": f"recoveriq_{opp.id}_1",
                                "status": "created",
                                "short_url": "https://rzp.io/i/uifbmcp",
                                "amount": 140000,
                                "currency": "INR",
                            }),
                        }
                    ],
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", mock_post)

    execute_recovery_attempt(session, opportunity_id=opp.id, decision_id=dec.id, policy_evaluation_id=policy.id)

    detail_res = client.get(f"/api/v1/opportunities/{opp.id}")
    assert detail_res.status_code == 200
    data = detail_res.json()["data"]

    action_trace = data["action_traceability"]
    assert action_trace["execution_strategy"] == "MCP"
    assert action_trace["used_fallback"] is True

    payment_link = data["attempts"][0]["payment_link"]
    assert payment_link is not None
    assert payment_link["execution_strategy"] == "MCP"
    assert payment_link["used_fallback"] is True


def test_08_data_source_clarity_separation(tmp_path: Path) -> None:
    """Verify data_source (SEEDED DEMO vs LIVE INGESTION) remains independent of payment_environment and mcp_status."""
    client, session = _setup_env(tmp_path, mode="rest_primary", mcp_enabled=True)
    res = client.get("/api/v1/dashboard/summary")
    assert res.status_code == 200
    op = res.json()["data"]["operating_status"]
    assert op["data_source"] in {"SEEDED DEMO", "LIVE INGESTION"}
    assert op["payment_environment"] == "RAZORPAY TEST"
    assert op["mcp_status"] == "AVAILABLE"
