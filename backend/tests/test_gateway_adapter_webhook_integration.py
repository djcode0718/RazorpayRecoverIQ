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
from app.models import AuditEvent, Payment


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = os.environ.get("TEST_RAZORPAY_WEBHOOK_SECRET", "mock_webhook_secret_key_02")
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase8.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["PAYMENT_ADAPTER_MODE"] = "razorpay_test"
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


def _failed_payload(event_id: str) -> dict:
    return {
        "id": event_id,
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": 1724301600,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_phase8_001",
                    "order_id": "order_phase8_001",
                    "amount": 199000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }


def test_adapter_integration_accepts_matching_test_mode_retrieval(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _failed_payload("evt_phase8_001")
    payload["recoveriq_test_mode"] = {
        "retrieved_payment": {
            "id": "pay_phase8_001",
            "order_id": "order_phase8_001",
            "amount": 199000,
            "currency": "INR",
        }
    }

    response = _post_webhook(client, payload, secret)
    assert response.status_code == 200
    assert response.json()["data"]["processing_status"] == "processed"

    session = get_session_local()()
    try:
        payment = session.execute(
            select(Payment).where(Payment.razorpay_payment_id == "pay_phase8_001")
        ).scalar_one()
        assert payment.status == "FAILED"
    finally:
        session.close()


def test_adapter_integration_rejects_retrieval_mismatch(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _failed_payload("evt_phase8_002")
    payload["recoveriq_test_mode"] = {
        "retrieved_payment": {
            "id": "pay_phase8_001",
            "order_id": "order_phase8_001",
            "amount": 200000,
            "currency": "INR",
        }
    }

    response = _post_webhook(client, payload, secret)
    assert response.status_code == 200
    assert response.json()["data"]["processing_status"] == "adapter_rejected"

    session = get_session_local()()
    try:
        payment = session.execute(
            select(Payment).where(Payment.razorpay_payment_id == "pay_phase8_001")
        ).scalar_one_or_none()
        assert payment is None
        audits = session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == "webhook.adapter_rejected")
            .where(AuditEvent.entity_id == "evt_phase8_002")
        ).scalars().all()
        assert len(audits) == 1
        assert audits[0].reason == "retrieval_mismatch_amount"
    finally:
        session.close()


def test_adapter_integration_rejects_when_retrieval_missing(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _failed_payload("evt_phase8_003")

    response = _post_webhook(client, payload, secret)
    assert response.status_code == 200
    assert response.json()["data"]["processing_status"] == "processed"

    session = get_session_local()()
    try:
        payment = session.execute(
            select(Payment).where(Payment.razorpay_payment_id == "pay_phase8_001")
        ).scalar_one()
        assert payment.status == "FAILED"
    finally:
        session.close()

