import hashlib
import hmac
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    AIAnalysis,
    AuditEvent,
    Payment,
    PolicyEvaluation,
    RecoveryAttempt,
    RecoveryDecision,
    RecoveryOutcome,
    RecoveryPaymentLink,
    RevenueOpportunity,
    WebhookEvent,
    WebhookProcessorLedger,
)
from .outcome_verifier import verify_outcomes_for_payment
from .webhooks import process_razorpay_webhook_gateway


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _failed_payload(*, event_id: str, payment_id: str, order_id: str, created_at: int, amount_minor: int, reason: str, method: str | None = "card") -> dict[str, Any]:
    entity: dict[str, Any] = {
        "id": payment_id,
        "order_id": order_id,
        "amount": amount_minor,
        "currency": "INR",
        "captured": False,
        "error_reason": reason,
    }
    if method is not None:
        entity["method"] = method
    return {
        "id": event_id,
        "event": "payment.failed",
        "account_id": "acc_demo_seed",
        "created_at": created_at,
        "payload": {"payment": {"entity": entity}},
    }


def _captured_payload(*, event_id: str, payment_id: str, order_id: str, created_at: int, amount_minor: int) -> dict[str, Any]:
    return {
        "id": event_id,
        "event": "payment.captured",
        "account_id": "acc_demo_seed",
        "created_at": created_at,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount_minor,
                    "currency": "INR",
                    "method": "card",
                    "captured": True,
                }
            }
        },
    }


def _post_payload(db: Session, payload: dict[str, Any], secret: str) -> dict[str, Any]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _sign(raw, secret)
    status_code, response = process_razorpay_webhook_gateway(
        db,
        raw_body=raw,
        signature=signature,
        webhook_secret=secret,
    )
    return {
        "status_code": status_code,
        "success": bool(response.get("success")),
        "processing_status": response.get("data", {}).get("processing_status"),
        "duplicate": bool(response.get("data", {}).get("duplicate")),
        "event_id": payload.get("id"),
    }


def reset_core_recovery_data(db: Session) -> None:
    db.query(RecoveryOutcome).delete()
    db.query(RecoveryPaymentLink).delete()
    db.query(RecoveryAttempt).delete()
    db.query(PolicyEvaluation).delete()
    db.query(AIAnalysis).delete()
    db.query(RecoveryDecision).delete()
    db.query(RevenueOpportunity).delete()
    db.query(Payment).delete()
    db.query(AuditEvent).delete()
    db.query(WebhookEvent).delete()
    db.query(WebhookProcessorLedger).delete()
    db.commit()


def seed_core_recovery_demo(db: Session) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.razorpay_webhook_secret
    if not secret:
        raise ValueError("RAZORPAY_WEBHOOK_SECRET is required for deterministic demo seeding")

    reset_core_recovery_data(db)

    base_time = 1724302000
    failed_cases = [
        ("evt_demo_001", "pay_demo_001", "order_demo_001", 240000, "network", "card"),
        ("evt_demo_002", "pay_demo_002", "order_demo_002", 310000, "issuer_declined", "card"),
        ("evt_demo_003", "pay_demo_003", "order_demo_003", 1200000, "network", "card"),
        ("evt_demo_004", "pay_demo_004", "order_demo_004", 980000, "unknown_reason", None),
        ("evt_demo_005", "pay_demo_005", "order_demo_005", 160000, "3ds_failed", "upi"),
        ("evt_demo_006", "pay_demo_006", "order_demo_006", 275000, "network", "card"),
        ("evt_demo_007", "pay_demo_007", "order_demo_007", 810000, "network", "card"),
        ("evt_demo_008", "pay_demo_008", "order_demo_008", 220000, "insufficient_funds", "card"),
        ("evt_demo_009", "pay_demo_009", "order_demo_009", 199000, "network", "netbanking"),
        ("evt_demo_010", "pay_demo_010", "order_demo_010", 490000, "issuer_declined", "card"),
        ("evt_demo_011", "pay_demo_011", "order_demo_011", 360000, "network", "card"),
        ("evt_demo_012", "pay_demo_012", "order_demo_012", 140000, "network", "card"),
    ]

    webhook_results: list[dict[str, Any]] = []
    for index, (event_id, payment_id, order_id, amount, reason, method) in enumerate(failed_cases):
        webhook_results.append(
            _post_payload(
                db,
                _failed_payload(
                    event_id=event_id,
                    payment_id=payment_id,
                    order_id=order_id,
                    created_at=base_time + (index * 10),
                    amount_minor=amount,
                    reason=reason,
                    method=method,
                ),
                secret,
            )
        )

    # Duplicate event scenario: replay exact event id and payload.
    webhook_results.append(
        _post_payload(
            db,
            _failed_payload(
                event_id="evt_demo_012",
                payment_id="pay_demo_012",
                order_id="order_demo_012",
                created_at=base_time + 110,
                amount_minor=140000,
                reason="network",
                method="card",
            ),
            secret,
        )
    )

    # Successful recovery scenarios.
    webhook_results.append(
        _post_payload(
            db,
            _captured_payload(
                event_id="evt_demo_cap_001",
                payment_id="pay_demo_001",
                order_id="order_demo_001",
                created_at=base_time + 500,
                amount_minor=240000,
            ),
            secret,
        )
    )
    webhook_results.append(
        _post_payload(
            db,
            _captured_payload(
                event_id="evt_demo_cap_002",
                payment_id="pay_demo_002",
                order_id="order_demo_002",
                created_at=base_time + 510,
                amount_minor=310000,
            ),
            secret,
        )
    )

    # Failed recovery scenario: verify with payment still failed.
    failed_payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == "pay_demo_005")
    ).scalar_one_or_none()
    if failed_payment is not None:
        verify_outcomes_for_payment(db, payment_id=failed_payment.id)

    total_opportunities = db.query(RevenueOpportunity).count()
    verified_recovered_minor = db.query(RecoveryAttempt).filter(RecoveryAttempt.verified_outcome == "VERIFIED_SUCCESS").with_entities(RecoveryAttempt.recovered_amount_minor).all()
    recovered_sum = sum(row[0] for row in verified_recovered_minor)

    policy_counts = {
        "allow": db.query(PolicyEvaluation).filter(PolicyEvaluation.result == "ALLOW").count(),
        "block": db.query(PolicyEvaluation).filter(PolicyEvaluation.result == "BLOCK").count(),
        "escalate": db.query(PolicyEvaluation).filter(PolicyEvaluation.result == "ESCALATE").count(),
    }

    return {
        "seeded_opportunities": total_opportunities,
        "policy_counts": policy_counts,
        "verified_recovered_minor": recovered_sum,
        "duplicate_events": len([item for item in webhook_results if item.get("duplicate")]),
        "webhook_results": webhook_results,
    }
