import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_db_runtime
from app.main import create_app
from app.security import redact_sensitive_data


def _build_client(tmp_path: Path) -> TestClient:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase12.db'}"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app())


def test_phase12_failure_demo_endpoints_are_user_visible(tmp_path: Path) -> None:
    client = _build_client(tmp_path)

    scenarios_response = client.get("/api/v1/failure-demos")
    assert scenarios_response.status_code == 200
    scenarios_payload = scenarios_response.json()
    assert scenarios_payload["success"] is True
    assert len(scenarios_payload["data"]["scenarios"]) >= 8

    scenario_ids = {item["scenario_id"] for item in scenarios_payload["data"]["scenarios"]}
    assert {
        "invalid_webhook_signature",
        "invalid_evaluation_request",
        "opportunity_not_found",
        "ai_invalid_output",
        "ai_unavailable",
        "policy_blocked",
        "recovery_failure",
        "duplicate_webhook",
    }.issubset(scenario_ids)

    trigger_response = client.post(
        "/api/v1/failure-demos/trigger",
        json={"scenario_id": "invalid_webhook_signature"},
    )
    assert trigger_response.status_code == 401
    trigger_payload = trigger_response.json()
    assert trigger_payload["success"] is False
    assert trigger_payload["error"]["code"] == "INVALID_SIGNATURE"

    ai_invalid = client.post(
        "/api/v1/failure-demos/trigger",
        json={"scenario_id": "ai_invalid_output"},
    )
    assert ai_invalid.status_code == 422
    ai_invalid_payload = ai_invalid.json()
    assert ai_invalid_payload["error"]["code"] == "AI_SCHEMA_INVALID"
    assert "expected_behavior" in ai_invalid_payload["data"]
    assert "actual_behavior" in ai_invalid_payload["data"]


def test_phase12_validation_error_and_safe_envelope(tmp_path: Path) -> None:
    client = _build_client(tmp_path)

    response = client.get("/api/v1/opportunities?page=0")
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "query.page" in payload["error"]["fields"]


def test_phase12_redaction_guard_masks_sensitive_fields() -> None:
    payload = {
        "authorization": "Bearer test",
        "nested": {
            "phone": "9999999999",
            "safe": "ok",
        },
        "items": [{"signature": "abcd"}, {"other": "value"}],
    }

    redacted = redact_sensitive_data(payload)
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["phone"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "ok"
    assert redacted["items"][0]["signature"] == "[REDACTED]"
