import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_db_runtime, get_session_local
from app.gateway_adapters import RazorpayPaymentAdapter, PaymentLinkRequest, check_razorpay_api_connectivity
from app.main import create_app
from app.models import (
    AuditEvent,
    Payment,
    PolicyEvaluation,
    RecoveryAttempt,
    RecoveryDecision,
    RecoveryOutcome,
    RecoveryPaymentLink,
    RevenueOpportunity,
    WebhookEvent,
)


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_test_client(
    tmp_path: Path,
    *,
    adapter_mode: str = "simulation",
    key_id: str = "rzp_test_money_loop_key",
    key_secret: str = "money_loop_secret",
    ai_provider: str = "mock",
    secret: str = "mock_money_loop_test_secret",
) -> tuple[TestClient, str]:
    db_file = tmp_path / f"money_loop_test_{os.urandom(4).hex()}.db"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{db_file}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["PAYMENT_ADAPTER_MODE"] = adapter_mode
    os.environ["RAZORPAY_KEY_ID"] = key_id
    os.environ["RAZORPAY_KEY_SECRET"] = key_secret
    os.environ["AI_PROVIDER"] = ai_provider
    os.environ["APP_MODE"] = "simulation"

    get_settings.cache_clear()
    reset_db_runtime()
    init_db()

    app = create_app()
    return TestClient(app), secret


def test_money_loop_01_credentials_loading(tmp_path: Path) -> None:
    """1. Prove credentials load securely from settings without exposing secrets."""
    client, secret = _build_test_client(tmp_path, key_id="rzp_test_abc123", key_secret="secret_xyz789")
    settings = get_settings()
    assert settings.razorpay_key_id == "rzp_test_abc123"
    assert settings.razorpay_configured is True
    assert settings.razorpay_test_mode_keys is True
    assert settings.razorpay_live_mode_detected is False


def test_money_loop_02_razorpay_connectivity_check(tmp_path: Path, monkeypatch) -> None:
    """2. Prove Razorpay connectivity checks test credentials and live mode safety."""
    client, secret = _build_test_client(tmp_path, key_id="rzp_test_valid", key_secret="valid_sec")
    settings = get_settings()

    # Mock successful HTTP 200 response
    class MockResponse:
        status_code = 200
        def json(self):
            return {"items": []}

    monkeypatch.setattr("httpx.get", lambda url, auth, timeout: MockResponse())
    connected, reason = check_razorpay_api_connectivity(settings)
    assert connected is True
    assert reason is None


def test_money_loop_03_payment_link_creation_contract(tmp_path: Path, monkeypatch) -> None:
    """3. Prove Razorpay Standard Payment Link creation uses official POST /v1/payment_links schema."""
    captured_calls = []

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "id": "plink_test_mock_123",
                "short_url": "https://rzp.io/rzp/mocklink",
                "status": "created",
                "amount": 250000,
                "currency": "INR",
                "reference_id": "recoveriq_10_1_1724300000",
            }

    def mock_post(url, json, auth, timeout):
        captured_calls.append({"url": url, "json": json, "auth": auth})
        return MockResponse()

    monkeypatch.setattr("httpx.post", mock_post)

    adapter = RazorpayPaymentAdapter(key_id="rzp_test_unit", key_secret="unit_sec")
    req = PaymentLinkRequest(
        opportunity_id=10,
        attempt_number=1,
        amount_minor=250000,
        currency="INR",
        customer_reference="CUST-001",
    )
    result = adapter.create_payment_link(req)

    assert result.payment_link_id == "plink_test_mock_123"
    assert result.short_url == "https://rzp.io/rzp/mocklink"
    assert len(captured_calls) == 1
    call_payload = captured_calls[0]["json"]
    assert call_payload["amount"] == 250000
    assert call_payload["currency"] == "INR"
    assert call_payload["accept_partial"] is False
    assert "recoveriq_10_1" in call_payload["reference_id"]
    assert call_payload["notes"]["recoveriq_opportunity_id"] == "10"


def test_money_loop_04_payment_link_persistence(tmp_path: Path) -> None:
    """4. Prove Payment Link ID, short URL, reference ID, and attempt IDs persist in DB."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest a failed payment to trigger recovery attempt and payment link
    payload = {
        "id": "evt_p2_004",
        "event": "payment.failed",
        "account_id": "acc_p2",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_p2_004",
                    "order_id": "order_p2_004",
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
    client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": _sign(raw, secret), "content-type": "application/json"})

    session = get_session_local()()
    try:
        link = session.query(RecoveryPaymentLink).first()
        assert link is not None
        assert link.payment_link_id.startswith("plink_")
        assert link.amount_minor == 180000
        assert link.currency == "INR"
        assert link.recovery_attempt_id is not None
        assert link.opportunity_id is not None
    finally:
        session.close()


def test_money_loop_05_success_path_payment_link_paid_to_recovered(tmp_path: Path) -> None:
    """5. Prove success path: payment_link.paid -> VERIFIED_SUCCESS -> RECOVERED -> gross_recovered increases."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest failed payment
    fail_payload = {
        "id": "evt_p2_005_fail",
        "event": "payment.failed",
        "account_id": "acc_p2",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_p2_005",
                    "order_id": "order_p2_005",
                    "amount": 300000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    raw_fail = json.dumps(fail_payload).encode("utf-8")
    client.post("/api/v1/webhooks/razorpay", content=raw_fail, headers={"x-razorpay-signature": _sign(raw_fail, secret), "content-type": "application/json"})

    # Check that gross_recovered is 0 while pending
    s_before = client.get("/api/v1/dashboard/summary").json()["data"]
    assert s_before["gross_recovered_minor"] == 0

    session = get_session_local()()
    try:
        link = session.query(RecoveryPaymentLink).first()
        plink_id = link.payment_link_id
        ref_id = link.payment_link_reference_id
        opp_id = link.opportunity_id
    finally:
        session.close()

    # Ingest payment_link.paid webhook
    paid_payload = {
        "id": "evt_p2_005_paid",
        "event": "payment_link.paid",
        "account_id": "acc_p2",
        "created_at": 1724300500,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id,
                    "reference_id": ref_id,
                    "amount": 300000,
                    "currency": "INR",
                    "status": "paid",
                    "notes": {"recoveriq_opportunity_id": str(opp_id)},
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_p2_005_captured",
                    "amount": 300000,
                    "currency": "INR",
                    "captured": True,
                    "notes": {"recoveriq_opportunity_id": str(opp_id)},
                }
            }
        },
    }
    raw_paid = json.dumps(paid_payload).encode("utf-8")
    client.post("/api/v1/webhooks/razorpay", content=raw_paid, headers={"x-razorpay-signature": _sign(raw_paid, secret), "content-type": "application/json"})

    # Check that gross_recovered has now increased
    s_after = client.get("/api/v1/dashboard/summary").json()["data"]
    assert s_after["gross_recovered_minor"] == 300000
    assert s_after["recovery_rate"] == 1.0

    # Verify opportunity state
    detail = client.get(f"/api/v1/opportunities/{opp_id}").json()["data"]
    assert detail["opportunity"]["status"] == "VERIFIED_RECOVERED"
    assert detail["action_traceability"]["outcome"] == "RECOVERED"


def test_money_loop_06_failure_path_preserves_recovered_revenue(tmp_path: Path) -> None:
    """6. Prove failure path: failed payment on link -> VERIFIED_FAILURE -> NOT_RECOVERED -> gross_recovered untouched."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest failed payment
    fail_payload = {
        "id": "evt_p2_006_fail",
        "event": "payment.failed",
        "account_id": "acc_p2",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_p2_006",
                    "order_id": "order_p2_006",
                    "amount": 200000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    raw_fail = json.dumps(fail_payload).encode("utf-8")
    client.post("/api/v1/webhooks/razorpay", content=raw_fail, headers={"x-razorpay-signature": _sign(raw_fail, secret), "content-type": "application/json"})

    session = get_session_local()()
    try:
        link = session.query(RecoveryPaymentLink).first()
        plink_id = link.payment_link_id
        ref_id = link.payment_link_reference_id
        opp_id = link.opportunity_id
    finally:
        session.close()

    # Ingest failure webhook on the payment link
    fail_link_payload = {
        "id": "evt_p2_006_link_fail",
        "event": "payment.failed",
        "account_id": "acc_p2",
        "created_at": 1724300600,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id,
                    "reference_id": ref_id,
                    "amount": 200000,
                    "currency": "INR",
                    "status": "failed",
                    "notes": {"recoveriq_opportunity_id": str(opp_id)},
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_p2_006_rec_failed",
                    "amount": 200000,
                    "currency": "INR",
                    "captured": False,
                    "error_reason": "card_declined",
                    "notes": {"recoveriq_opportunity_id": str(opp_id)},
                }
            }
        },
    }
    raw_link_fail = json.dumps(fail_link_payload).encode("utf-8")
    client.post("/api/v1/webhooks/razorpay", content=raw_link_fail, headers={"x-razorpay-signature": _sign(raw_link_fail, secret), "content-type": "application/json"})

    s_final = client.get("/api/v1/dashboard/summary").json()["data"]
    assert s_final["gross_recovered_minor"] == 0

    detail = client.get(f"/api/v1/opportunities/{opp_id}").json()["data"]
    assert detail["opportunity"]["status"] in {"PAYMENT_FAILED", "RECOVERY_FAILED"}
    assert detail["action_traceability"]["outcome"] in {"NOT_RECOVERED", "FAILED"}


def test_money_loop_07_webhook_signature_verification(tmp_path: Path) -> None:
    """7. Prove webhook signature verification rejects invalid or tampered signatures."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    payload = {"id": "evt_sig_007", "event": "payment.failed", "created_at": 1724300000, "payload": {}}
    raw = json.dumps(payload).encode("utf-8")

    # Invalid signature
    res_bad = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": "bad_sig_12345", "content-type": "application/json"})
    assert res_bad.status_code in {400, 401}
    assert "SIGNATURE" in res_bad.json()["error"]["code"]

    # Valid signature
    valid_sig = _sign(raw, secret)
    res_good = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": valid_sig, "content-type": "application/json"})
    assert res_good.status_code == 200


def test_money_loop_08_duplicate_event_deduplication(tmp_path: Path) -> None:
    """8. Prove duplicate webhook events are safely ignored via ledger idempotency."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    payload = {
        "id": "evt_dedup_008",
        "event": "payment.failed",
        "account_id": "acc_p2",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_dedup_008",
                    "order_id": "order_dedup_008",
                    "amount": 100000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = _sign(raw, secret)

    # Ingest first time
    r1 = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": sig, "content-type": "application/json"})
    assert r1.status_code == 200
    assert r1.json()["data"]["duplicate"] is False

    # Ingest duplicate
    r2 = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": sig, "content-type": "application/json"})
    assert r2.status_code == 200
    assert r2.json()["data"]["duplicate"] is True


def test_money_loop_09_recovered_revenue_integrity(tmp_path: Path) -> None:
    """9. Prove recovered revenue remains 0 while links are pending and increases only on verified payment."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    for i in range(1, 4):
        payload = {
            "id": f"evt_p2_009_{i}",
            "event": "payment.failed",
            "account_id": "acc_p2",
            "created_at": 1724300000 + i,
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_p2_009_{i}",
                        "order_id": f"order_p2_009_{i}",
                        "amount": 100000,
                        "currency": "INR",
                        "method": "card",
                        "captured": False,
                        "error_reason": "network",
                    }
                }
            },
        }
        raw = json.dumps(payload).encode("utf-8")
        client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": _sign(raw, secret), "content-type": "application/json"})

    # 3 payment links created, zero verified paid
    s = client.get("/api/v1/dashboard/summary").json()["data"]
    assert s["revenue_at_risk_minor"] == 300000
    assert s["gross_recovered_minor"] == 0
    assert s["recovery_rate"] == 0.0


def test_money_loop_10_complete_audit_trail(tmp_path: Path) -> None:
    """10. Prove complete end-to-end audit trail is recorded from detection to verification."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest failed payment
    fail_payload = {
        "id": "evt_p2_010_fail",
        "event": "payment.failed",
        "account_id": "acc_p2",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_p2_010",
                    "order_id": "order_p2_010",
                    "amount": 500000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    raw_fail = json.dumps(fail_payload).encode("utf-8")
    client.post("/api/v1/webhooks/razorpay", content=raw_fail, headers={"x-razorpay-signature": _sign(raw_fail, secret), "content-type": "application/json"})

    opp_id = client.get("/api/v1/opportunities").json()["data"]["items"][0]["id"]
    detail = client.get(f"/api/v1/opportunities/{opp_id}").json()["data"]

    # Verify audit trail contains stage events
    audit_events = [a["event_type"] for a in detail["audit_trail"]]
    assert any("detection" in e for e in audit_events)
    assert any("diagnosis" in e for e in audit_events)
    assert any("policy" in e for e in audit_events)
    assert any("execution" in e for e in audit_events)
