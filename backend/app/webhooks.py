import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .gateway_adapters import get_gateway_adapter
from .models import AuditEvent, Payment, WebhookEvent, WebhookProcessorLedger
from .simulation_workflow import run_detection_to_verification_flow
from .state_machine import can_transition_payment


EVENT_TO_PAYMENT_STATUS = {
    "payment.created": "CREATED",
    "payment.authorized": "PENDING",
    "payment.failed": "FAILED",
    "payment.captured": "CAPTURED",
}


def verify_razorpay_signature(raw_body: bytes, signature: str, webhook_secret: str) -> bool:
    if not webhook_secret or not signature:
        return False
    computed = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


def parse_event_time(payload: dict[str, Any]) -> datetime:
    created_at = payload.get("created_at")
    if isinstance(created_at, int):
        return datetime.fromtimestamp(created_at, tz=UTC).replace(tzinfo=None)
    return datetime.now(UTC).replace(tzinfo=None)


def _payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def _extract_payment_entity(payload: dict[str, Any]) -> dict[str, Any] | None:
    payment = payload.get("payload", {}).get("payment", {}).get("entity")
    if isinstance(payment, dict):
        return payment
    return None


def _extract_event_created_at(payload: dict[str, Any]) -> datetime | None:
    created_at = payload.get("created_at")
    if isinstance(created_at, int):
        return datetime.fromtimestamp(created_at, tz=UTC).replace(tzinfo=None)
    return None


def _write_audit_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str = "WebhookEvent",
    entity_id: str,
    correlation_id: str,
    reason: str | None,
    result: str | None = None,
    metadata: dict[str, Any] | None = None,
    input_snapshot: dict[str, Any] | None = None,
    outcome_snapshot: dict[str, Any] | None = None,
) -> None:
    audit = AuditEvent(
        event_type=event_type,
        actor_type="SYSTEM",
        actor_id="webhook_gateway",
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        result=result,
        metadata_json=metadata,
        input_snapshot=input_snapshot,
        outcome_snapshot=outcome_snapshot,
        reason=reason,
    )
    db.add(audit)
    db.commit()


def _write_audit_event_once(
    db: Session,
    *,
    event_type: str,
    entity_id: str,
    correlation_id: str,
    reason: str | None,
    input_snapshot: dict[str, Any] | None = None,
    outcome_snapshot: dict[str, Any] | None = None,
) -> None:
    existing = db.execute(
        select(AuditEvent).where(AuditEvent.event_type == event_type, AuditEvent.entity_id == entity_id)
    ).scalar_one_or_none()
    if existing is not None:
        return
    _write_audit_event(
        db,
        event_type=event_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        reason=reason,
        input_snapshot=input_snapshot,
        outcome_snapshot=outcome_snapshot,
    )


def _record_processor_ledger(
    db: Session,
    *,
    event_id: str,
    event_type: str,
    event_created_at: datetime | None,
    correlation_id: str,
    processing_status: str,
    processing_error: str | None,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ledger = db.execute(
        select(WebhookProcessorLedger).where(WebhookProcessorLedger.razorpay_event_id == event_id)
    ).scalar_one_or_none()

    if ledger is None:
        ledger = WebhookProcessorLedger(
            razorpay_event_id=event_id,
            event_type=event_type,
            event_created_at=event_created_at,
            first_received_at=now,
            last_received_at=now,
            delivery_count=1,
            last_processing_status=processing_status,
            last_processing_error=processing_error,
            last_correlation_id=correlation_id,
        )
        db.add(ledger)
        db.commit()
        return

    ledger.last_received_at = now
    ledger.delivery_count += 1
    ledger.last_processing_status = processing_status
    ledger.last_processing_error = processing_error
    ledger.last_correlation_id = correlation_id
    db.commit()


def persist_webhook_event(
    db: Session,
    *,
    event_id: str,
    event_type: str,
    account_id: str | None,
    signature_valid: bool,
    raw_body: bytes,
    processing_status: str,
    processing_error: str | None,
    processed: bool,
    correlation_id: str,
) -> WebhookEvent:
    event = WebhookEvent(
        razorpay_event_id=event_id,
        event_type=event_type,
        account_id=account_id,
        signature_valid=signature_valid,
        processed=processed,
        processing_status=processing_status,
        processing_error=processing_error,
        payload_hash=_payload_hash(raw_body),
        raw_payload=raw_body.decode("utf-8", errors="replace"),
        correlation_id=correlation_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def process_payment_event(db: Session, payload: dict[str, Any], event_time: datetime) -> tuple[str, str | None]:
    event_type = payload.get("event")
    target_status = EVENT_TO_PAYMENT_STATUS.get(event_type)
    if target_status is None:
        return "ignored_event", None

    entity = _extract_payment_entity(payload)
    if entity is None:
        return "ignored_event", "missing_payment_entity"

    payment_id = entity.get("id")
    if not payment_id:
        return "ignored_event", "missing_payment_id"

    query = select(Payment).where(Payment.razorpay_payment_id == payment_id)
    payment = db.execute(query).scalar_one_or_none()

    if payment is None:
        payment = Payment(
            razorpay_payment_id=payment_id,
            razorpay_order_id=entity.get("order_id"),
            customer_id=None,
            amount_minor=int(entity.get("amount") or 0),
            currency=str(entity.get("currency") or "INR"),
            status=target_status,
            method=entity.get("method"),
            captured=bool(entity.get("captured") or target_status == "CAPTURED"),
            failure_code=entity.get("error_code"),
            failure_description=entity.get("error_description"),
            failure_source=entity.get("error_source"),
            failure_step=entity.get("error_step"),
            failure_reason=entity.get("error_reason"),
            first_seen_at=event_time,
            last_seen_at=event_time,
        )
        db.add(payment)
        db.commit()
        return "processed", None

    if event_time < payment.last_seen_at:
        return "stale_ignored", None

    if not can_transition_payment(payment.status, target_status):
        return "conflicting_transition", f"{payment.status}->{target_status}"

    payment.status = target_status
    payment.razorpay_order_id = entity.get("order_id") or payment.razorpay_order_id
    payment.amount_minor = int(entity.get("amount") or payment.amount_minor)
    payment.currency = str(entity.get("currency") or payment.currency)
    payment.method = entity.get("method") or payment.method
    payment.captured = bool(entity.get("captured") or target_status == "CAPTURED")
    payment.failure_code = entity.get("error_code")
    payment.failure_description = entity.get("error_description")
    payment.failure_source = entity.get("error_source")
    payment.failure_step = entity.get("error_step")
    payment.failure_reason = entity.get("error_reason")
    payment.last_seen_at = event_time
    db.commit()
    return "processed", None


def process_webhook_payload(db: Session, payload: dict[str, Any]) -> tuple[str, str | None]:
    try:
        adapter = get_gateway_adapter()
        mapped_payload = adapter.map_webhook_payload(payload)
        validation = adapter.validate_retrieval_consistency(mapped_payload)
        if not validation.ok:
            return "adapter_rejected", validation.reason
    except Exception:  # noqa: BLE001
        return "adapter_rejected", "adapter_mapping_failed"

    event_time = parse_event_time(mapped_payload)
    return process_payment_event(db, mapped_payload, event_time)


def _persist_workflow_stage_audits(
    db: Session,
    *,
    workflow_result: dict[str, Any],
    event_id: str,
    correlation_id: str,
) -> None:
    workflow_chain_id = workflow_result["workflow_chain_id"]
    for stage in workflow_result.get("stages", []):
        _write_audit_event(
            db,
            event_type=f"workflow.stage.{stage.get('stage', 'unknown')}",
            entity_type="RecoveryWorkflow",
            entity_id=workflow_chain_id,
            correlation_id=correlation_id,
            reason=stage.get("reason"),
            input_snapshot={
                "source_event_id": event_id,
                "payment_id": workflow_result.get("payment_id"),
                "event_type": workflow_result.get("event_type"),
            },
            outcome_snapshot=stage,
        )


def _persist_business_events(
    db: Session,
    *,
    workflow_result: dict[str, Any],
    event_id: str,
    correlation_id: str,
) -> None:
    for event_name in workflow_result.get("business_events", []):
        _write_audit_event(
            db,
            event_type=event_name,
            entity_type="RecoveryWorkflow",
            entity_id=workflow_result["workflow_chain_id"],
            correlation_id=correlation_id,
            reason=None,
            result="recorded",
            metadata={
                "source_event_id": event_id,
                "payment_id": workflow_result.get("payment_id"),
                "opportunity_id": workflow_result.get("opportunity_id"),
                "decision_id": workflow_result.get("decision_id"),
                "policy_evaluation_id": workflow_result.get("policy_evaluation_id"),
                "attempt_id": workflow_result.get("attempt_id"),
            },
        )


def _preview_payment_event(payload: dict[str, Any], db: Session) -> tuple[str, str | None]:
    event_type = payload.get("event")
    target_status = EVENT_TO_PAYMENT_STATUS.get(event_type)
    if target_status is None:
        return "ignored_event", None

    entity = _extract_payment_entity(payload)
    if entity is None:
        return "ignored_event", "missing_payment_entity"

    payment_id = entity.get("id")
    if not payment_id:
        return "ignored_event", "missing_payment_id"

    payment = db.execute(select(Payment).where(Payment.razorpay_payment_id == payment_id)).scalar_one_or_none()
    event_time = parse_event_time(payload)
    if payment is None:
        return "processed", None

    if event_time < payment.last_seen_at:
        return "stale_ignored", None

    if not can_transition_payment(payment.status, target_status):
        return "conflicting_transition", f"{payment.status}->{target_status}"
    return "processed", None


def process_razorpay_webhook_gateway(
    db: Session,
    raw_body: bytes,
    signature: str,
    webhook_secret: str,
    header_event_id: str | None = None,
) -> tuple[int, dict[str, Any]]:
    correlation_id = str(uuid.uuid4())
    header_event_id = (header_event_id or "").strip() or None

    signature_valid = verify_razorpay_signature(raw_body, signature, webhook_secret)
    if not signature_valid:
        unverified_event_id = header_event_id or f"unverified_{correlation_id}"
        persist_webhook_event(
            db,
            event_id=unverified_event_id,
            event_type="unknown",
            account_id=None,
            signature_valid=False,
            raw_body=raw_body,
            processing_status="invalid_signature",
            processing_error="signature_verification_failed",
            processed=False,
            correlation_id=correlation_id,
        )
        _write_audit_event(
            db,
            event_type="webhook.invalid_signature",
            entity_id=unverified_event_id,
            correlation_id=correlation_id,
            reason="signature_verification_failed",
            input_snapshot={"header_event_id": header_event_id, "raw_body_size": len(raw_body)},
            outcome_snapshot={"status_code": 401, "signature_valid": False},
        )
        _record_processor_ledger(
            db,
            event_id=unverified_event_id,
            event_type="unknown",
            event_created_at=None,
            correlation_id=correlation_id,
            processing_status="invalid_signature",
            processing_error="signature_verification_failed",
        )
        return 401, {
            "success": False,
            "error": {"code": "INVALID_SIGNATURE", "message": "Webhook signature verification failed."},
        }

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        _write_audit_event(
            db,
            event_type="webhook.invalid_json",
            entity_id=correlation_id,
            correlation_id=correlation_id,
            reason="invalid_json",
            input_snapshot={"raw_body_size": len(raw_body)},
            outcome_snapshot={"status_code": 400},
        )
        return 400, {
            "success": False,
            "error": {"code": "INVALID_JSON", "message": "Webhook payload is not valid JSON."},
        }

    payload_event_id = payload.get("id")
    if isinstance(payload_event_id, str) and payload_event_id.strip():
        event_id = payload_event_id.strip()
    elif header_event_id is not None:
        event_id = header_event_id
    else:
        event_id = payload_event_id

    if header_event_id is not None and isinstance(payload_event_id, str) and payload_event_id.strip():
        if payload_event_id.strip() != header_event_id:
            _write_audit_event(
                db,
                event_type="webhook.event_id_mismatch",
                entity_id=header_event_id,
                correlation_id=correlation_id,
                reason="header_payload_event_id_mismatch",
                input_snapshot={"payload_event_id": payload_event_id, "header_event_id": header_event_id},
                outcome_snapshot={"status_code": 400},
            )
            return 400, {
                "success": False,
                "error": {
                    "code": "EVENT_ID_MISMATCH",
                    "message": "Header and payload event ids do not match.",
                },
            }

    event_type = payload.get("event") or "unknown"
    account_id = payload.get("account_id")
    event_created_at = _extract_event_created_at(payload)

    if not isinstance(event_id, str) or not event_id.strip():
        _write_audit_event(
            db,
            event_type="webhook.missing_event_id",
            entity_id=correlation_id,
            correlation_id=correlation_id,
            reason="missing_event_id",
            input_snapshot={"event_type": event_type, "account_id": account_id},
            outcome_snapshot={"status_code": 400},
        )
        return 400, {
            "success": False,
            "error": {"code": "MISSING_EVENT_ID", "message": "Razorpay event id is required."},
        }


    existing = db.execute(select(WebhookEvent).where(WebhookEvent.razorpay_event_id == event_id)).scalar_one_or_none()
    if existing is not None:
        _record_processor_ledger(
            db,
            event_id=event_id,
            event_type=event_type,
            event_created_at=event_created_at,
            correlation_id=existing.correlation_id or correlation_id,
            processing_status="duplicate",
            processing_error=None,
        )
        _write_audit_event_once(
            db,
            event_type="webhook.duplicate",
            entity_id=event_id,
            correlation_id=existing.correlation_id or correlation_id,
            reason="duplicate_event",
            input_snapshot={"event_type": event_type, "account_id": account_id},
            outcome_snapshot={"status": "duplicate"},
        )
        return 200, {
            "success": True,
            "data": {
                "acknowledged": True,
                "duplicate": True,
                "event_id": event_id,
                "correlation_id": existing.correlation_id,
            },
        }


    status, error = process_webhook_payload(db, payload)

    persisted_event = persist_webhook_event(
        db,
        event_id=event_id,
        event_type=event_type,
        account_id=account_id,
        signature_valid=True,
        raw_body=raw_body,
        processing_status=status,
        processing_error=error,
        processed=True,
        correlation_id=correlation_id,
    )
    workflow_result = run_detection_to_verification_flow(
        db,
        payload=payload,
        processing_status=status,
        source_event_id=persisted_event.id,
    )

    if workflow_result is not None:
        _persist_workflow_stage_audits(
            db,
            workflow_result=workflow_result,
            event_id=event_id,
            correlation_id=correlation_id,
        )
        _persist_business_events(
            db,
            workflow_result=workflow_result,
            event_id=event_id,
            correlation_id=correlation_id,
        )

        for stage in workflow_result.get("stages", []):
            stage_name = stage.get("stage")
            if stage_name == "diagnosis":
                _write_audit_event(
                    db,
                    event_type=(
                        "ai.decision.escalated_safe"
                        if stage.get("fallback_used")
                        else "ai.decision.created"
                    ),
                    entity_id=event_id,
                    correlation_id=correlation_id,
                    reason=stage.get("reason"),
                    outcome_snapshot={
                        "workflow_chain_id": workflow_result["workflow_chain_id"],
                        "opportunity_id": workflow_result.get("opportunity_id"),
                        "decision_id": stage.get("decision_id"),
                        "recommended_action": stage.get("recommended_action"),
                        "decision_source": stage.get("decision_source"),
                    },
                )
            elif stage_name == "policy":
                _write_audit_event(
                    db,
                    event_type=f"policy.{str(stage.get('policy_result') or 'not_evaluated').lower()}",
                    entity_id=event_id,
                    correlation_id=correlation_id,
                    reason=stage.get("reason"),
                    outcome_snapshot={
                        "workflow_chain_id": workflow_result["workflow_chain_id"],
                        "opportunity_id": workflow_result.get("opportunity_id"),
                        "decision_id": workflow_result.get("decision_id"),
                        "policy_evaluation_id": stage.get("policy_evaluation_id"),
                        "policy_result": stage.get("policy_result"),
                        "reason_codes": stage.get("reason_codes"),
                    },
                )
            elif stage_name == "execution":
                _write_audit_event(
                    db,
                    event_type=f"recovery.execution.{stage.get('status')}",
                    entity_id=event_id,
                    correlation_id=correlation_id,
                    reason=stage.get("reason"),
                    outcome_snapshot={
                        "workflow_chain_id": workflow_result["workflow_chain_id"],
                        "opportunity_id": workflow_result.get("opportunity_id"),
                        "decision_id": workflow_result.get("decision_id"),
                        "policy_evaluation_id": workflow_result.get("policy_evaluation_id"),
                        "attempt_id": stage.get("attempt_id"),
                        "execution_status": stage.get("status"),
                    },
                )
            elif stage_name == "verification" and stage.get("status") == "completed":
                _write_audit_event(
                    db,
                    event_type="recovery.verification.completed",
                    entity_id=event_id,
                    correlation_id=correlation_id,
                    reason=None,
                    outcome_snapshot={
                        "workflow_chain_id": workflow_result["workflow_chain_id"],
                        "payment_id": workflow_result.get("payment_id"),
                        "attempt_count": stage.get("attempt_count"),
                        "outcomes": stage.get("outcomes"),
                    },
                )

    _write_audit_event(
        db,
        event_type=f"webhook.{status}",
        entity_id=event_id,
        correlation_id=correlation_id,
        reason=error,
        input_snapshot={"event_type": event_type, "account_id": account_id},
        outcome_snapshot={"status": status, "processed": True},
    )
    _record_processor_ledger(
        db,
        event_id=event_id,
        event_type=event_type,
        event_created_at=event_created_at,
        correlation_id=correlation_id,
        processing_status=status,
        processing_error=error,
    )

    return 200, {
        "success": True,
        "data": {
            "acknowledged": True,
            "duplicate": False,
            "event_id": event_id,
            "processing_status": status,
            "correlation_id": correlation_id,
        },
    }


def handle_razorpay_webhook(
    db: Session,
    raw_body: bytes,
    signature: str,
    webhook_secret: str,
    header_event_id: str | None = None,
) -> tuple[int, dict[str, Any]]:
    return process_razorpay_webhook_gateway(
        db,
        raw_body=raw_body,
        signature=signature,
        webhook_secret=webhook_secret,
        header_event_id=header_event_id,
    )


def replay_webhook_event_from_ledger(
    db: Session,
    *,
    event_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    correlation_id = str(uuid.uuid4())

    if not settings.internal_webhook_replay_enabled:
        _write_audit_event(
            db,
            event_type="webhook.replay.blocked",
            entity_id=event_id,
            correlation_id=correlation_id,
            reason="internal_replay_disabled",
        )
        return {"success": False, "error": {"code": "REPLAY_DISABLED", "message": "Internal replay is disabled."}}

    ledger = db.execute(
        select(WebhookProcessorLedger).where(WebhookProcessorLedger.razorpay_event_id == event_id)
    ).scalar_one_or_none()
    if ledger is None:
        _write_audit_event(
            db,
            event_type="webhook.replay.not_found",
            entity_id=event_id,
            correlation_id=correlation_id,
            reason="ledger_not_found",
        )
        return {"success": False, "error": {"code": "LEDGER_EVENT_NOT_FOUND", "message": "Ledger event was not found."}}

    stored_event = db.execute(select(WebhookEvent).where(WebhookEvent.razorpay_event_id == event_id)).scalar_one_or_none()
    if stored_event is None or not stored_event.signature_valid:
        _write_audit_event(
            db,
            event_type="webhook.replay.blocked",
            entity_id=event_id,
            correlation_id=correlation_id,
            reason="event_not_replayable",
            outcome_snapshot={"signature_valid": bool(stored_event and stored_event.signature_valid)},
        )
        return {
            "success": False,
            "error": {
                "code": "EVENT_NOT_REPLAYABLE",
                "message": "Only signature-valid persisted webhook events can be replayed.",
            },
        }

    try:
        payload = json.loads(stored_event.raw_payload)
    except json.JSONDecodeError:
        _write_audit_event(
            db,
            event_type="webhook.replay.invalid_payload",
            entity_id=event_id,
            correlation_id=correlation_id,
            reason="stored_payload_invalid_json",
        )
        return {
            "success": False,
            "error": {
                "code": "INVALID_STORED_PAYLOAD",
                "message": "Stored payload cannot be decoded for replay.",
            },
        }

    if dry_run:
        status, error = _preview_payment_event(payload, db)
        replay_mode = "dry_run"
    else:
        status, error = process_webhook_payload(db, payload)
        replay_mode = "apply"

    _write_audit_event(
        db,
        event_type="webhook.replay.completed",
        entity_id=event_id,
        correlation_id=correlation_id,
        reason=error,
        input_snapshot={"dry_run": dry_run, "event_type": stored_event.event_type},
        outcome_snapshot={"status": status, "replay_mode": replay_mode},
    )

    ledger.last_processing_status = f"replay_{status}"
    ledger.last_processing_error = error
    ledger.last_correlation_id = correlation_id
    db.commit()

    return {
        "success": True,
        "data": {
            "event_id": event_id,
            "replay_mode": replay_mode,
            "processing_status": status,
            "processing_error": error,
            "correlation_id": correlation_id,
        },
    }
