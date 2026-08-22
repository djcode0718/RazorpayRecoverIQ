import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_db_runtime
from app.main import create_app


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = "whsec_phase14"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase14.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["PAYMENT_ADAPTER_MODE"] = "razorpay_test"
    os.environ["RAZORPAY_KEY_ID"] = "rzp_test_demo_key"
    os.environ["RAZORPAY_KEY_SECRET"] = "demo_secret"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app()), secret


def test_razorpay_integration_status_reports_flags_without_exposing_secrets(tmp_path: Path, monkeypatch) -> None:
    client, _ = _build_client(tmp_path)
    monkeypatch.setattr("app.api.routes.check_razorpay_api_connectivity", lambda settings: (True, None))

    response = client.get("/api/v1/integrations/razorpay/status")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["test_mode"] is True
    assert data["credentials_configured"] is True
    assert data["api_connectivity"] is True
    assert data["webhook_configured"] is True
    assert "razorpay_key_secret" not in json.dumps(data)
    assert "demo_secret" not in json.dumps(data)


def test_razorpay_integration_status_includes_last_webhook_event(tmp_path: Path, monkeypatch) -> None:
    client, secret = _build_client(tmp_path)
    monkeypatch.setattr("app.api.routes.check_razorpay_api_connectivity", lambda settings: (False, "timeout"))

    payload = {
        "id": "evt_phase14_001",
        "event": "payment.failed",
        "account_id": "acc_phase14",
        "created_at": 1724303000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_phase14_001",
                    "order_id": "order_phase14_001",
                    "amount": 180000,
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
    webhook_response = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )
    assert webhook_response.status_code == 200

    response = client.get("/api/v1/integrations/razorpay/status")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["api_connectivity"] is False
    assert data["api_connectivity_reason"] == "timeout"
    assert data["last_event"] == "payment.failed"
    assert data["last_event_id"] == "evt_phase14_001"
    assert data["last_event_status"] == "processed"


def test_razorpay_status_marks_test_mode_when_test_keys_exist_in_simulation_mode(tmp_path: Path, monkeypatch) -> None:
    client, _ = _build_client(tmp_path)
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    get_settings.cache_clear()
    monkeypatch.setattr("app.api.routes.check_razorpay_api_connectivity", lambda settings: (True, None))

    response = client.get("/api/v1/integrations/razorpay/status")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["test_mode"] is True
    assert data["api_connectivity"] is False
    assert data["api_connectivity_reason"] == "adapter_mode_not_razorpay_test"
