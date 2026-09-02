import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.main import create_app
from app.models import AuditEvent, Payment, WebhookEvent, WebhookProcessorLedger
from app.webhooks import replay_webhook_event_from_ledger


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_client(tmp_path: Path) -> tuple[TestClient, str]:
    secret = "mock_webhook_idempotency_secret"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase2.db'}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    app = create_app()
    return TestClient(app), secret


def _post_webhook(
    client: TestClient,
    payload: dict,
    secret: str,
    *,
    tamper_signature: bool = False,
    header_event_id: str | None = None,
):
    raw = json.dumps(payload).encode("utf-8")
    signature = _sign(raw, secret)
    if tamper_signature:
        signature = "bad" + signature[3:]
    headers = {"x-razorpay-signature": signature, "content-type": "application/json"}
    if header_event_id is not None:
        headers["x-razorpay-event-id"] = header_event_id
    return client.post(
        "/api/v1/webhooks/razorpay",
        content=raw,
        headers=headers,
    )


def _audit_events_for(session, event_type: str, entity_id: str):
    return session.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == event_type)
        .where(AuditEvent.entity_id == entity_id)
    ).scalars().all()


def _payment_failed_payload(*, event_id: str, payment_id: str, created_at: int) -> dict:
    return {
        "id": event_id,
        "event": "payment.failed",
        "account_id": "acc_test_001",
        "created_at": created_at,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": "order_test_001",
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


def _payment_captured_payload(*, event_id: str, payment_id: str, created_at: int) -> dict:
    return {
        "id": event_id,
        "event": "payment.captured",
        "account_id": "acc_test_001",
        "created_at": created_at,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": "order_test_001",
                    "amount": 749900,
                    "currency": "INR",
                    "method": "card",
                    "captured": True,
                }
            }
        },
    }


def test_valid_webhook_is_accepted_and_persists_payment(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _payment_failed_payload(event_id="evt_001", payment_id="pay_001", created_at=1724300000)

    response = _post_webhook(client, payload, secret)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["processing_status"] == "processed"

    session = get_session_local()()
    try:
        payment = session.execute(select(Payment).where(Payment.razorpay_payment_id == "pay_001")).scalar_one()
        assert payment.status == "FAILED"
        event = session.execute(select(WebhookEvent).where(WebhookEvent.razorpay_event_id == "evt_001")).scalar_one()
        assert event.signature_valid is True
        ledger = session.execute(
            select(WebhookProcessorLedger).where(WebhookProcessorLedger.razorpay_event_id == "evt_001")
        ).scalar_one()
        assert ledger.delivery_count == 1
        assert ledger.last_processing_status == "processed"
        assert ledger.event_created_at == datetime.fromtimestamp(1724300000, tz=UTC).replace(tzinfo=None)
        audits = _audit_events_for(session, "webhook.processed", "evt_001")
        assert len(audits) == 1
    finally:
        session.close()


def test_invalid_signature_rejected_and_recorded(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _payment_failed_payload(event_id="evt_002", payment_id="pay_002", created_at=1724300001)

    response = _post_webhook(client, payload, secret, tamper_signature=True, header_event_id="evt_002")
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_SIGNATURE"

    session = get_session_local()()
    try:
        event = session.execute(select(WebhookEvent).where(WebhookEvent.razorpay_event_id == "evt_002")).scalar_one()
        assert event.signature_valid is False
        assert event.processed is False
        ledger = session.execute(
            select(WebhookProcessorLedger).where(WebhookProcessorLedger.razorpay_event_id == "evt_002")
        ).scalar_one()
        assert ledger.last_processing_status == "invalid_signature"
        audits = _audit_events_for(session, "webhook.invalid_signature", "evt_002")
        assert len(audits) == 1
    finally:
        session.close()


def test_invalid_signature_returns_before_json_parsing(tmp_path: Path, monkeypatch) -> None:
    client, _ = _build_client(tmp_path)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("json.loads should not be called for invalid signatures")

    monkeypatch.setattr("app.webhooks.json.loads", _fail_if_called)

    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=b"{not-valid-json",
        headers={
            "x-razorpay-signature": "invalid-signature",
            "x-razorpay-event-id": "evt_invalid_sig_early_return",
            "content-type": "application/json",
        },
    )

    assert response.status_code == 401
    assert b"INVALID_SIGNATURE" in response.content


def test_duplicate_event_is_idempotent(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _payment_failed_payload(event_id="evt_003", payment_id="pay_003", created_at=1724300002)

    first = _post_webhook(client, payload, secret)
    second = _post_webhook(client, payload, secret)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["duplicate"] is True

    session = get_session_local()()
    try:
        count = session.execute(select(WebhookEvent).where(WebhookEvent.razorpay_event_id == "evt_003")).scalars().all()
        assert len(count) == 1
        ledger = session.execute(
            select(WebhookProcessorLedger).where(WebhookProcessorLedger.razorpay_event_id == "evt_003")
        ).scalar_one()
        assert ledger.delivery_count == 2
        assert ledger.last_processing_status == "duplicate"
        audits = _audit_events_for(session, "webhook.duplicate", "evt_003")
        assert len(audits) == 1
    finally:
        session.close()


def test_out_of_order_event_does_not_corrupt_newer_state(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)

    captured = _payment_captured_payload(event_id="evt_004", payment_id="pay_004", created_at=1724300100)
    failed_older = _payment_failed_payload(event_id="evt_005", payment_id="pay_004", created_at=1724300000)

    first = _post_webhook(client, captured, secret)
    second = _post_webhook(client, failed_older, secret)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["processing_status"] == "stale_ignored"

    session = get_session_local()()
    try:
        payment = session.execute(select(Payment).where(Payment.razorpay_payment_id == "pay_004")).scalar_one()
        assert payment.status == "CAPTURED"
        audits = _audit_events_for(session, "webhook.stale_ignored", "evt_005")
        assert len(audits) == 1
    finally:
        session.close()


def test_conflicting_transition_is_rejected(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)

    captured = _payment_captured_payload(event_id="evt_006", payment_id="pay_006", created_at=1724300200)
    failed_newer = _payment_failed_payload(event_id="evt_007", payment_id="pay_006", created_at=1724300300)

    _post_webhook(client, captured, secret)
    response = _post_webhook(client, failed_newer, secret)

    assert response.status_code == 200
    assert response.json()["data"]["processing_status"] == "conflicting_transition"

    session = get_session_local()()
    try:
        payment = session.execute(select(Payment).where(Payment.razorpay_payment_id == "pay_006")).scalar_one()
        assert payment.status == "CAPTURED"
        audits = _audit_events_for(session, "webhook.conflicting_transition", "evt_007")
        assert len(audits) == 1
    finally:
        session.close()


def test_invalid_json_is_rejected_and_audited(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    raw = b"not-json"
    signature = _sign(raw, secret)

    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw,
        headers={"x-razorpay-signature": signature, "content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"

    session = get_session_local()()
    try:
        audits = session.execute(select(AuditEvent).where(AuditEvent.event_type == "webhook.invalid_json")).scalars().all()
        assert len(audits) == 1
    finally:
        session.close()


def test_missing_event_id_is_rejected_and_audited(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _payment_failed_payload(event_id="evt_unused", payment_id="pay_007", created_at=1724300400)
    payload.pop("id")

    response = _post_webhook(client, payload, secret)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_EVENT_ID"

    session = get_session_local()()
    try:
        audits = session.execute(select(AuditEvent).where(AuditEvent.event_type == "webhook.missing_event_id")).scalars().all()
        assert len(audits) == 1
    finally:
        session.close()


def test_missing_payload_event_id_can_fallback_to_header_event_id(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _payment_failed_payload(event_id="evt_header_fallback", payment_id="pay_011", created_at=1724300420)
    payload.pop("id")

    response = _post_webhook(client, payload, secret, header_event_id="evt_header_fallback")

    assert response.status_code == 200
    assert response.json()["data"]["event_id"] == "evt_header_fallback"


def test_header_and_payload_event_id_mismatch_is_rejected(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _payment_failed_payload(event_id="evt_payload_012", payment_id="pay_012", created_at=1724300430)

    response = _post_webhook(client, payload, secret, header_event_id="evt_header_012")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EVENT_ID_MISMATCH"


def test_unsupported_event_is_ignored_and_audited(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = {
        "id": "evt_008",
        "event": "order.paid",
        "account_id": "acc_test_001",
        "created_at": 1724300500,
        "payload": {},
    }

    response = _post_webhook(client, payload, secret)

    assert response.status_code == 200
    assert response.json()["data"]["processing_status"] == "ignored_event"

    session = get_session_local()()
    try:
        event = session.execute(select(WebhookEvent).where(WebhookEvent.razorpay_event_id == "evt_008")).scalar_one()
        assert event.processing_status == "ignored_event"
        audits = _audit_events_for(session, "webhook.ignored_event", "evt_008")
        assert len(audits) == 1
    finally:
        session.close()


def test_replay_dry_run_reprocesses_without_state_mutation(tmp_path: Path) -> None:
    client, secret = _build_client(tmp_path)
    payload = _payment_failed_payload(event_id="evt_replay_001", payment_id="pay_replay_001", created_at=1724300600)
    response = _post_webhook(client, payload, secret)
    assert response.status_code == 200

    session = get_session_local()()
    try:
        payment_before = session.execute(
            select(Payment).where(Payment.razorpay_payment_id == "pay_replay_001")
        ).scalar_one()
        result = replay_webhook_event_from_ledger(session, event_id="evt_replay_001", dry_run=True)
        payment_after = session.execute(
            select(Payment).where(Payment.razorpay_payment_id == "pay_replay_001")
        ).scalar_one()

        assert result["success"] is True
        assert result["data"]["replay_mode"] == "dry_run"
        assert result["data"]["processing_status"] == "processed"
        assert payment_before.last_seen_at == payment_after.last_seen_at

        ledger = session.execute(
            select(WebhookProcessorLedger).where(WebhookProcessorLedger.razorpay_event_id == "evt_replay_001")
        ).scalar_one()
        assert ledger.last_processing_status == "replay_processed"
        audits = _audit_events_for(session, "webhook.replay.completed", "evt_replay_001")
        assert len(audits) == 1
    finally:
        session.close()


def test_replay_missing_ledger_event_returns_not_found(tmp_path: Path) -> None:
    _build_client(tmp_path)
    session = get_session_local()()
    try:
        result = replay_webhook_event_from_ledger(session, event_id="evt_missing", dry_run=True)
        assert result["success"] is False
        assert result["error"]["code"] == "LEDGER_EVENT_NOT_FOUND"
        audits = _audit_events_for(session, "webhook.replay.not_found", "evt_missing")
        assert len(audits) == 1
    finally:
        session.close()



