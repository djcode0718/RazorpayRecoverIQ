import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    AIAnalysis,
    AuditEvent,
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
    db.query(Order).delete()
    db.query(Customer).delete()
    db.query(Merchant).delete()
    db.query(AuditEvent).delete()
    db.query(WebhookEvent).delete()
    db.query(WebhookProcessorLedger).delete()
    db.commit()


SYNTHETIC_CUSTOMERS_SPEC = [
    {"name": "[TEST] Aarav Sharma", "email": "aarav.sharma.test@synthetix.internal", "phone": "+919876500001", "segment": "ENTERPRISE", "attempts": 16, "success": 14, "failed": 2, "rec_count": 2, "rec_rate": 88},
    {"name": "[TEST] Priya Patel", "email": "priya.patel.test@apex-logistics.internal", "phone": "+919876500002", "segment": "MID_MARKET", "attempts": 10, "success": 8, "failed": 2, "rec_count": 1, "rec_rate": 65},
    {"name": "[TEST] Rohan Verma", "email": "rohan.verma.test@zenith.internal", "phone": "+919876500003", "segment": "ENTERPRISE", "attempts": 24, "success": 21, "failed": 3, "rec_count": 3, "rec_rate": 92},
    {"name": "[TEST] Ananya Iyer", "email": "ananya.iyer.test@pulse-media.internal", "phone": "+919876500004", "segment": "GROWTH_SME", "attempts": 6, "success": 4, "failed": 2, "rec_count": 0, "rec_rate": 0},
    {"name": "[TEST] Vikram Malhotra", "email": "vikram.malhotra.test@delta.internal", "phone": "+919876500005", "segment": "SMB", "attempts": 8, "success": 6, "failed": 2, "rec_count": 1, "rec_rate": 50},
    {"name": "[TEST] Neha Reddy", "email": "neha.reddy.test@kite.internal", "phone": "+919876500006", "segment": "ENTERPRISE", "attempts": 19, "success": 17, "failed": 2, "rec_count": 2, "rec_rate": 85},
    {"name": "[TEST] Rajesh Kulkarni", "email": "rajesh.kulkarni.test@cloudpeak.internal", "phone": "+919876500007", "segment": "MID_MARKET", "attempts": 12, "success": 10, "failed": 2, "rec_count": 1, "rec_rate": 70},
    {"name": "[TEST] Kavita Sundaram", "email": "kavita.sundaram.test@nexa.internal", "phone": "+919876500008", "segment": "SMB", "attempts": 7, "success": 5, "failed": 2, "rec_count": 0, "rec_rate": 0},
    {"name": "[TEST] Siddharth Nair", "email": "siddharth.nair.test@vector.internal", "phone": "+919876500009", "segment": "GROWTH_SME", "attempts": 14, "success": 12, "failed": 2, "rec_count": 1, "rec_rate": 60},
    {"name": "[TEST] Meera Banerjee", "email": "meera.banerjee.test@stellar.internal", "phone": "+919876500010", "segment": "MID_MARKET", "attempts": 11, "success": 9, "failed": 2, "rec_count": 1, "rec_rate": 75},
    {"name": "[TEST] Aditya Joshi", "email": "aditya.joshi.test@horizon.internal", "phone": "+919876500011", "segment": "ENTERPRISE", "attempts": 20, "success": 18, "failed": 2, "rec_count": 2, "rec_rate": 90},
    {"name": "[TEST] Deepa Chawla", "email": "deepa.chawla.test@strata.internal", "phone": "+919876500012", "segment": "GROWTH_SME", "attempts": 9, "success": 7, "failed": 2, "rec_count": 1, "rec_rate": 55},
]


def seed_core_recovery_demo(db: Session) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.razorpay_webhook_secret
    if not secret:
        raise ValueError("RAZORPAY_WEBHOOK_SECRET is required for deterministic demo seeding")

    reset_core_recovery_data(db)

    # 1. Seed Synthetic Merchant
    merchant = Merchant(
        name="[TEST] Synthetix SaaS Platform",
        environment="simulation",
        razorpay_account_id="acc_demo_seed",
    )
    db.add(merchant)
    db.commit()

    # 2. Seed Synthetic Customers
    created_customers: list[Customer] = []
    for idx, spec in enumerate(SYNTHETIC_CUSTOMERS_SPEC, start=1):
        cust = Customer(
            external_customer_id=f"CUST-SYNTH-{idx:04d}",
            name=spec["name"],
            email=spec["email"],
            phone=spec["phone"],
            segment=spec["segment"],
            total_payment_attempts=spec["attempts"],
            successful_payment_count=spec["success"],
            failed_payment_count=spec["failed"],
            total_success_value=spec["success"] * 250000,
            average_payment_value=250000,
            historical_recovery_count=spec["rec_count"],
            historical_recovery_rate=spec["rec_rate"],
        )
        db.add(cust)
        created_customers.append(cust)
    db.commit()
    for cust in created_customers:
        db.refresh(cust)

    base_time = int((datetime.now(UTC) - timedelta(days=5)).timestamp())
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

    # 3. Seed Synthetic Orders and Ingest Webhook Events
    webhook_results: list[dict[str, Any]] = []
    for index, (event_id, payment_id, order_id, amount, reason, method) in enumerate(failed_cases):
        cust = created_customers[index % len(created_customers)]
        order = Order(
            razorpay_order_id=order_id,
            customer_id=cust.id,
            amount_minor=amount,
            currency="INR",
            status="attempted",
            attempts=1,
            raw_reference=f"[TEST] Order for {cust.name}",
        )
        db.add(order)
        db.commit()

        webhook_results.append(
            _post_payload(
                db,
                _failed_payload(
                    event_id=event_id,
                    payment_id=payment_id,
                    order_id=order_id,
                    created_at=base_time + (index * 36000),
                    amount_minor=amount,
                    reason=reason,
                    method=method,
                ),
                secret,
            )
        )

        # Link synthetic customer to payment and opportunity
        pay_rec = db.execute(select(Payment).where(Payment.razorpay_payment_id == payment_id)).scalar_one_or_none()
        if pay_rec is not None:
            pay_rec.customer_id = cust.id
            db.commit()

            opp_rec = db.execute(select(RevenueOpportunity).where(RevenueOpportunity.payment_id == pay_rec.id)).scalar_one_or_none()
            if opp_rec is not None:
                opp_rec.customer_id = cust.id
                opp_rec.order_id = order.id
                db.commit()

    # Duplicate event scenario: replay exact event id and payload.
    webhook_results.append(
        _post_payload(
            db,
            _failed_payload(
                event_id="evt_demo_012",
                payment_id="pay_demo_012",
                order_id="order_demo_012",
                created_at=base_time + (11 * 36000) + 120,
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
                created_at=base_time + 7200,
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
                created_at=base_time + 36000 + 7200,
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

    failed_payments = db.query(Payment).filter(Payment.status == "FAILED").count()
    successful_recoveries = db.query(RecoveryAttempt).filter(RecoveryAttempt.verified_outcome == "VERIFIED_SUCCESS").count()
    failed_recoveries = db.query(RecoveryAttempt).filter(RecoveryAttempt.verified_outcome == "VERIFIED_FAILURE").count()

    primary_recovery_opportunity = db.execute(
        select(RevenueOpportunity)
        .join(PolicyEvaluation, PolicyEvaluation.opportunity_id == RevenueOpportunity.id)
        .where(PolicyEvaluation.result == "ALLOW")
        .order_by(RevenueOpportunity.id.asc())
    ).scalars().first()

    blocked_opportunity = db.execute(
        select(RevenueOpportunity)
        .join(PolicyEvaluation, PolicyEvaluation.opportunity_id == RevenueOpportunity.id)
        .where(PolicyEvaluation.result == "BLOCK")
        .order_by(RevenueOpportunity.id.asc())
    ).scalars().first()

    escalated_opportunity = db.execute(
        select(RevenueOpportunity)
        .join(PolicyEvaluation, PolicyEvaluation.opportunity_id == RevenueOpportunity.id)
        .where(PolicyEvaluation.result == "ESCALATE")
        .order_by(RevenueOpportunity.id.asc())
    ).scalars().first()

    return {
        "seeded_opportunities": total_opportunities,
        "policy_counts": policy_counts,
        "verified_recovered_minor": recovered_sum,
        "duplicate_events": len([item for item in webhook_results if item.get("duplicate")]),
        "demo_story": {
            "failed_payments": failed_payments,
            "recoverable_opportunities": policy_counts["allow"],
            "blocked_opportunities": policy_counts["block"],
            "escalated_opportunities": policy_counts["escalate"],
            "failed_recoveries": failed_recoveries,
            "successful_recoveries": successful_recoveries,
            "primary_recovery_opportunity_id": primary_recovery_opportunity.id if primary_recovery_opportunity else None,
            "blocked_opportunity_id": blocked_opportunity.id if blocked_opportunity else None,
            "escalated_opportunity_id": escalated_opportunity.id if escalated_opportunity else None,
        },
        "webhook_results": webhook_results,
    }
