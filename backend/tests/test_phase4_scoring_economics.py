import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.economics import compute_economics
from app.main import create_app
from app.models import RevenueOpportunity


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = "whsec_test_secret"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase4.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
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


def test_economic_engine_minor_unit_math_is_deterministic() -> None:
    first = compute_economics(749_900, 65, "RECOVERY_PROMPT")
    second = compute_economics(749_900, 65, "RECOVERY_PROMPT")
    assert first == second
    assert first.expected_recovery_minor == (749_900 * 65) // 100
    assert first.expected_net_recovery_minor == first.expected_recovery_minor - 500


def test_scoring_engine_is_deterministic_for_same_payment(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    failed_event_one = {
        "id": "evt_phase4_001",
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": 1724300700,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_phase4_001",
                    "order_id": "order_phase4_001",
                    "amount": 749900,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Card declined",
                    "error_source": "gateway",
                    "error_step": "payment_authentication",
                    "error_reason": "issuer_declined",
                }
            }
        },
    }

    failed_event_two = {
        "id": "evt_phase4_001_b",
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": 1724300701,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_phase4_001_b",
                    "order_id": "order_phase4_001_b",
                    "amount": 749900,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Card declined",
                    "error_source": "gateway",
                    "error_step": "payment_authentication",
                    "error_reason": "issuer_declined",
                }
            }
        },
    }

    response_one = _post_webhook(client, failed_event_one, secret)
    response_two = _post_webhook(client, failed_event_two, secret)
    assert response_one.status_code == 200
    assert response_two.status_code == 200

    session = get_session_local()()
    try:
        opportunities = session.execute(
            select(RevenueOpportunity).where(RevenueOpportunity.failure_reason == "issuer_declined")
        ).scalars().all()
        assert len(opportunities) == 2
        first, second = opportunities[0], opportunities[1]

        assert first.recovery_probability == second.recovery_probability
        assert first.recovery_score == second.recovery_score
        assert first.recommended_action == second.recommended_action
        assert first.confidence == second.confidence
        assert first.expected_recovery_minor == (first.amount_at_risk_minor * first.recovery_probability) // 100
        assert second.expected_recovery_minor == (second.amount_at_risk_minor * second.recovery_probability) // 100
    finally:
        session.close()


def test_failed_webhook_creates_single_revenue_opportunity(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)

    payload = {
        "id": "evt_phase4_002",
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": 1724300800,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_phase4_002",
                    "order_id": "order_phase4_002",
                    "amount": 200000,
                    "currency": "INR",
                    "method": "upi",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }

    first = _post_webhook(client, payload, secret)
    second = _post_webhook(client, payload, secret)
    assert first.status_code == 200
    assert second.status_code == 200

    session = get_session_local()()
    try:
        opportunities = session.execute(
            select(RevenueOpportunity).where(RevenueOpportunity.failure_reason == "network")
        ).scalars().all()
        assert len(opportunities) == 1
        opportunity = opportunities[0]
        assert opportunity.amount_at_risk_minor == 200000
        assert opportunity.expected_recovery_minor == (200000 * opportunity.recovery_probability) // 100
    finally:
        session.close()



