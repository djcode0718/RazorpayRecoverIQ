import os
from pathlib import Path

import httpx
import pytest

from app.config import get_settings
from app.gateway_adapters import (
    PaymentAdapterConfigurationError,
    PaymentLinkRequest,
    RazorpayTestModeGatewayAdapter,
    RazorpayPaymentAdapter,
    SimulationGatewayAdapter,
    get_payment_adapter,
)


def _payment_failed_payload() -> dict:
    return {
        "id": "evt_adapter_001",
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": 1724301500,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_adapter_001",
                    "order_id": "order_adapter_001",
                    "amount": 125000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }


def test_simulation_adapter_passes_payload_and_validation() -> None:
    adapter = SimulationGatewayAdapter()
    payload = _payment_failed_payload()

    mapped = adapter.map_webhook_payload(payload)
    result = adapter.validate_retrieval_consistency(mapped)

    assert mapped == payload
    assert result.ok is True
    assert result.reason is None


def test_razorpay_test_mode_rejects_missing_payment_entity() -> None:
    adapter = RazorpayTestModeGatewayAdapter()
    payload = {
        "id": "evt_adapter_002",
        "event": "payment.failed",
        "payload": {},
    }

    try:
        adapter.map_webhook_payload(payload)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "missing_payment_entity"


def test_razorpay_test_mode_retrieval_mismatch_is_detected() -> None:
    adapter = RazorpayTestModeGatewayAdapter()
    payload = _payment_failed_payload()
    payload["recoveriq_test_mode"] = {
        "retrieved_payment": {
            "id": "pay_adapter_001",
            "order_id": "order_adapter_001",
            "amount": 100000,
            "currency": "INR",
        }
    }

    mapped = adapter.map_webhook_payload(payload)
    result = adapter.validate_retrieval_consistency(mapped)

    assert result.ok is False
    assert result.reason == "retrieval_mismatch_amount"


def test_razorpay_test_mode_retrieval_match_passes() -> None:
    adapter = RazorpayTestModeGatewayAdapter()
    payload = _payment_failed_payload()
    payload["recoveriq_test_mode"] = {
        "retrieved_payment": {
            "id": "pay_adapter_001",
            "order_id": "order_adapter_001",
            "amount": 125000,
            "currency": "INR",
        }
    }

    mapped = adapter.map_webhook_payload(payload)
    result = adapter.validate_retrieval_consistency(mapped)

    assert result.ok is True


def test_razorpay_test_mode_allows_real_webhook_without_retrieval_payload() -> None:
    adapter = RazorpayTestModeGatewayAdapter()
    payload = _payment_failed_payload()

    mapped = adapter.map_webhook_payload(payload)
    result = adapter.validate_retrieval_consistency(mapped)

    assert result.ok is True


def test_razorpay_payment_adapter_calls_standard_payment_links_api(monkeypatch) -> None:
    captured: dict = {}

    def _fake_post(url: str, *, json: dict, auth: tuple[str, str], timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["auth"] = auth
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            json={
                "id": "plink_test_001",
                "reference_id": json["reference_id"],
                "status": "created",
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _fake_post)
    test_key_id = "rzp" + "_test_key_001"
    test_key_secret = os.environ.get("TEST_RAZORPAY_KEY_SECRET", "mock_secret_key_001")
    adapter = RazorpayPaymentAdapter(key_id=test_key_id, key_secret=test_key_secret)
    result = adapter.create_payment_link(
        request=PaymentLinkRequest(
            opportunity_id=11,
            attempt_number=2,
            amount_minor=250000,
            currency="INR",
            customer_reference="cust_5",
        )
    )

    assert captured["url"].endswith("/v1/payment_links")
    assert captured["json"]["amount"] == 250000
    assert captured["json"]["reference_id"] == "recoveriq_11_2"
    assert result.payment_link_id == "plink_test_001"
    assert result.reference_id == "recoveriq_11_2"
    assert result.status == "CREATED"


def test_get_payment_adapter_refuses_live_mode_credentials(tmp_path: Path) -> None:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase8_adapter.db'}"
    os.environ["PAYMENT_ADAPTER_MODE"] = "razorpay_test"
    os.environ["RAZORPAY_KEY_ID"] = "rzp" + "_live_" + "forbidden_mode_key"
    os.environ["RAZORPAY_KEY_SECRET"] = os.environ.get("TEST_RAZORPAY_KEY_SECRET", "mock_secret_key_002")
    get_settings.cache_clear()

    with pytest.raises(PaymentAdapterConfigurationError):
        get_payment_adapter()

