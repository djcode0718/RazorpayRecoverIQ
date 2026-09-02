import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_db_runtime, get_session_local
from app.demo_seed import seed_core_recovery_demo
from app.main import create_app
from app.models import (
    Customer,
    Merchant,
    Order,
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
    key_id: str = "rzp_test_fixture_key",
    key_secret: str = "fixture_secret",
    ai_provider: str = "mock",
    secret: str = "whsec_fixture_acceptance",
) -> tuple[TestClient, str]:
    db_file = tmp_path / f"test_{os.urandom(4).hex()}.db"
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


def test_acceptance_1_simulation_data_with_razorpay_test_payment_adapter(tmp_path: Path, monkeypatch) -> None:
    """1. Simulation data + Razorpay Test payment adapter mode decoupling."""
    client, secret = _build_test_client(tmp_path, adapter_mode="razorpay_test")
    monkeypatch.setattr("app.api.routes.check_razorpay_api_connectivity", lambda settings: (True, None))

    # Seed simulation demo data
    seed_res = client.post("/api/v1/demo/seed-core-recovery")
    assert seed_res.status_code == 200

    # Query status
    status_res = client.get("/api/v1/integrations/razorpay/status")
    assert status_res.status_code == 200
    status_data = status_res.json()["data"]

    op_status = status_data["operating_status"]
    # Data source is SEEDED DEMO
    assert op_status["data_source"] == "SEEDED DEMO"
    # Payment environment is RAZORPAY TEST
    assert op_status["payment_environment"] == "RAZORPAY TEST"
    # AI provider is deterministic mock
    assert op_status["ai_provider"] == "MOCK/FALLBACK"
    # Webhook is verified because demo webhooks passed signature verification
    assert op_status["webhook"] == "VERIFIED"
    assert op_status["policy_engine"] == "ACTIVE"


def test_acceptance_2_seeded_opportunity_and_synthetic_entity_quality(tmp_path: Path) -> None:
    """2. Seeded opportunity contains realistic synthetic entities without UNKNOWN labels."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")
    seed_res = client.post("/api/v1/demo/seed-core-recovery")
    assert seed_res.status_code == 200

    opps_res = client.get("/api/v1/opportunities")
    assert opps_res.status_code == 200
    opps_data = opps_res.json()["data"]

    assert opps_data["count"] > 0
    for item in opps_data["items"]:
        # Verify no UNKNOWN customer reference is presented
        assert "UNKNOWN" not in item["customer_reference"]
        assert item["customer_reference"].startswith("[TEST]") or item["customer_reference"].startswith("CUST-")
        assert item["amount_at_risk_minor"] > 0
        assert item["outcome"] in {"PENDING", "RECOVERED", "NOT_RECOVERED", "BLOCKED", "ESCALATED", "FAILED", "VERIFICATION_FAILED"}


def test_acceptance_3_payment_link_created_not_treated_as_recovered(tmp_path: Path) -> None:
    """3. Payment link created but not paid: remains PENDING and does not increase recovered revenue."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest a failed payment that policy allows
    payload = {
        "id": "evt_accept_003",
        "event": "payment.failed",
        "account_id": "acc_demo_seed",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_accept_003",
                    "order_id": "order_accept_003",
                    "amount": 150000,
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
    resp = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": sig, "content-type": "application/json"})
    assert resp.status_code == 200

    summary_res = client.get("/api/v1/dashboard/summary")
    summary = summary_res.json()["data"]

    # Payment link is created, but not paid
    assert summary["gross_recovered_minor"] == 0
    assert summary["recovery_rate"] == 0.0

    opps = client.get("/api/v1/opportunities").json()["data"]["items"]
    matched = [item for item in opps if item["amount_at_risk_minor"] == 150000][0]
    assert matched["status"] == "PAYMENT_LINK_CREATED"
    assert matched["outcome"] == "PENDING"


def test_acceptance_4_failed_recovery_outcome(tmp_path: Path) -> None:
    """4. Failed recovery: verified failed outcome does not add recovered revenue."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Seed core recovery demo which includes failed recovery for pay_demo_005
    client.post("/api/v1/demo/seed-core-recovery")

    # Look up the opportunity for pay_demo_005
    session = get_session_local()()
    try:
        pay = session.query(Payment).filter(Payment.razorpay_payment_id == "pay_demo_005").first()
        opp = session.query(RevenueOpportunity).filter(RevenueOpportunity.payment_id == pay.id).first()
        opp_id = opp.id
    finally:
        session.close()

    detail = client.get(f"/api/v1/opportunities/{opp_id}").json()["data"]
    assert detail["opportunity"]["status"] in {"PAYMENT_FAILED", "RECOVERY_FAILED"}
    assert detail["action_traceability"]["outcome"] in {"NOT_RECOVERED", "FAILED"}
    assert detail["economics"]["gross_recovered_minor"] == 0


def test_acceptance_5_successful_verified_recovery(tmp_path: Path) -> None:
    """5. Successful verified recovery: increases gross_recovered_minor truthfully from persisted data."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest failed payment
    fail_payload = {
        "id": "evt_accept_005_fail",
        "event": "payment.failed",
        "account_id": "acc_demo_seed",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_accept_005",
                    "order_id": "order_accept_005",
                    "amount": 250000,
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

    # Prior to capture, recovered is 0
    summary_before = client.get("/api/v1/dashboard/summary").json()["data"]
    assert summary_before["gross_recovered_minor"] == 0

    # Ingest captured webhook
    cap_payload = {
        "id": "evt_accept_005_cap",
        "event": "payment.captured",
        "account_id": "acc_demo_seed",
        "created_at": 1724303600,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_accept_005",
                    "order_id": "order_accept_005",
                    "amount": 250000,
                    "currency": "INR",
                    "method": "card",
                    "captured": True,
                }
            }
        },
    }
    raw_cap = json.dumps(cap_payload).encode("utf-8")
    client.post("/api/v1/webhooks/razorpay", content=raw_cap, headers={"x-razorpay-signature": _sign(raw_cap, secret), "content-type": "application/json"})

    # After capture, verified recovered amount reflects exact amount
    summary_after = client.get("/api/v1/dashboard/summary").json()["data"]
    assert summary_after["gross_recovered_minor"] == 250000
    assert summary_after["recovery_rate"] == 1.0


def test_acceptance_6_blocked_policy(tmp_path: Path) -> None:
    """6. Blocked policy: high amount opportunity is blocked and output as BLOCKED outcome."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest payment exceeding 900,000 minor policy limit (e.g. ₹15,000 = 1,500,000 minor)
    payload = {
        "id": "evt_accept_006",
        "event": "payment.failed",
        "account_id": "acc_demo_seed",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_accept_006",
                    "order_id": "order_accept_006",
                    "amount": 1500000,
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

    opps = client.get("/api/v1/opportunities").json()["data"]["items"]
    matched = [item for item in opps if item["amount_at_risk_minor"] == 1500000][0]
    assert matched["status"] == "POLICY_BLOCKED"
    assert matched["policy_result"] == "BLOCK"
    assert matched["outcome"] == "BLOCKED"


def test_acceptance_7_escalated_opportunity(tmp_path: Path) -> None:
    """7. Escalated opportunity: policy/AI escalation sets status to ESCALATED with ESCALATED outcome."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Unknown reason with netbanking defaults to ESCALATE in scoring
    payload = {
        "id": "evt_accept_007",
        "event": "payment.failed",
        "account_id": "acc_demo_seed",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_accept_007",
                    "order_id": "order_accept_007",
                    "amount": 890000,
                    "currency": "INR",
                    "method": "unknown_method",
                    "captured": False,
                    "error_reason": "unknown_failure",
                }
            }
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": _sign(raw, secret), "content-type": "application/json"})

    opps = client.get("/api/v1/opportunities").json()["data"]["items"]
    matched = [item for item in opps if item["amount_at_risk_minor"] == 890000][0]
    assert matched["status"] == "ESCALATED" or matched["policy_result"] == "ESCALATE"
    assert matched["outcome"] == "ESCALATED"


def test_acceptance_8_duplicate_recovery_attempt_guard(tmp_path: Path) -> None:
    """8. Duplicate recovery attempt: idempotency ledger and open attempt guard prevent double execution."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    payload = {
        "id": "evt_accept_008",
        "event": "payment.failed",
        "account_id": "acc_demo_seed",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_accept_008",
                    "order_id": "order_accept_008",
                    "amount": 200000,
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

    # First post
    r1 = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": sig, "content-type": "application/json"})
    assert r1.status_code == 200
    assert r1.json()["data"]["duplicate"] is False

    # Second post (duplicate replay)
    r2 = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": sig, "content-type": "application/json"})
    assert r2.status_code == 200
    assert r2.json()["data"]["duplicate"] is True

    # Check total attempts recorded
    session = get_session_local()()
    try:
        attempts = session.query(RecoveryAttempt).all()
        assert len(attempts) == 1
    finally:
        session.close()


def test_acceptance_9_no_false_increase_in_recovered_revenue(tmp_path: Path) -> None:
    """9. Financial correctness: pending and failed recovery attempts never increase recovered revenue."""
    client, secret = _build_test_client(tmp_path, adapter_mode="simulation")

    # Ingest multiple failed payments
    for i in range(1, 4):
        payload = {
            "id": f"evt_accept_009_{i}",
            "event": "payment.failed",
            "account_id": "acc_demo_seed",
            "created_at": 1724300000 + (i * 100),
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_accept_009_{i}",
                        "order_id": f"order_accept_009_{i}",
                        "amount": 100000 * i,
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

    summary = client.get("/api/v1/dashboard/summary").json()["data"]
    # 3 opportunities created with payment links, none captured
    assert summary["active_opportunities"] == 3
    assert summary["revenue_at_risk_minor"] == 600000
    assert summary["gross_recovered_minor"] == 0
    assert summary["recovery_rate"] == 0.0


def test_acceptance_10_truthful_operating_mode_reporting(tmp_path: Path, monkeypatch) -> None:
    """10. Truthful operating-mode reporting across all 5 dimensions."""
    # Case A: Simulation mode without Razorpay credentials
    client_sim, _ = _build_test_client(tmp_path, adapter_mode="simulation", key_id="", key_secret="")
    health_sim = client_sim.get("/api/v1/health").json()["data"]["operating_status"]
    assert health_sim["payment_environment"] == "SIMULATION"
    assert health_sim["ai_provider"] == "MOCK/FALLBACK"
    assert health_sim["policy_engine"] == "ACTIVE"
    assert health_sim["webhook"] in {"WAITING", "CONFIGURED"}

    # Case B: Razorpay Test mode with valid test credentials and active connection
    client_test, secret = _build_test_client(tmp_path, adapter_mode="razorpay_test", key_id="rzp_test_valid_123", key_secret="valid_secret")
    monkeypatch.setattr("app.api.routes.check_razorpay_api_connectivity", lambda settings: (True, None))

    # Send a webhook to verify webhook state
    payload = {
        "id": "evt_accept_010",
        "event": "payment.failed",
        "account_id": "acc_live_merchant_123",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_accept_010",
                    "order_id": "order_accept_010",
                    "amount": 200000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    client_test.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": _sign(raw, secret), "content-type": "application/json"})

    status_data = client_test.get("/api/v1/integrations/razorpay/status").json()["data"]["operating_status"]
    assert status_data["data_source"] == "LIVE INGESTION"
    assert status_data["payment_environment"] == "RAZORPAY TEST"
    assert status_data["webhook"] == "VERIFIED"
    assert status_data["api_connectivity"] is True
