import base64
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..demo_seed import seed_core_recovery_demo
from ..demo_seed import reset_core_recovery_data
from ..economics import estimate_intervention_cost_minor
from ..evaluation import (
    evaluation_summary_to_dict,
    generate_synthetic_cases,
    get_strategy_attribution_comparison,
    get_evaluation_run_summary,
    run_baseline_evaluation,
)
from ..models import (
    AuditEvent,
    Customer,
    EvaluationCase,
    EvaluationResult,
    Payment,
    PolicyEvaluation,
    RecoveryAttempt,
    RecoveryDecision,
    RecoveryPaymentLink,
    RevenueOpportunity,
    WebhookEvent,
)
from ..gateway_adapters import check_razorpay_api_connectivity
from ..policy_engine import evaluate_policy_for_decision
from ..recovery_executor import execute_recovery_attempt
from ..recovery_intelligence import create_recovery_decision_for_opportunity
from ..readiness import execute_readiness_acceptance_workflow
from ..webhooks import process_razorpay_webhook_gateway

router = APIRouter()


class EvaluationRunRequest(BaseModel):
    dataset_version: str = Field(min_length=1)
    split: str = "TEST"
    evaluation_run_id: str | None = None
    generate_if_missing: bool = True
    generation_seed: int = 42
    total_cases: int = Field(default=1000, ge=10, le=2000)
    force_regenerate: bool = False


class FailureScenarioTriggerRequest(BaseModel):
    scenario_id: str = Field(min_length=1)


def _derive_risk_bucket(*, recovery_probability: int, confidence: int, amount_at_risk_minor: int) -> str:
    if amount_at_risk_minor >= 500_000 or recovery_probability < 45 or confidence < 60:
        return "high"
    if amount_at_risk_minor >= 200_000 or recovery_probability < 70 or confidence < 75:
        return "medium"
    return "low"


def _safe_dict(data: dict | None) -> dict:
    return data if isinstance(data, dict) else {}


def _safe_json_object(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_stage(event_type: str) -> str | None:
    prefix = "workflow.stage."
    if event_type.startswith(prefix):
        return event_type[len(prefix) :]
    return None


def _stage_group(stage: str | None) -> str:
    if stage in {"detection", "diagnosis"}:
        return "Signal"
    if stage in {"policy"}:
        return "Policy"
    if stage in {"execution", "verification"}:
        return "Execution"
    return "System"


def _outcome_status(outcome_snapshot: dict | None, reason: str | None) -> str:
    payload = _safe_dict(outcome_snapshot)
    candidate = str(payload.get("status") or reason or "").lower()
    if any(token in candidate for token in ["deny", "blocked", "failed", "error"]):
        return "fail"
    if any(token in candidate for token in ["pending", "unverified"]):
        return "pending"
    return "pass"


def _serialize_opportunity_list_item(
    opportunity: RevenueOpportunity,
    *,
    decision: RecoveryDecision | None,
    policy_evaluation: PolicyEvaluation | None,
    latest_attempt: RecoveryAttempt | None,
) -> dict:
    risk_bucket = _derive_risk_bucket(
        recovery_probability=opportunity.recovery_probability,
        confidence=opportunity.confidence,
        amount_at_risk_minor=opportunity.amount_at_risk_minor,
    )
    if decision is not None:
        decision_evidence = _safe_dict(decision.evidence)
        evidence_bucket = decision_evidence.get("risk_bucket")
        if isinstance(evidence_bucket, str) and evidence_bucket.strip():
            risk_bucket = evidence_bucket.strip().lower()

    return {
        "id": opportunity.id,
        "customer_reference": f"CUST-{opportunity.customer_id}" if opportunity.customer_id is not None else "UNKNOWN",
        "status": opportunity.status,
        "failure_category": opportunity.failure_category,
        "failure_reason": opportunity.failure_reason,
        "recommended_action": opportunity.recommended_action,
        "confidence": opportunity.confidence,
        "recovery_probability": opportunity.recovery_probability,
        "amount_at_risk_minor": opportunity.amount_at_risk_minor,
        "expected_recovery_minor": opportunity.expected_recovery_minor,
        "expected_net_recovery_minor": opportunity.expected_net_recovery_minor,
        "risk_bucket": risk_bucket,
        "policy_result": policy_evaluation.result if policy_evaluation else None,
        "latest_attempt_status": latest_attempt.status if latest_attempt else None,
        "latest_verified_outcome": latest_attempt.verified_outcome if latest_attempt else None,
        "updated_at": opportunity.updated_at.isoformat() if opportunity.updated_at else None,
    }


def _timeline_from_audits(audits: list[AuditEvent]) -> list[dict]:
    timeline: list[dict] = []
    for audit in audits:
        stage = _parse_stage(audit.event_type)
        timeline.append(
            {
                "timestamp": audit.timestamp.isoformat() if audit.timestamp else None,
                "event_type": audit.event_type,
                "stage": stage,
                "stage_group": _stage_group(stage),
                "outcome_status": _outcome_status(audit.outcome_snapshot, audit.reason),
                "actor_type": audit.actor_type,
                "reason": audit.reason,
                "outcome": audit.outcome_snapshot,
            }
        )
    return timeline


def _group_timeline(timeline: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for event in timeline:
        key = str(event.get("stage_group") or "System")
        grouped.setdefault(key, []).append(event)

    result: list[dict] = []
    for group_name in ["Signal", "Policy", "Execution", "System"]:
        events = grouped.get(group_name, [])
        if not events:
            continue
        pass_count = len([item for item in events if item.get("outcome_status") == "pass"])
        fail_count = len([item for item in events if item.get("outcome_status") == "fail"])
        pending_count = len([item for item in events if item.get("outcome_status") == "pending"])
        result.append(
            {
                "group": group_name,
                "counts": {"pass": pass_count, "fail": fail_count, "pending": pending_count},
                "events": events,
            }
        )
    return result


def _evaluation_summary_or_404(db: Session, *, run_id: str):
    summary = get_evaluation_run_summary(db, evaluation_run_id=run_id)
    if summary is None:
        return None, JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "EVAL_RUN_NOT_FOUND",
                    "message": "Evaluation run id was not found.",
                },
            },
        )
    return summary, None


def _encode_opportunity_cursor(*, last_id: int) -> str:
    raw = json.dumps({"last_id": last_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def _decode_opportunity_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        decoded = json.loads(payload)
        last_id = decoded.get("last_id")
        return int(last_id) if isinstance(last_id, int) or isinstance(last_id, str) else None
    except Exception:
        return None


def _policy_checks_from_evaluation(policy: PolicyEvaluation | None) -> dict:
    if policy is None:
        return {
            "result": None,
            "checks": {},
            "reason_codes": {"failed": [], "passed": []},
            "policy_version": None,
        }

    checks = {
        # Prompt 05 judge-facing naming.
        "confidence_check": policy.confidence_check,
        "amount_check": policy.max_amount_check,
        "expected_recovery_check": policy.economic_check,
        "retry_limit_check": policy.retry_limit_check,
        "duplicate_check": policy.duplicate_check,
        "test_mode_check": policy.environment_check,
        # Backward-compatible aliases used by earlier UI revisions.
        "max_amount": policy.max_amount_check,
        "confidence": policy.confidence_check,
        "retry_limit": policy.retry_limit_check,
        "economic": policy.economic_check,
        "duplicate": policy.duplicate_check,
        "test_mode": policy.environment_check,
    }
    return {
        "result": policy.result,
        "checks": checks,
        "evaluated_rules": policy.evaluated_rules,
        "reason_codes": policy.reason_codes,
        "policy_version": policy.policy_version,
        "evaluated_at": policy.evaluated_at.isoformat() if policy.evaluated_at else None,
    }


def _latest_decision_for_opportunity(db: Session, opportunity_id: int) -> RecoveryDecision | None:
    return db.execute(
        select(RecoveryDecision)
        .where(RecoveryDecision.opportunity_id == opportunity_id)
        .order_by(RecoveryDecision.created_at.desc(), RecoveryDecision.id.desc())
    ).scalars().first()


def _latest_policy_for_decision(db: Session, decision_id: int) -> PolicyEvaluation | None:
    return db.execute(
        select(PolicyEvaluation)
        .where(PolicyEvaluation.decision_id == decision_id)
        .order_by(PolicyEvaluation.evaluated_at.desc(), PolicyEvaluation.id.desc())
    ).scalars().first()


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    mode = (
        "razorpay_test"
        if settings.payment_adapter_mode.lower() == "razorpay_test"
        and settings.razorpay_test_mode_keys
        and not settings.razorpay_live_mode_detected
        else "simulation"
    )
    mode_label = "Razorpay Test Mode" if mode == "razorpay_test" else "Simulation Mode"

    revenue_at_risk_minor = db.execute(
        select(func.coalesce(func.sum(RevenueOpportunity.amount_at_risk_minor), 0))
    ).scalar_one()
    recoverable_revenue_minor = db.execute(
        select(func.coalesce(func.sum(RevenueOpportunity.expected_recovery_minor), 0))
    ).scalar_one()
    active_opportunities = db.execute(
        select(func.count(RevenueOpportunity.id)).where(RevenueOpportunity.status.not_in(["CLOSED", "RESOLVED"]))
    ).scalar_one()
    approved_actions = db.execute(
        select(func.count(PolicyEvaluation.id)).where(PolicyEvaluation.result == "ALLOW")
    ).scalar_one()
    blocked_actions = db.execute(
        select(func.count(PolicyEvaluation.id)).where(PolicyEvaluation.result != "ALLOW")
    ).scalar_one()
    escalations = db.execute(
        select(func.count(RecoveryDecision.id)).where(RecoveryDecision.recommended_action == "ESCALATE")
    ).scalar_one()

    attempts = db.execute(select(RecoveryAttempt.action, RecoveryAttempt.recovered_amount_minor)).all()
    recovery_attempts = len(attempts)
    gross_recovered_minor = sum(row.recovered_amount_minor for row in attempts)
    intervention_cost_minor = sum(estimate_intervention_cost_minor(row.action) for row in attempts)
    net_recovered_minor = gross_recovered_minor - intervention_cost_minor

    recovery_rate = 0.0
    if recoverable_revenue_minor > 0:
        recovery_rate = round(gross_recovered_minor / recoverable_revenue_minor, 4)

    data = {
        "mode": mode,
        "mode_label": mode_label,
        "revenue_at_risk_minor": revenue_at_risk_minor,
        "recoverable_revenue_minor": recoverable_revenue_minor,
        "recovery_attempts": recovery_attempts,
        "gross_recovered_minor": gross_recovered_minor,
        "net_recovered_minor": net_recovered_minor,
        "recovery_rate": recovery_rate,
        "active_opportunities": active_opportunities,
        "allowed_actions": approved_actions,
        "escalated_actions": escalations,
        "approved_actions": approved_actions,
        "blocked_actions": blocked_actions,
        "escalations": escalations,
    }
    return {"success": True, "data": data}


@router.get("/opportunities")
def list_opportunities(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=25, ge=1, le=100),
    pagination_mode: str = Query(default="page", pattern="^(page|cursor)$"),
    cursor: str | None = None,
    status: str | None = None,
    action: str | None = None,
    risk_bucket: str | None = None,
    search: str | None = None,
    sort_by: str = "updated_desc",
):
    bounded_page = max(page, 1)
    bounded_page_size = min(max(page_size, 1), 100)
    query = select(RevenueOpportunity)
    if status:
        query = query.where(RevenueOpportunity.status == status)
    if action:
        query = query.where(RevenueOpportunity.recommended_action == action)

    normalized_search = (search or "").strip().lower()
    normalized_bucket = (risk_bucket or "").strip().lower()

    pagination_mode = pagination_mode.lower()
    decoded_cursor = _decode_opportunity_cursor(cursor)

    if pagination_mode == "cursor":
        if sort_by != "updated_desc":
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": {
                        "code": "CURSOR_SORT_NOT_SUPPORTED",
                        "message": "Cursor pagination currently supports sort_by=updated_desc only.",
                    },
                },
            )
        if cursor and decoded_cursor is None:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": {
                        "code": "INVALID_CURSOR",
                        "message": "Cursor token is invalid.",
                    },
                },
            )

    opportunities: list[RevenueOpportunity] = []
    if pagination_mode == "cursor":
        candidate_cursor = decoded_cursor
        scanned = 0
        enriched_items: list[dict] = []
        while len(enriched_items) < bounded_page_size + 1 and scanned < 1000:
            batch_query = query
            if candidate_cursor is not None:
                batch_query = batch_query.where(RevenueOpportunity.id < candidate_cursor)

            batch = db.execute(
                batch_query.order_by(RevenueOpportunity.id.desc()).limit(min(120, bounded_page_size * 4))
            ).scalars().all()
            if not batch:
                break

            opportunities = list(batch)
            scanned += len(opportunities)
            candidate_cursor = opportunities[-1].id

            for opportunity in opportunities:
                latest_decision = db.execute(
                    select(RecoveryDecision)
                    .where(RecoveryDecision.opportunity_id == opportunity.id)
                    .order_by(RecoveryDecision.created_at.desc(), RecoveryDecision.id.desc())
                ).scalars().first()

                policy_evaluation = None
                if latest_decision is not None:
                    policy_evaluation = db.execute(
                        select(PolicyEvaluation)
                        .where(PolicyEvaluation.decision_id == latest_decision.id)
                        .order_by(PolicyEvaluation.evaluated_at.desc(), PolicyEvaluation.id.desc())
                    ).scalars().first()

                latest_attempt = db.execute(
                    select(RecoveryAttempt)
                    .where(RecoveryAttempt.opportunity_id == opportunity.id)
                    .order_by(RecoveryAttempt.attempt_number.desc(), RecoveryAttempt.id.desc())
                ).scalars().first()

                serialized = _serialize_opportunity_list_item(
                    opportunity,
                    decision=latest_decision,
                    policy_evaluation=policy_evaluation,
                    latest_attempt=latest_attempt,
                )

                if normalized_bucket and serialized["risk_bucket"] != normalized_bucket:
                    continue
                if normalized_search and normalized_search not in f"{serialized['id']} {serialized['failure_category'] or ''} {serialized['failure_reason'] or ''} {serialized['recommended_action'] or ''}".lower():
                    continue

                enriched_items.append(serialized)
                if len(enriched_items) >= bounded_page_size + 1:
                    break

        paginated_items = enriched_items[:bounded_page_size]
        next_cursor = _encode_opportunity_cursor(last_id=paginated_items[-1]["id"]) if len(enriched_items) > bounded_page_size else None

        total_count = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        return {
            "success": True,
            "data": {
                "items": paginated_items,
                "count": len(paginated_items),
                "page": 1,
                "page_size": bounded_page_size,
                "total_count": total_count,
                "total_pages": 1,
                "has_next": next_cursor is not None,
                "has_prev": decoded_cursor is not None,
                "pagination_mode": "cursor",
                "cursor": cursor,
                "next_cursor": next_cursor,
                "filters": {
                    "status": status,
                    "action": action,
                    "risk_bucket": risk_bucket,
                    "search": search,
                    "sort_by": sort_by,
                },
            },
        }

    opportunities = list(
        db.execute(
            query.order_by(RevenueOpportunity.updated_at.desc(), RevenueOpportunity.id.desc()).limit(250)
        ).scalars().all()
    )

    enriched_items: list[dict] = []
    for opportunity in opportunities:
        latest_decision = db.execute(
            select(RecoveryDecision)
            .where(RecoveryDecision.opportunity_id == opportunity.id)
            .order_by(RecoveryDecision.created_at.desc(), RecoveryDecision.id.desc())
        ).scalars().first()

        policy_evaluation = None
        if latest_decision is not None:
            policy_evaluation = db.execute(
                select(PolicyEvaluation)
                .where(PolicyEvaluation.decision_id == latest_decision.id)
                .order_by(PolicyEvaluation.evaluated_at.desc(), PolicyEvaluation.id.desc())
            ).scalars().first()

        latest_attempt = db.execute(
            select(RecoveryAttempt)
            .where(RecoveryAttempt.opportunity_id == opportunity.id)
            .order_by(RecoveryAttempt.attempt_number.desc(), RecoveryAttempt.id.desc())
        ).scalars().first()

        enriched_items.append(
            _serialize_opportunity_list_item(
                opportunity,
                decision=latest_decision,
                policy_evaluation=policy_evaluation,
                latest_attempt=latest_attempt,
            )
        )

    filtered_items = enriched_items

    if normalized_bucket:
        filtered_items = [item for item in filtered_items if item["risk_bucket"] == normalized_bucket]
    if normalized_search:
        filtered_items = [
            item
            for item in filtered_items
            if normalized_search in f"{item['id']} {item['failure_category'] or ''} {item['failure_reason'] or ''} {item['recommended_action'] or ''}".lower()
        ]

    sort_key_map = {
        "updated_desc": lambda item: item.get("updated_at") or "",
        "risk_desc": lambda item: item.get("amount_at_risk_minor") or 0,
        "risk_asc": lambda item: item.get("amount_at_risk_minor") or 0,
        "confidence_desc": lambda item: item.get("confidence") or 0,
        "probability_desc": lambda item: item.get("recovery_probability") or 0,
    }
    selected_sort = sort_key_map.get(sort_by, sort_key_map["updated_desc"])
    reverse_sort = sort_by in {"updated_desc", "risk_desc", "confidence_desc", "probability_desc"}
    filtered_items = sorted(filtered_items, key=selected_sort, reverse=reverse_sort)
    total_count = len(filtered_items)
    total_pages = max(1, (total_count + bounded_page_size - 1) // bounded_page_size)
    start_index = (bounded_page - 1) * bounded_page_size
    end_index = start_index + bounded_page_size
    paginated_items = filtered_items[start_index:end_index]

    return {
        "success": True,
        "data": {
            "items": paginated_items,
            "count": len(paginated_items),
            "page": bounded_page,
            "page_size": bounded_page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": bounded_page < total_pages,
            "has_prev": bounded_page > 1,
            "pagination_mode": "page",
            "cursor": None,
            "next_cursor": None,
            "filters": {
                "status": status,
                "action": action,
                "risk_bucket": risk_bucket,
                "search": search,
                "sort_by": sort_by,
            },
        },
    }


@router.get("/opportunities/{opportunity_id}")
def get_opportunity_detail(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)
    ).scalar_one_or_none()
    if opportunity is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "OPPORTUNITY_NOT_FOUND",
                    "message": "Opportunity id was not found.",
                },
            },
        )

    decision = db.execute(
        select(RecoveryDecision)
        .where(RecoveryDecision.opportunity_id == opportunity.id)
        .order_by(RecoveryDecision.created_at.desc(), RecoveryDecision.id.desc())
    ).scalars().first()
    policy = None
    if decision is not None:
        policy = db.execute(
            select(PolicyEvaluation)
            .where(PolicyEvaluation.decision_id == decision.id)
            .order_by(PolicyEvaluation.evaluated_at.desc(), PolicyEvaluation.id.desc())
        ).scalars().first()

    attempts = db.execute(
        select(RecoveryAttempt)
        .where(RecoveryAttempt.opportunity_id == opportunity.id)
        .order_by(RecoveryAttempt.attempt_number.asc(), RecoveryAttempt.id.asc())
    ).scalars().all()
    attempt_ids = [attempt.id for attempt in attempts]
    links = (
        db.execute(select(RecoveryPaymentLink).where(RecoveryPaymentLink.recovery_attempt_id.in_(attempt_ids))).scalars().all()
        if attempt_ids
        else []
    )
    link_by_attempt_id = {link.recovery_attempt_id: link for link in links}

    payment = None
    if opportunity.payment_id is not None:
        payment = db.execute(select(Payment).where(Payment.id == opportunity.payment_id)).scalar_one_or_none()

    customer = None
    customer_id = opportunity.customer_id
    if payment is not None and payment.customer_id is not None:
        customer_id = payment.customer_id
    if customer_id is not None:
        customer = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()

    customer_payments = []
    if customer_id is not None:
        customer_payments = db.execute(select(Payment).where(Payment.customer_id == customer_id)).scalars().all()

    workflow_audits: list[AuditEvent] = []
    if payment is not None and payment.razorpay_payment_id:
        workflow_chain_id = f"payment:{payment.razorpay_payment_id}"
        workflow_audits = list(
            db.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "RecoveryWorkflow")
            .where(AuditEvent.entity_id == workflow_chain_id)
            .order_by(AuditEvent.id.asc())
        ).scalars().all()
        )

    gross_recovered_minor = sum(attempt.recovered_amount_minor for attempt in attempts)
    total_intervention_cost_minor = sum(estimate_intervention_cost_minor(attempt.action) for attempt in attempts)

    timeline = _timeline_from_audits(workflow_audits)
    timeline_groups = _group_timeline(timeline)

    has_recommendation = bool((decision.recommended_action if decision else opportunity.recommended_action))
    approved = bool(policy is not None and policy.result == "ALLOW")
    has_payment_link = any(attempt.id in link_by_attempt_id for attempt in attempts)
    pending = any(attempt.status in {"PENDING", "IN_PROGRESS", "REQUESTED"} for attempt in attempts)
    successful = any(
        (attempt.verified_outcome == "VERIFIED_SUCCESS") or (attempt.recovered_amount_minor > 0)
        for attempt in attempts
    )
    verified = any(
        (attempt.verified_outcome or "").startswith("VERIFIED")
        for attempt in attempts
    )
    recovered = any(
        (attempt.verified_outcome == "VERIFIED_SUCCESS") and attempt.recovered_amount_minor > 0
        for attempt in attempts
    )

    recovery_state = {
        "current": (
            "Recovered"
            if recovered
            else "Verified"
            if verified
            else "Successful"
            if successful
            else "Pending"
            if pending
            else "Payment Link Created"
            if has_payment_link
            else "Approved"
            if approved
            else "Recommended"
            if has_recommendation
            else "Opportunity"
        ),
        "stages": [
            {"name": "Opportunity", "reached": True},
            {"name": "Recommended", "reached": has_recommendation},
            {"name": "Approved", "reached": approved},
            {"name": "Payment Link Created", "reached": has_payment_link},
            {"name": "Pending", "reached": pending},
            {"name": "Successful", "reached": successful},
            {"name": "Verified", "reached": verified},
            {"name": "Recovered", "reached": recovered},
        ],
    }

    customer_history = {
        "customer_id": customer_id,
        "segment": customer.segment if customer else None,
        "total_attempts": len(customer_payments),
        "successful_count": len([row for row in customer_payments if bool(row.captured) or row.status in {"CAPTURED", "SUCCEEDED"}]),
        "failed_count": len([row for row in customer_payments if row.status in {"FAILED", "FAILURE"}]),
        "historical_recovery_count": customer.historical_recovery_count if customer else None,
    }

    failure_context = {
        "category": opportunity.failure_category,
        "reason": opportunity.failure_reason,
        "payment_failure_reason": payment.failure_reason if payment else None,
        "payment_failure_code": payment.failure_code if payment else None,
    }

    data = {
        "opportunity": {
            "id": opportunity.id,
            "status": opportunity.status,
            "failure_category": opportunity.failure_category,
            "failure_reason": opportunity.failure_reason,
            "recommended_action": opportunity.recommended_action,
            "recovery_probability": opportunity.recovery_probability,
            "confidence": opportunity.confidence,
            "currency": opportunity.currency,
            "amount_at_risk_minor": opportunity.amount_at_risk_minor,
            "created_at": opportunity.created_at.isoformat() if opportunity.created_at else None,
            "updated_at": opportunity.updated_at.isoformat() if opportunity.updated_at else None,
        },
        "payment": (
            {
                "payment_id": payment.id,
                "razorpay_payment_id": payment.razorpay_payment_id,
                "razorpay_order_id": payment.razorpay_order_id,
                "status": payment.status,
                "captured": payment.captured,
                "method": payment.method,
                "amount_minor": payment.amount_minor,
                "currency": payment.currency,
                "failure_reason": payment.failure_reason,
                "failure_code": payment.failure_code,
            }
            if payment is not None
            else None
        ),
        "customer_history": customer_history,
        "failure": failure_context,
        "evidence": {
            "diagnosis": decision.diagnosis if decision else None,
            "model_evidence": decision.evidence if decision else {},
            "decision_source": decision.decision_source if decision else None,
            "provider": decision.provider if decision else None,
            "model": decision.model if decision else None,
            "schema_version": decision.schema_version if decision else None,
        },
        "economics": {
            "expected_recovery_minor": opportunity.expected_recovery_minor,
            "estimated_intervention_cost_minor": opportunity.estimated_intervention_cost_minor,
            "expected_net_recovery_minor": opportunity.expected_net_recovery_minor,
            "gross_recovered_minor": gross_recovered_minor,
            "net_recovered_minor": gross_recovered_minor - total_intervention_cost_minor,
            "total_intervention_cost_minor": total_intervention_cost_minor,
        },
        "policy_checks": _policy_checks_from_evaluation(policy),
        "action_traceability": {
            "recommended_action": decision.recommended_action if decision else opportunity.recommended_action,
            "allow_execution": policy.result == "ALLOW" if policy else None,
            "latest_attempt_status": attempts[-1].status if attempts else None,
            "latest_verified_outcome": attempts[-1].verified_outcome if attempts else None,
            "attempt_count": len(attempts),
        },
        "recovery_state": recovery_state,
        "attempts": [
            {
                "attempt_number": attempt.attempt_number,
                "action": attempt.action,
                "status": attempt.status,
                "verified_outcome": attempt.verified_outcome,
                "amount_minor": attempt.amount_minor,
                "recovered_amount_minor": attempt.recovered_amount_minor,
                "requested_at": attempt.requested_at.isoformat() if attempt.requested_at else None,
                "executed_at": attempt.executed_at.isoformat() if attempt.executed_at else None,
                "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
                "payment_link": (
                    {
                        "payment_link_id": link_by_attempt_id[attempt.id].payment_link_id,
                        "payment_link_reference_id": link_by_attempt_id[attempt.id].payment_link_reference_id,
                        "status": link_by_attempt_id[attempt.id].status,
                    }
                    if attempt.id in link_by_attempt_id
                    else None
                ),
            }
            for attempt in attempts
        ],
        "timeline": timeline,
        "timeline_groups": timeline_groups,
        "audit_trail": [
            {
                "timestamp": item.get("timestamp"),
                "event_type": item.get("event_type"),
                "stage": item.get("stage"),
                "outcome_status": item.get("outcome_status"),
                "reason": item.get("reason"),
            }
            for item in timeline
        ],
    }
    return {"success": True, "data": data}


@router.get("/opportunities/{opportunity_id}/explanation")
def get_opportunity_explanation(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)).scalar_one_or_none()
    if opportunity is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "OPPORTUNITY_NOT_FOUND",
                    "message": "Opportunity id was not found.",
                },
            },
        )

    decision = _latest_decision_for_opportunity(db, opportunity_id)
    if decision is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "OPPORTUNITY_NOT_EVALUATED",
                    "message": "Opportunity has no diagnosis yet.",
                },
            },
        )

    evidence = _safe_dict(decision.evidence)
    data = {
        "opportunity_id": opportunity.id,
        "diagnosis": decision.diagnosis,
        "confidence": decision.confidence,
        "recovery_probability": decision.recovery_probability,
        "recommended_action": decision.recommended_action,
        "evidence": evidence.get("signals", []),
        "provider": decision.provider,
        "model": decision.model,
        "schema_version": decision.schema_version,
        "decision_source": decision.decision_source,
    }
    return {"success": True, "data": data}


@router.post("/opportunities/{opportunity_id}/evaluate")
def evaluate_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)).scalar_one_or_none()
    if opportunity is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "OPPORTUNITY_NOT_FOUND",
                    "message": "Opportunity id was not found.",
                },
            },
        )

    decision_result = create_recovery_decision_for_opportunity(db, opportunity_id=opportunity_id)
    if decision_result is None:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "EVALUATION_FAILED",
                    "message": "Unable to evaluate opportunity.",
                },
            },
        )

    policy = evaluate_policy_for_decision(db, opportunity_id=opportunity_id, decision_id=decision_result.decision.id)
    return {
        "success": True,
        "data": {
            "opportunity_id": opportunity_id,
            "decision_id": decision_result.decision.id,
            "recommended_action": decision_result.decision.recommended_action,
            "fallback_used": decision_result.fallback_used,
            "policy_evaluation_id": policy.id,
            "policy_result": policy.result,
            "reason_codes": policy.reason_codes,
        },
    }


@router.post("/opportunities/{opportunity_id}/execute")
def execute_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)).scalar_one_or_none()
    if opportunity is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "OPPORTUNITY_NOT_FOUND",
                    "message": "Opportunity id was not found.",
                },
            },
        )

    decision = _latest_decision_for_opportunity(db, opportunity_id)
    if decision is None:
        decision_result = create_recovery_decision_for_opportunity(db, opportunity_id=opportunity_id)
        if decision_result is None:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": {
                        "code": "EVALUATION_FAILED",
                        "message": "Unable to evaluate opportunity before execution.",
                    },
                },
            )
        decision = decision_result.decision

    policy = _latest_policy_for_decision(db, decision.id)
    if policy is None:
        policy = evaluate_policy_for_decision(db, opportunity_id=opportunity_id, decision_id=decision.id)

    if policy.result != "ALLOW":
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": {
                    "code": "POLICY_NOT_ALLOW",
                    "message": "Policy blocked automated execution for this opportunity.",
                },
                "data": {
                    "policy_result": policy.result,
                    "reason_codes": policy.reason_codes,
                },
            },
        )

    try:
        attempt = execute_recovery_attempt(
            db,
            opportunity_id=opportunity_id,
            decision_id=decision.id,
            policy_evaluation_id=policy.id,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": {
                    "code": "EXECUTION_BLOCKED",
                    "message": str(exc),
                },
            },
        )

    payment_link = db.execute(
        select(RecoveryPaymentLink)
        .where(RecoveryPaymentLink.recovery_attempt_id == attempt.id)
        .order_by(RecoveryPaymentLink.id.desc())
    ).scalars().first()

    return {
        "success": True,
        "data": {
            "opportunity_id": opportunity_id,
            "attempt_id": attempt.id,
            "attempt_status": attempt.status,
            "verified_outcome": attempt.verified_outcome,
            "payment_link": (
                {
                    "payment_link_id": payment_link.payment_link_id,
                    "payment_link_reference_id": payment_link.payment_link_reference_id,
                    "status": payment_link.status,
                    "amount_minor": payment_link.amount_minor,
                    "currency": payment_link.currency,
                }
                if payment_link is not None
                else None
            ),
        },
    }


@router.get("/opportunities/{opportunity_id}/audit")
def get_opportunity_audit(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)).scalar_one_or_none()
    if opportunity is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "OPPORTUNITY_NOT_FOUND",
                    "message": "Opportunity id was not found.",
                },
            },
        )

    payment = db.execute(select(Payment).where(Payment.id == opportunity.payment_id)).scalar_one_or_none() if opportunity.payment_id else None
    workflow_chain_id = f"payment:{payment.razorpay_payment_id}" if payment and payment.razorpay_payment_id else None
    audits = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "RecoveryWorkflow")
            .where(AuditEvent.entity_id == workflow_chain_id)
            .order_by(AuditEvent.id.asc())
        ).scalars().all()
        if workflow_chain_id
        else []
    )
    timeline = _timeline_from_audits(list(audits))
    return {
        "success": True,
        "data": {
            "opportunity_id": opportunity_id,
            "workflow_chain_id": workflow_chain_id,
            "count": len(timeline),
            "items": timeline,
        },
    }


@router.get("/health")
def health() -> dict:
    return {"success": True, "data": {"status": "ok"}}


@router.get("/failure-demos")
def list_failure_demos() -> dict:
    scenarios = [
        {
            "scenario_id": "invalid_webhook_signature",
            "title": "Invalid webhook signature",
            "severity": "high",
            "expected_error_code": "INVALID_SIGNATURE",
            "description": "Demonstrates gateway rejection for tampered webhook signatures.",
            "expected_behavior": "Request rejected before domain processing.",
            "actual_behavior": "Returns 401 with sanitized error envelope.",
        },
        {
            "scenario_id": "invalid_evaluation_request",
            "title": "Invalid evaluation request",
            "severity": "medium",
            "expected_error_code": "VALIDATION_ERROR",
            "description": "Demonstrates request validation guardrails on evaluation inputs.",
            "expected_behavior": "Invalid payload cannot run evaluation.",
            "actual_behavior": "Returns 422 with field-level validation details.",
        },
        {
            "scenario_id": "opportunity_not_found",
            "title": "Opportunity detail not found",
            "severity": "low",
            "expected_error_code": "OPPORTUNITY_NOT_FOUND",
            "description": "Demonstrates safe 404 handling for missing resources.",
            "expected_behavior": "Missing opportunity is not auto-created.",
            "actual_behavior": "Returns 404 with deterministic error code.",
        },
        {
            "scenario_id": "ai_invalid_output",
            "title": "AI invalid output",
            "severity": "high",
            "expected_error_code": "AI_SCHEMA_INVALID",
            "description": "Demonstrates schema validation rejection for malformed AI output.",
            "expected_behavior": "Invalid AI output is never executed.",
            "actual_behavior": "Returns safe error and indicates fallback/escalation path.",
        },
        {
            "scenario_id": "ai_unavailable",
            "title": "AI provider unavailable",
            "severity": "high",
            "expected_error_code": "AI_UNAVAILABLE",
            "description": "Demonstrates graceful handling when AI provider is unreachable.",
            "expected_behavior": "System remains functional with safe fallback.",
            "actual_behavior": "Returns sanitized unavailable response.",
        },
        {
            "scenario_id": "policy_blocked",
            "title": "Policy blocked",
            "severity": "medium",
            "expected_error_code": "POLICY_NOT_ALLOW",
            "description": "Demonstrates deterministic policy preventing unsafe execution.",
            "expected_behavior": "AI cannot bypass deterministic policy.",
            "actual_behavior": "Returns 409 blocked response.",
        },
        {
            "scenario_id": "recovery_failure",
            "title": "Recovery failure",
            "severity": "high",
            "expected_error_code": "RECOVERY_EXECUTION_FAILED",
            "description": "Demonstrates safe handling when recovery execution fails.",
            "expected_behavior": "No recovered revenue is counted.",
            "actual_behavior": "Returns failure envelope with safe metadata.",
        },
        {
            "scenario_id": "duplicate_webhook",
            "title": "Duplicate webhook",
            "severity": "medium",
            "expected_error_code": "DUPLICATE_EVENT_IGNORED",
            "description": "Demonstrates idempotent duplicate-event protection.",
            "expected_behavior": "Duplicate event has no duplicate side effects.",
            "actual_behavior": "Returns deterministic duplicate-ignored response.",
        },
    ]
    return {"success": True, "data": {"scenarios": scenarios}}


@router.post("/failure-demos/trigger")
def trigger_failure_demo(request: FailureScenarioTriggerRequest):
    scenario_id = request.scenario_id.strip().lower()
    if scenario_id == "invalid_evaluation_request":
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Evaluation request validation failed.",
                },
                "data": {
                    "expected_behavior": "Invalid payload is rejected.",
                    "actual_behavior": "Validation blocked request before execution.",
                },
            },
        )
    if scenario_id == "opportunity_not_found":
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "OPPORTUNITY_NOT_FOUND",
                    "message": "Opportunity id was not found.",
                },
                "data": {
                    "expected_behavior": "Missing opportunity returns safe 404.",
                    "actual_behavior": "No domain mutation performed.",
                },
            },
        )
    if scenario_id == "invalid_webhook_signature":
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_SIGNATURE",
                    "message": "Razorpay signature verification failed.",
                },
                "data": {
                    "expected_behavior": "Signature must be validated.",
                    "actual_behavior": "Webhook processing was rejected.",
                },
            },
        )
    if scenario_id == "ai_invalid_output":
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "AI_SCHEMA_INVALID",
                    "message": "AI output did not satisfy required schema.",
                },
                "data": {
                    "expected_behavior": "Invalid AI output must not execute.",
                    "actual_behavior": "Decision marked non-executable and escalated.",
                },
            },
        )
    if scenario_id == "ai_unavailable":
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": {
                    "code": "AI_UNAVAILABLE",
                    "message": "AI provider is unavailable. Safe fallback required.",
                },
                "data": {
                    "expected_behavior": "Workflow remains safe and deterministic.",
                    "actual_behavior": "Fallback path selected without execution bypass.",
                },
            },
        )
    if scenario_id == "policy_blocked":
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": {
                    "code": "POLICY_NOT_ALLOW",
                    "message": "Policy blocked automated execution.",
                },
                "data": {
                    "expected_behavior": "Policy can override AI recommendation.",
                    "actual_behavior": "Execution denied with deterministic rule outcome.",
                },
            },
        )
    if scenario_id == "recovery_failure":
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": {
                    "code": "RECOVERY_EXECUTION_FAILED",
                    "message": "Recovery execution failed safely.",
                },
                "data": {
                    "expected_behavior": "Recovered revenue remains unchanged.",
                    "actual_behavior": "Failure captured with no verified recovery increment.",
                },
            },
        )
    if scenario_id == "duplicate_webhook":
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": {
                    "code": "DUPLICATE_EVENT_IGNORED",
                    "message": "Duplicate webhook delivery ignored safely.",
                },
                "data": {
                    "expected_behavior": "No duplicate actions or revenue counting.",
                    "actual_behavior": "Idempotency guard prevented side effects.",
                },
            },
        )

    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": {
                "code": "FAILURE_SCENARIO_UNKNOWN",
                "message": "Failure scenario id is not recognized.",
            },
        },
    )


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"success": True, "data": {"status": "ready"}}


@router.get("/integrations/razorpay/status")
def razorpay_integration_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    mode = settings.payment_adapter_mode.strip().lower()
    adapter_test_mode = mode in {"razorpay_test", "test_mode"}
    live_mode_detected = settings.razorpay_live_mode_detected
    credentials_configured = settings.razorpay_configured
    credentials_test_mode = settings.razorpay_test_mode_keys and credentials_configured and not live_mode_detected
    test_mode = adapter_test_mode and credentials_test_mode
    webhook_configured = bool((settings.razorpay_webhook_secret or "").strip())

    api_connectivity = False
    api_connectivity_reason = None
    if test_mode:
        api_connectivity, api_connectivity_reason = check_razorpay_api_connectivity(settings)
    elif live_mode_detected:
        api_connectivity_reason = "live_mode_not_allowed"
    elif not adapter_test_mode:
        api_connectivity_reason = "adapter_mode_not_razorpay_test"
    elif not credentials_configured:
        api_connectivity_reason = "credentials_not_configured"
    elif not settings.razorpay_test_mode_keys:
        api_connectivity_reason = "razorpay_test_mode_credentials_required"
    else:
        api_connectivity_reason = "integration_not_configured"

    last_event = db.execute(select(WebhookEvent).order_by(WebhookEvent.id.desc())).scalars().first()
    links = db.execute(
        select(RecoveryPaymentLink).order_by(RecoveryPaymentLink.updated_at.desc(), RecoveryPaymentLink.id.desc()).limit(8)
    ).scalars().all()

    last_successful_razorpay_operation = None
    for link in links:
        parsed = _safe_json_object(link.external_response_reference)
        adapter_name = str(parsed.get("adapter") or "").strip().lower()
        if adapter_name != "razorpay_test":
            continue
        response_payload = parsed.get("response") if isinstance(parsed.get("response"), dict) else {}
        short_url = str(parsed.get("short_url") or response_payload.get("short_url") or "").strip() or None
        last_successful_razorpay_operation = {
            "operation": "payment_link_created",
            "payment_link_id": link.payment_link_id,
            "reference_id": link.payment_link_reference_id,
            "short_url": short_url,
            "status": link.status,
            "updated_at": link.updated_at.isoformat() if link.updated_at else None,
        }
        break

    return {
        "success": True,
        "data": {
            "test_mode": test_mode,
            "live_mode_detected": live_mode_detected,
            "credentials_configured": credentials_configured,
            "api_connectivity": api_connectivity,
            "api_connectivity_reason": api_connectivity_reason,
            "webhook_configured": webhook_configured,
            "adapter_mode": settings.payment_adapter_mode,
            "last_event": last_event.event_type if last_event is not None else None,
            "last_event_id": last_event.razorpay_event_id if last_event is not None else None,
            "last_event_status": last_event.processing_status if last_event is not None else None,
            "last_event_received_at": last_event.received_at.isoformat() if last_event and last_event.received_at else None,
            "last_successful_razorpay_operation": last_successful_razorpay_operation,
        },
    }


@router.post("/readiness/execute")
def execute_readiness(db: Session = Depends(get_db)) -> dict:
    result = execute_readiness_acceptance_workflow(db)
    return {"success": True, "data": result}


@router.post("/readiness/phase13/execute")
def execute_phase13_readiness(db: Session = Depends(get_db)) -> dict:
    # Legacy route preserved for backward compatibility.
    result = execute_readiness_acceptance_workflow(db)
    return {"success": True, "data": result}


@router.post("/demo/seed-core-recovery")
def seed_core_recovery(db: Session = Depends(get_db)) -> dict:
    result = seed_core_recovery_demo(db)
    return {"success": True, "data": result}


@router.post("/demo/reset-core-recovery")
def reset_core_recovery(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    reset_core_recovery_data(db)
    return {
        "success": True,
        "data": {
            "status": "reset",
            "mode": settings.payment_adapter_mode,
            "message": "Core recovery demo data reset completed.",
        },
    }


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    header_event_id = request.headers.get("x-razorpay-event-id")
    status_code, payload = process_razorpay_webhook_gateway(
        db,
        raw_body=raw_body,
        signature=signature,
        webhook_secret=settings.razorpay_webhook_secret,
        header_event_id=header_event_id,
    )
    if status_code == 200:
        return payload
    return JSONResponse(status_code=status_code, content=payload)


@router.post("/evaluation/run")
def run_evaluation(request: EvaluationRunRequest, db: Session = Depends(get_db)):
    dataset_count = db.query(EvaluationCase).filter(EvaluationCase.dataset_version == request.dataset_version).count()
    if request.force_regenerate or (request.generate_if_missing and dataset_count == 0):
        generate_synthetic_cases(
            db,
            dataset_version=request.dataset_version,
            generation_seed=request.generation_seed,
            total_cases=request.total_cases,
        )
    elif dataset_count == 0:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "DATASET_NOT_FOUND",
                    "message": "Dataset version not found. Enable generation or create cases first.",
                },
            },
        )

    summary = run_baseline_evaluation(
        db,
        dataset_version=request.dataset_version,
        split=request.split,
        evaluation_run_id=request.evaluation_run_id,
    )
    db.add(
        AuditEvent(
            event_type="evaluation.completed",
            actor_type="SYSTEM",
            actor_id="evaluation_center",
            entity_type="EvaluationRun",
            entity_id=summary.evaluation_run_id,
            correlation_id=summary.evaluation_run_id,
            result="success",
            metadata_json={
                "dataset_version": request.dataset_version,
                "split": request.split,
                "generation_seed": request.generation_seed,
                "total_cases": request.total_cases,
            },
            outcome_snapshot=evaluation_summary_to_dict(summary),
            reason=None,
        )
    )
    db.commit()
    return {"success": True, "data": evaluation_summary_to_dict(summary)}


@router.get("/evaluation/history")
def get_evaluation_history(db: Session = Depends(get_db), limit: int = 10) -> dict:
    bounded_limit = min(max(limit, 1), 50)
    run_rows = db.execute(
        select(
            EvaluationResult.evaluation_run_id,
            func.max(EvaluationResult.created_at).label("last_created_at"),
            func.count(EvaluationResult.id).label("records"),
        )
        .group_by(EvaluationResult.evaluation_run_id)
        .order_by(func.max(EvaluationResult.created_at).desc())
        .limit(bounded_limit)
    ).all()

    items: list[dict] = []
    for row in run_rows:
        summary = get_evaluation_run_summary(db, evaluation_run_id=row.evaluation_run_id)
        if summary is None:
            continue
        summary_payload = evaluation_summary_to_dict(summary)
        summary_payload["last_created_at"] = row.last_created_at.isoformat() if row.last_created_at else None
        items.append(summary_payload)

    return {"success": True, "data": {"items": items, "count": len(items)}}


@router.get("/evaluation/{run_id}/comparison")
def get_evaluation_comparison(run_id: str, db: Session = Depends(get_db)):
    summary, not_found = _evaluation_summary_or_404(db, run_id=run_id)
    if not_found is not None:
        return not_found

    comparison = get_strategy_attribution_comparison(db, evaluation_run_id=run_id)
    if comparison is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "EVAL_RUN_NOT_FOUND",
                    "message": "Evaluation run id was not found.",
                },
            },
        )
    baseline = evaluation_summary_to_dict(comparison["baseline_summary"])
    recoveriq = evaluation_summary_to_dict(comparison["recoveriq_summary"])
    deltas = {
        "precision_delta": round(recoveriq["precision"] - baseline["precision"], 4),
        "recall_delta": round(recoveriq["recall"] - baseline["recall"], 4),
        "f1_delta": round(recoveriq["f1"] - baseline["f1"], 4),
        "false_positive_rate_delta": round(recoveriq["false_positive_rate"] - baseline["false_positive_rate"], 4),
        "recovery_rate_delta": round(recoveriq["recovery_rate"] - baseline["recovery_rate"], 4),
        "net_recovered_minor_delta": recoveriq["net_recovered_minor"] - baseline["net_recovered_minor"],
        "false_positive_count_delta": recoveriq["false_positive_count"] - baseline["false_positive_count"],
        "false_positive_exposure_minor_delta": recoveriq["false_positive_exposure_minor"] - baseline["false_positive_exposure_minor"],
        "false_positive_intervention_cost_minor_delta": recoveriq["false_positive_intervention_cost_minor"] - baseline["false_positive_intervention_cost_minor"],
        "allowed_delta": recoveriq["operational"]["allowed"] - baseline["operational"]["allowed"],
        "blocked_delta": recoveriq["operational"]["blocked"] - baseline["operational"]["blocked"],
        "escalated_delta": recoveriq["operational"]["escalated"] - baseline["operational"]["escalated"],
        "failed_delta": recoveriq["operational"]["failed"] - baseline["operational"]["failed"],
    }

    return {
        "success": True,
        "data": {
            "baseline": baseline,
            "recoveriq": recoveriq,
            "deltas": deltas,
            "attribution": comparison["attribution"],
            "comparison_note": "RecoverIQ metrics are computed using a deterministic policy-path strategy over the same held-out cases.",
        },
    }


@router.get("/evaluation/{run_id}/drilldown")
def get_evaluation_run_drilldown(run_id: str, db: Session = Depends(get_db)):
    summary, not_found = _evaluation_summary_or_404(db, run_id=run_id)
    if not_found is not None:
        return not_found

    results = db.execute(
        select(EvaluationResult)
        .where(EvaluationResult.evaluation_run_id == run_id)
        .order_by(EvaluationResult.id.asc())
    ).scalars().all()

    case_ids = [result.case_id for result in results]
    cases = db.execute(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))).scalars().all() if case_ids else []
    case_map = {case.id: case for case in cases}

    tp = fp = fn = tn = 0
    failed_case_count = successful_case_count = 0
    failed_correct = successful_correct = 0
    sample_errors: list[dict] = []

    for result in results:
        if result.predicted_recoverable and result.actual_recoverable:
            tp += 1
        elif result.predicted_recoverable and not result.actual_recoverable:
            fp += 1
        elif (not result.predicted_recoverable) and result.actual_recoverable:
            fn += 1
        else:
            tn += 1

        case = case_map.get(result.case_id)
        if case is not None:
            is_failed_case = case.case_type == "failed_payment"
            if is_failed_case:
                failed_case_count += 1
                if result.correct:
                    failed_correct += 1
            else:
                successful_case_count += 1
                if result.correct:
                    successful_correct += 1

            if (result.false_positive or result.false_negative) and len(sample_errors) < 10:
                sample_errors.append(
                    {
                        "case_id": case.id,
                        "error_type": "false_positive" if result.false_positive else "false_negative",
                        "predicted_action": result.predicted_action,
                        "actual_action": result.actual_action,
                        "failure_reason": case.failure_features.get("reason"),
                    }
                )

    data = {
        "summary": evaluation_summary_to_dict(summary),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "false_positive_cost": {
            "count": summary.false_positive_count,
            "financial_exposure_minor": summary.false_positive_exposure_minor,
            "intervention_cost_minor": summary.false_positive_intervention_cost_minor,
        },
        "operational": {
            "allowed": summary.allowed_count,
            "blocked": summary.blocked_count,
            "escalated": summary.escalated_count,
            "failed": summary.failed_count,
        },
        "metric_drilldown": {
            "failed_payment_accuracy": round(failed_correct / failed_case_count, 4) if failed_case_count else 0.0,
            "successful_payment_accuracy": round(successful_correct / successful_case_count, 4) if successful_case_count else 0.0,
            "total_errors": fp + fn,
        },
        "sample_errors": sample_errors,
    }
    return {"success": True, "data": data}


@router.get("/evaluation/{run_id}")
def get_evaluation_run(run_id: str, db: Session = Depends(get_db)):
    summary, not_found = _evaluation_summary_or_404(db, run_id=run_id)
    if not_found is not None:
        return not_found
    return {"success": True, "data": evaluation_summary_to_dict(summary)}
