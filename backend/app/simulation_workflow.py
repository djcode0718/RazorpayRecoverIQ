from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Payment, RecoveryPaymentLink
from .outcome_verifier import verify_outcomes_for_payment, verify_outcomes_for_payment_link
from .policy_engine import evaluate_policy_for_decision
from .recovery_executor import execute_recovery_attempt
from .recovery_intelligence import create_recovery_decision_for_opportunity, upsert_revenue_opportunity_for_payment


def _extract_payment_entity(payload: dict[str, Any]) -> dict[str, Any] | None:
    payment = payload.get("payload", {}).get("payment", {}).get("entity")
    if isinstance(payment, dict):
        return payment
    plink = payload.get("payload", {}).get("payment_link", {}).get("entity")
    if isinstance(plink, dict):
        return {
            "id": plink.get("id"),
            "order_id": plink.get("order_id"),
            "amount": plink.get("amount"),
            "currency": plink.get("currency", "INR"),
            "method": "payment_link",
            "captured": plink.get("status") in {"paid", "PAID"},
            "error_reason": None,
        }
    order = payload.get("payload", {}).get("order", {}).get("entity")
    if isinstance(order, dict):
        return {
            "id": order.get("id"),
            "order_id": order.get("id"),
            "amount": order.get("amount"),
            "currency": order.get("currency", "INR"),
            "method": "order",
            "captured": order.get("status") in {"paid", "PAID"},
            "error_reason": None,
        }
    return None


def _resolve_payment(db: Session, payload: dict[str, Any]) -> Payment | None:
    entity = _extract_payment_entity(payload)
    if entity is None:
        return None
    razorpay_payment_id = entity.get("id")
    if not razorpay_payment_id:
        return None
    return db.execute(
        select(Payment).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).scalar_one_or_none()


def build_workflow_chain_id(payment: Payment) -> str:
    return f"payment:{payment.razorpay_payment_id or payment.id}"


def run_detection_to_verification_flow(
    db: Session,
    *,
    payload: dict[str, Any],
    processing_status: str,
    source_event_id: int,
) -> dict[str, Any] | None:
    if processing_status != "processed":
        return None

    event_type = payload.get("event")
    payment = _resolve_payment(db, payload)
    if payment is None:
        return None

    workflow: dict[str, Any] = {
        "workflow_chain_id": build_workflow_chain_id(payment),
        "payment_id": payment.id,
        "event_type": event_type,
        "stages": [],
        "opportunity_id": None,
        "decision_id": None,
        "policy_evaluation_id": None,
        "attempt_id": None,
        "business_events": [],
    }

    # Check for payment link reference or notes in payload
    plink_entity = payload.get("payload", {}).get("payment_link", {}).get("entity") or {}
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity") or {}
    plink_id = plink_entity.get("id") or payment_entity.get("notes", {}).get("recoveriq_payment_link_id")
    ref_id = plink_entity.get("reference_id")
    notes_opp_id = plink_entity.get("notes", {}).get("recoveriq_opportunity_id") or payment_entity.get("notes", {}).get("recoveriq_opportunity_id")
    opp_id_int = int(notes_opp_id) if notes_opp_id and str(notes_opp_id).isdigit() else None

    if event_type == "payment.failed":
        # Check if this failure belongs to an existing recovery payment link
        if plink_id or ref_id or opp_id_int:
            link_attempts = verify_outcomes_for_payment_link(
                db,
                payment_link_id=plink_id,
                reference_id=ref_id,
                opportunity_id=opp_id_int,
                is_success=False,
                payment_id=payment.id,
            )
            if link_attempts:
                workflow["stages"].append({
                    "stage": "verification",
                    "status": "completed",
                    "attempt_count": len(link_attempts),
                    "outcomes": {"VERIFIED_FAILURE": len(link_attempts)},
                })
                workflow["business_events"].append("outcome.received")
                return workflow

        opportunity = upsert_revenue_opportunity_for_payment(
            db,
            payment_id=payment.id,
            source_event_id=source_event_id,
        )
        if opportunity is None:
            workflow["stages"].append({"stage": "detection", "status": "skipped"})
            return workflow

        workflow["opportunity_id"] = opportunity.id
        workflow["stages"].append({"stage": "detection", "status": "completed", "opportunity_id": opportunity.id})
        workflow["business_events"].append("opportunity.created")

        decision_result = create_recovery_decision_for_opportunity(db, opportunity_id=opportunity.id)
        if decision_result is None:
            workflow["stages"].append({"stage": "diagnosis", "status": "failed"})
            return workflow

        workflow["decision_id"] = decision_result.decision.id
        workflow["stages"].append(
            {
                "stage": "diagnosis",
                "status": "completed",
                "decision_id": decision_result.decision.id,
                "fallback_used": decision_result.fallback_used,
                "reason": decision_result.failure_reason,
                "decision_source": decision_result.decision.decision_source,
                "recommended_action": decision_result.decision.recommended_action,
            }
        )
        workflow["business_events"].append("analysis.completed")
        workflow["business_events"].append("recovery.recommended")

        evaluation = evaluate_policy_for_decision(
            db,
            opportunity_id=opportunity.id,
            decision_id=decision_result.decision.id,
        )
        workflow["policy_evaluation_id"] = evaluation.id
        workflow["stages"].append(
            {
                "stage": "policy",
                "status": "completed",
                "policy_evaluation_id": evaluation.id,
                "policy_result": evaluation.result,
                "reason_codes": evaluation.reason_codes,
            }
        )
        workflow["business_events"].append("policy.evaluated")

        if evaluation.result == "BLOCK":
            workflow["stages"].append({"stage": "execution", "status": "blocked_by_policy"})
            return workflow
        if evaluation.result == "ESCALATE":
            workflow["stages"].append({"stage": "execution", "status": "escalated_by_policy"})
            return workflow

        workflow["business_events"].append("recovery.approved")

        try:
            attempt = execute_recovery_attempt(
                db,
                opportunity_id=opportunity.id,
                decision_id=decision_result.decision.id,
                policy_evaluation_id=evaluation.id,
            )
            workflow["attempt_id"] = attempt.id
            workflow["stages"].append(
                {
                    "stage": "execution",
                    "status": "completed",
                    "attempt_id": attempt.id,
                    "attempt_status": attempt.status,
                }
            )
            workflow["business_events"].append("recovery.executed")
        except ValueError as exc:
            workflow["stages"].append(
                {
                    "stage": "execution",
                    "status": "blocked_by_guardrail",
                    "reason": str(exc),
                }
            )

        return workflow

    if event_type in {"payment.captured", "payment_link.paid", "order.paid"}:
        attempts = []
        if plink_id or ref_id or opp_id_int:
            amount_val = int(plink_entity.get("amount") or payment_entity.get("amount") or 0) or None
            attempts = verify_outcomes_for_payment_link(
                db,
                payment_link_id=plink_id,
                reference_id=ref_id,
                opportunity_id=opp_id_int,
                is_success=True,
                amount_minor=amount_val,
                payment_id=payment.id,
            )
        
        if not attempts:
            attempts = verify_outcomes_for_payment(db, payment_id=payment.id)

        outcomes = {
            "VERIFIED_SUCCESS": 0,
            "VERIFIED_FAILURE": 0,
            "VERIFICATION_PENDING": 0,
            "UNVERIFIED": 0,
        }
        for attempt in attempts:
            key = attempt.verified_outcome or "UNVERIFIED"
            outcomes[key] = outcomes.get(key, 0) + 1

        workflow["stages"].append(
            {
                "stage": "verification",
                "status": "completed" if attempts else "skipped",
                "attempt_count": len(attempts),
                "outcomes": outcomes,
            }
        )
        workflow["business_events"].append("outcome.received")
        if outcomes.get("VERIFIED_SUCCESS", 0) > 0:
            workflow["business_events"].append("outcome.verified")
            workflow["business_events"].append("recovery.completed")
        return workflow

    return None
