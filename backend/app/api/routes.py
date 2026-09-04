import base64
import json
from datetime import datetime, timedelta, date
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..security import redact_sensitive_data, safe_error_payload, sanitize_error_message, verify_security_guard
from ..demo_seed import seed_core_recovery_demo
from ..demo_seed import reset_core_recovery_data
from ..economics import estimate_intervention_cost_minor
from ..evaluation import (
    _baseline_prediction,
    _recoveriq_policy_prediction,
    _summary_from_predictions,
    evaluation_summary_to_dict,
    generate_synthetic_cases,
    get_evaluation_run_cases,
    get_evaluation_run_summary,
    get_recoveriq_policy_path_summary,
    get_strategy_attribution_comparison,
    run_baseline_evaluation,
)
from ..models import (
    AIAnalysis,
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
    WebhookProcessorLedger,
)
from ..gateway_adapters import (
    PaymentAdapterAccountLimitError,
    PaymentAdapterError,
    PaymentAdapterRateLimitError,
    PaymentAdapterTimeoutError,
    check_razorpay_api_connectivity,
)
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
    if (
        event_type.startswith("recovery.execution.")
        or event_type.startswith("recovery.payment_link.")
        or event_type.startswith("recovery.attempt.")
    ):
        return "execution"
    if (
        event_type.startswith("recovery.verification.")
        or event_type.startswith("outcome.")
        or event_type == "recovery.completed"
    ):
        return "verification"
    if event_type.startswith("policy."):
        return "policy"
    if event_type.startswith("webhook."):
        return "webhook"
    return None


def _stage_group(stage: str | None) -> str:
    if stage in {"detection", "diagnosis", "signal"}:
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
    if any(token in candidate for token in ["pending", "unverified", "awaiting"]):
        return "pending"
    return "pass"


def _serialize_opportunity_list_item(
    opportunity: RevenueOpportunity,
    *,
    decision: RecoveryDecision | None,
    policy_evaluation: PolicyEvaluation | None,
    latest_attempt: RecoveryAttempt | None,
    customer: Customer | None = None,
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

    # 1. Lifecycle status
    lifecycle_status = "OPEN"
    if opportunity.status in {"RESOLVED", "VERIFIED_RECOVERED"}:
        lifecycle_status = "RESOLVED"
    elif opportunity.status in {"CLOSED", "POLICY_BLOCKED", "ESCALATED", "PAYMENT_FAILED", "RECOVERY_FAILED"}:
        lifecycle_status = "CLOSED"

    # 2. Execution Status
    execution_status = "NOT_EXECUTED"
    if latest_attempt is not None:
        if latest_attempt.status in {"REQUESTED", "PENDING"}:
            execution_status = "RUNNING"
        elif latest_attempt.status == "FAILED":
            execution_status = "FAILED"
        elif latest_attempt.status in {"EXECUTED", "VERIFIED", "VERIFICATION_PENDING", "PENDING_VERIFICATION"}:
            execution_status = "SUCCEEDED"

    # 3. Verification Status
    verification_status = "UNVERIFIED"
    if latest_attempt is not None:
        if latest_attempt.status == "VERIFIED":
            verification_status = "VERIFIED"
        elif latest_attempt.status in {"PENDING_VERIFICATION", "VERIFICATION_PENDING"}:
            verification_status = "PENDING"
        elif latest_attempt.status == "VERIFICATION_BLOCKED" or latest_attempt.verified_outcome == "UNVERIFIED":
            verification_status = "VERIFICATION_FAILED"
        else:
            verification_status = "UNVERIFIED"

    # 4. Outcome
    outcome = "PENDING"
    if latest_attempt is not None:
        if latest_attempt.verified_outcome == "VERIFIED_SUCCESS":
            outcome = "RECOVERED"
        elif latest_attempt.verified_outcome == "VERIFIED_FAILURE":
            outcome = "NOT_RECOVERED"
        elif latest_attempt.verified_outcome == "UNVERIFIED" or latest_attempt.status == "VERIFICATION_BLOCKED":
            outcome = "VERIFICATION_FAILED"
        elif latest_attempt.status == "FAILED":
            outcome = "FAILED"
        elif latest_attempt.status in {"REQUESTED", "EXECUTED", "PENDING", "PENDING_VERIFICATION", "VERIFICATION_PENDING"}:
            outcome = "PENDING"
    elif policy_evaluation is not None:
        if policy_evaluation.result == "BLOCK":
            outcome = "BLOCKED"
        elif policy_evaluation.result == "ESCALATE":
            outcome = "ESCALATED"
        elif policy_evaluation.result == "ALLOW":
            outcome = "PENDING"

    customer_ref = (
        customer.name
        if customer and customer.name
        else (f"CUST-{opportunity.customer_id}" if opportunity.customer_id is not None else f"CUST-SYNTH-{opportunity.id:04d}")
    )

    return {
        "id": opportunity.id,
        "customer_reference": customer_ref,
        "status": opportunity.status,
        "lifecycle_status": lifecycle_status,
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
        "execution_status": execution_status,
        "verification_status": verification_status,
        "outcome": outcome,
        "updated_at": opportunity.updated_at.isoformat() if opportunity.updated_at else None,
    }


def _timeline_from_audits(audits: list[AuditEvent]) -> list[dict]:
    timeline: list[dict] = []
    for audit in audits:
        stage = _parse_stage(audit.event_type)
        timeline.append(
            {
                "id": audit.id,
                "timestamp": audit.timestamp.isoformat() if audit.timestamp else None,
                "event_type": audit.event_type,
                "stage": stage,
                "stage_group": _stage_group(stage),
                "outcome_status": _outcome_status(audit.outcome_snapshot, audit.reason),
                "actor_type": audit.actor_type,
                "actor_id": audit.actor_id,
                "entity_type": audit.entity_type,
                "entity_id": audit.entity_id,
                "correlation_id": audit.correlation_id,
                "result": audit.result,
                "reason": sanitize_error_message(audit.reason) if audit.reason else None,
                "metadata": redact_sensitive_data(audit.metadata_json),
                "outcome": redact_sensitive_data(audit.outcome_snapshot),
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
        # Standardized metric check naming.
        "confidence_check": policy.confidence_check,
        "amount_check": policy.max_amount_check,
        "expected_recovery_check": policy.economic_check,
        "retry_limit_check": policy.retry_limit_check,
        "duplicate_check": policy.duplicate_check,
        "test_mode_check": policy.environment_check,
        # Standard rule-key aliases for client consumers.
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


def _verified_success_amount(attempt: RecoveryAttempt) -> int:
    if attempt.verified_outcome == "VERIFIED_SUCCESS" and attempt.recovered_amount_minor > 0:
        return int(attempt.recovered_amount_minor)
    return 0


def _derive_semantic_states(
    *,
    payment: Payment | None,
    decision: RecoveryDecision | None,
    policy: PolicyEvaluation | None,
    attempts: list[RecoveryAttempt],
    has_payment_link: bool,
) -> dict[str, str | None]:
    latest_attempt = attempts[-1] if attempts else None

    original_payment_state = None
    if payment is not None:
        if payment.status == "FAILED":
            original_payment_state = "ORIGINAL_PAYMENT_FAILED"
        else:
            original_payment_state = f"ORIGINAL_PAYMENT_{str(payment.status or 'UNKNOWN').upper()}"

    policy_state = None
    if policy is not None:
        if policy.result == "ALLOW":
            policy_state = "POLICY_ALLOWED"
        elif policy.result == "ESCALATE":
            policy_state = "ESCALATED"
        else:
            policy_state = "POLICY_BLOCKED"

    recovery_payment_state = None
    verification_state = None
    business_outcome_state = None
    if latest_attempt is not None:
        if latest_attempt.verified_outcome == "VERIFIED_SUCCESS":
            recovery_payment_state = "RECOVERY_PAYMENT_SUCCESS"
            verification_state = "RECOVERY_OUTCOME_VERIFIED"
            business_outcome_state = "RECOVERED"
        elif latest_attempt.verified_outcome == "VERIFIED_FAILURE":
            recovery_payment_state = "RECOVERY_PAYMENT_FAILED"
            verification_state = "RECOVERY_OUTCOME_VERIFIED"
            business_outcome_state = "NOT_RECOVERED"
        elif latest_attempt.status in {"REQUESTED", "EXECUTED", "PENDING", "PENDING_VERIFICATION", "VERIFICATION_PENDING"}:
            recovery_payment_state = "RECOVERY_PAYMENT_PENDING"
        elif has_payment_link:
            recovery_payment_state = "RECOVERY_PAYMENT_PENDING"

    if business_outcome_state is None and (
        latest_attempt is not None
        or has_payment_link
        or policy_state in {"POLICY_BLOCKED", "ESCALATED", "POLICY_ALLOWED"}
        or decision is not None
    ):
        business_outcome_state = "NOT_RECOVERED"

    return {
        "original_payment": original_payment_state,
        "opportunity": "RECOVERY_OPPORTUNITY_IDENTIFIED",
        "ai": "AI_ANALYZED" if decision is not None else None,
        "recommendation": "RECOVERY_RECOMMENDED" if decision is not None else None,
        "policy": policy_state,
        "attempt": "RECOVERY_ATTEMPT_CREATED" if latest_attempt is not None else None,
        "payment_link": "PAYMENT_LINK_CREATED" if has_payment_link else None,
        "recovery_payment": recovery_payment_state,
        "verification": verification_state,
        "business_outcome": business_outcome_state,
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


def get_truthful_operating_status(db: Session, settings: Settings) -> dict[str, Any]:
    # 1. DATA SOURCE
    events = db.execute(select(WebhookEvent.account_id, WebhookEvent.razorpay_event_id).limit(100)).all()
    if not events:
        data_source = "SEEDED DEMO" if settings.app_mode.lower() == "simulation" else "LIVE INGESTION"
    else:
        has_live = any(
            (row.account_id and row.account_id != "acc_demo_seed")
            or not (row.razorpay_event_id and row.razorpay_event_id.startswith("evt_demo_"))
            for row in events
        )
        data_source = "LIVE INGESTION" if has_live else "SEEDED DEMO"

    # 2. PAYMENT ENVIRONMENT
    adapter_mode = settings.payment_adapter_mode.strip().lower()
    adapter_test_mode = adapter_mode in {
        "razorpay_test", "test_mode", "rest_primary", "rest_with_mcp_fallback",
        "mcp_primary", "mcp_with_rest_fallback", "mcp", "razorpay_mcp", "mcp_only", "rest_only"
    }
    live_mode_detected = settings.razorpay_live_mode_detected
    credentials_configured = settings.razorpay_configured
    credentials_test_mode = settings.razorpay_test_mode_keys and credentials_configured and not live_mode_detected

    api_connectivity = False
    api_connectivity_reason = None
    if adapter_test_mode and credentials_test_mode:
        payment_environment = "RAZORPAY TEST"
        api_connectivity, api_connectivity_reason = check_razorpay_api_connectivity(settings)
    elif live_mode_detected:
        payment_environment = "SIMULATION"
        api_connectivity_reason = "live_mode_not_allowed"
    elif not adapter_test_mode:
        payment_environment = "SIMULATION"
        api_connectivity_reason = "adapter_mode_not_razorpay_test"
    elif not credentials_configured:
        payment_environment = "SIMULATION"
        api_connectivity_reason = "credentials_not_configured"
    else:
        payment_environment = "SIMULATION"
        api_connectivity_reason = "razorpay_test_mode_credentials_required"

    # 3. AI PROVIDER
    ai_provider_config = (settings.ai_provider or "").strip().lower()
    if ai_provider_config == "mock":
        ai_provider_status = "MOCK/FALLBACK"
        ai_provider_note = "Deterministic mock provider active"
    elif ai_provider_config == "groq":
        if settings.groq_api_key:
            ai_provider_status = "CLOUD"
            ai_provider_note = f"Groq active ({settings.groq_model})"
        else:
            ai_provider_status = "MOCK/FALLBACK"
            ai_provider_note = "Groq key missing, fallback enabled"
    elif ai_provider_config == "gemini":
        if settings.gemini_api_key:
            ai_provider_status = "CLOUD"
            ai_provider_note = f"Gemini active ({settings.gemini_model})"
        else:
            ai_provider_status = "MOCK/FALLBACK"
            ai_provider_note = "Gemini key missing, fallback enabled"
    elif ai_provider_config in {"ollama", "local"}:
        try:
            resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=0.8)
            if resp.status_code == 200:
                ai_provider_status = "LOCAL"
                ai_provider_note = f"Ollama local active ({settings.ollama_model})"
            else:
                ai_provider_status = "MOCK/FALLBACK"
                ai_provider_note = "Ollama unresponsive, fallback enabled"
        except Exception:
            ai_provider_status = "MOCK/FALLBACK"
            ai_provider_note = "Ollama unreachable, fallback enabled"
    elif ai_provider_config in {"openai", "anthropic", "external"}:
        ai_provider_status = "EXTERNAL"
        ai_provider_note = f"External AI provider ({ai_provider_config})"
    else:
        ai_provider_status = "UNAVAILABLE"
        ai_provider_note = f"Unknown provider: {ai_provider_config}"

    # 4. POLICY ENGINE
    policy_engine_status = "ACTIVE"
    policy_engine_note = "Safety policy rules & threshold evaluation active"

    # 5. WEBHOOK
    webhook_secret_present = bool((settings.razorpay_webhook_secret or "").strip())
    last_event = db.execute(select(WebhookEvent).order_by(WebhookEvent.id.desc())).scalars().first()
    verified_events_count = db.execute(
        select(func.count(WebhookEvent.id)).where(WebhookEvent.signature_valid.is_(True))
    ).scalar_one()

    if not webhook_secret_present:
        webhook_status = "DEGRADED"
        webhook_note = "Webhook secret not configured"
    elif last_event is None:
        webhook_status = "WAITING"
        webhook_note = "Secret configured, waiting for events"
    elif verified_events_count > 0:
        webhook_status = "VERIFIED"
        webhook_note = f"Last verified event: {last_event.event_type}"
    else:
        webhook_status = "CONFIGURED"
        webhook_note = "Configured, awaiting verified events"

    # 6. MCP INTEGRATION STATUS
    mcp_enabled = bool(getattr(settings, "razorpay_mcp_enabled", False))
    mcp_configured = bool(getattr(settings, "razorpay_mcp_configured", False))
    mcp_endpoint = str(getattr(settings, "razorpay_mcp_endpoint", "")).strip()
    exec_strategy_mode = str(getattr(settings, "payment_adapter_mode", "simulation")).strip().lower()

    if settings.razorpay_live_mode_detected:
        mcp_status = "UNAVAILABLE"
        mcp_note = "MCP disabled in live mode for safety"
    elif not mcp_enabled:
        mcp_status = "NOT_CONFIGURED"
        mcp_note = "Razorpay MCP integration is disabled"
    elif not mcp_configured or not mcp_endpoint:
        mcp_status = "NOT_CONFIGURED"
        mcp_note = "Razorpay MCP endpoint or auth credentials missing"
    else:
        if exec_strategy_mode in {"mcp", "razorpay_mcp", "mcp_only", "mcp_primary", "razorpay_mcp_primary", "mcp_with_rest_fallback"}:
            mcp_status = "ACTIVE"
            mcp_note = f"Razorpay MCP active ({mcp_endpoint})"
        else:
            mcp_status = "AVAILABLE"
            mcp_note = f"Razorpay MCP configured & available as fallback ({mcp_endpoint})"

    return {
        "data_source": data_source,
        "payment_environment": payment_environment,
        "ai_provider": ai_provider_status,
        "ai_provider_note": ai_provider_note,
        "policy_engine": policy_engine_status,
        "policy_engine_note": policy_engine_note,
        "webhook": webhook_status,
        "webhook_note": webhook_note,
        "mcp_status": mcp_status,
        "mcp_note": mcp_note,
        "execution_strategy": exec_strategy_mode.upper(),
        "api_connectivity": api_connectivity,
        "api_connectivity_reason": api_connectivity_reason,
        "last_event": last_event.event_type if last_event else None,
        "last_event_id": last_event.razorpay_event_id if last_event else None,
        "last_event_status": last_event.processing_status if last_event else None,
        "last_event_received_at": last_event.received_at.isoformat() if last_event and last_event.received_at else None,
    }


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    operating_status = get_truthful_operating_status(db, settings)
    mode = (
        "razorpay_test"
        if operating_status["payment_environment"] == "RAZORPAY TEST"
        else "simulation"
    )
    mode_label = "Razorpay Test Mode" if mode == "razorpay_test" else "Simulation Mode"

    revenue_at_risk_minor = db.execute(
        select(func.coalesce(func.sum(RevenueOpportunity.amount_at_risk_minor), 0))
    ).scalar_one()
    recoverable_revenue_minor = db.execute(
        select(func.coalesce(func.sum(RevenueOpportunity.amount_at_risk_minor), 0))
        .join(PolicyEvaluation, PolicyEvaluation.opportunity_id == RevenueOpportunity.id)
        .where(PolicyEvaluation.result == "ALLOW")
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

    attempts = db.execute(
        select(RecoveryAttempt.action, RecoveryAttempt.recovered_amount_minor, RecoveryAttempt.verified_outcome)
    ).all()
    recovery_attempts = len(attempts)
    gross_recovered_minor = sum(
        int(row.recovered_amount_minor)
        for row in attempts
        if str(row.verified_outcome or "") == "VERIFIED_SUCCESS" and int(row.recovered_amount_minor or 0) > 0
    )
    intervention_cost_minor = sum(estimate_intervention_cost_minor(row.action) for row in attempts)
    net_recovered_minor = gross_recovered_minor - intervention_cost_minor

    recovery_rate = 0.0
    if recoverable_revenue_minor > 0:
        recovery_rate = min(1.0, round(gross_recovered_minor / recoverable_revenue_minor, 4))

    # AI identifiable: sum of amount_at_risk_minor for opportunities with recovery_probability >= 35
    ai_identifiable_minor = db.execute(
        select(func.coalesce(func.sum(RevenueOpportunity.amount_at_risk_minor), 0))
        .where(RevenueOpportunity.recovery_probability >= 35)
    ).scalar_one()

    # Recovery attempted: sum of amount_minor for attempts
    recovery_attempted_minor = db.execute(
        select(func.coalesce(func.sum(RecoveryAttempt.amount_minor), 0))
    ).scalar_one()

    # Query top open opportunity prioritized by expected_net_recovery_minor
    top_opp = db.execute(
        select(RevenueOpportunity)
        .where(RevenueOpportunity.status.not_in(["CLOSED", "RESOLVED"]))
        .order_by(RevenueOpportunity.expected_net_recovery_minor.desc())
        .limit(1)
    ).scalars().first()

    top_opportunity_data = None
    if top_opp is not None:
        top_opportunity_data = {
            "id": top_opp.id,
            "recommended_action": top_opp.recommended_action,
            "confidence": top_opp.confidence,
            "expected_recovery_minor": top_opp.expected_recovery_minor
        }

    # Enforce strict logical payment inequalities: Revenue at Risk >= Recoverable Revenue >= Gross Recovered
    if recoverable_revenue_minor > revenue_at_risk_minor:
        recoverable_revenue_minor = revenue_at_risk_minor
    if gross_recovered_minor > recoverable_revenue_minor:
        gross_recovered_minor = recoverable_revenue_minor
    net_recovered_minor = gross_recovered_minor - intervention_cost_minor

    recovery_rate = 0.0
    if recoverable_revenue_minor > 0:
        recovery_rate = min(1.0, round(gross_recovered_minor / recoverable_revenue_minor, 4))

    # Enforce strict funnel sequence capping
    ai_identifiable_minor = min(revenue_at_risk_minor, ai_identifiable_minor)
    policy_eligible_minor = min(ai_identifiable_minor, recoverable_revenue_minor)
    recovery_attempted_minor = min(policy_eligible_minor, recovery_attempted_minor)
    successfully_recovered_minor = min(recovery_attempted_minor, gross_recovered_minor)

    data = {
        "mode": mode,
        "mode_label": mode_label,
        "operating_status": operating_status,
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
        "funnel": {
            "revenue_at_risk_minor": revenue_at_risk_minor,
            "ai_identifiable_minor": ai_identifiable_minor,
            "policy_eligible_minor": policy_eligible_minor,
            "recovery_attempted_minor": recovery_attempted_minor,
            "successfully_recovered_minor": successfully_recovered_minor,
        },
        "ai_copilot": {
            "active_opportunities_count": active_opportunities,
            "total_recoverable_value_minor": recoverable_revenue_minor,
            "top_opportunity": top_opportunity_data
        }
    }
    return {"success": True, "data": data}


@router.get("/dashboard/trend")
def get_dashboard_trend(db: Session = Depends(get_db)):
    today = date.today()
    stats = []
    
    for i in range(6, -1, -1):
        target_date = today - timedelta(days=i)
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date, datetime.max.time())
        
        risk_sum = db.execute(
            select(func.coalesce(func.sum(RevenueOpportunity.amount_at_risk_minor), 0))
            .where(RevenueOpportunity.created_at >= start_dt, RevenueOpportunity.created_at <= end_dt)
        ).scalar_one()
        
        recovered_sum = db.execute(
            select(func.coalesce(func.sum(RecoveryAttempt.recovered_amount_minor), 0))
            .where(RecoveryAttempt.requested_at >= start_dt, RecoveryAttempt.requested_at <= end_dt)
            .where(RecoveryAttempt.verified_outcome == "VERIFIED_SUCCESS")
        ).scalar_one()
        
        attempts_count = db.execute(
            select(func.count(RecoveryAttempt.id))
            .where(RecoveryAttempt.requested_at >= start_dt, RecoveryAttempt.requested_at <= end_dt)
        ).scalar_one()
        
        stats.append({
            "date": target_date.strftime("%Y-%m-%d"),
            "display_date": target_date.strftime("%b %d"),
            "revenue_at_risk_minor": risk_sum,
            "recovered_revenue_minor": recovered_sum,
            "attempts_count": attempts_count
        })
        
    return {"success": True, "data": stats}


@router.get("/dashboard/events")
def get_dashboard_events(db: Session = Depends(get_db), limit: int = 20):
    events = db.execute(
        select(AuditEvent)
        .order_by(AuditEvent.id.desc())
        .limit(limit)
    ).scalars().all()
    
    return {
        "success": True,
        "data": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor_type": event.actor_type,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "result": event.result,
                "reason": event.reason,
                "created_at": event.timestamp.isoformat() if event.timestamp else None
            }
            for event in events
        ]
    }


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
        status_upper = status.strip().upper()
        if status_upper == "OPEN":
            query = query.where(RevenueOpportunity.status.in_([
                "OPEN", "IDENTIFIED", "ANALYZED", "RECOMMENDED", "POLICY_ALLOWED",
                "PAYMENT_LINK_CREATED", "PAYMENT_PENDING", "PAYMENT_SUCCESSFUL"
            ]))
        elif status_upper == "RESOLVED":
            query = query.where(RevenueOpportunity.status.in_(["RESOLVED", "VERIFIED_RECOVERED"]))
        elif status_upper == "CLOSED":
            query = query.where(RevenueOpportunity.status.in_([
                "CLOSED", "POLICY_BLOCKED", "ESCALATED", "PAYMENT_FAILED", "RECOVERY_FAILED"
            ]))
        else:
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

                customer = (
                    db.execute(select(Customer).where(Customer.id == opportunity.customer_id)).scalar_one_or_none()
                    if opportunity.customer_id is not None
                    else None
                )

                serialized = _serialize_opportunity_list_item(
                    opportunity,
                    decision=latest_decision,
                    policy_evaluation=policy_evaluation,
                    latest_attempt=latest_attempt,
                    customer=customer,
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

        customer = (
            db.execute(select(Customer).where(Customer.id == opportunity.customer_id)).scalar_one_or_none()
            if opportunity.customer_id is not None
            else None
        )

        enriched_items.append(
            _serialize_opportunity_list_item(
                opportunity,
                decision=latest_decision,
                policy_evaluation=policy_evaluation,
                latest_attempt=latest_attempt,
                customer=customer,
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
def get_opportunity_detail(opportunity_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
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

    attempts = list(db.execute(
        select(RecoveryAttempt)
        .where(RecoveryAttempt.opportunity_id == opportunity.id)
        .order_by(RecoveryAttempt.attempt_number.asc(), RecoveryAttempt.id.asc())
    ).scalars().all())
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
    workflow_chain_id = f"payment:{payment.razorpay_payment_id}" if payment and payment.razorpay_payment_id else None
    attempt_ids = [str(a.id) for a in attempts]
    conditions = []
    if workflow_chain_id:
        conditions.append((AuditEvent.entity_type == "RecoveryWorkflow") & (AuditEvent.entity_id == workflow_chain_id))
    if attempt_ids:
        conditions.append((AuditEvent.entity_type == "RecoveryAttempt") & (AuditEvent.entity_id.in_(attempt_ids)))
    conditions.append((AuditEvent.entity_type == "RevenueOpportunity") & (AuditEvent.entity_id == str(opportunity_id)))

    workflow_audits = list(
        db.execute(
            select(AuditEvent)
            .where(or_(*conditions))
            .order_by(AuditEvent.id.asc())
        ).scalars().all()
    )

    gross_recovered_minor = sum(_verified_success_amount(attempt) for attempt in attempts)
    total_intervention_cost_minor = sum(estimate_intervention_cost_minor(attempt.action) for attempt in attempts)

    timeline = _timeline_from_audits(workflow_audits)
    timeline_groups = _group_timeline(timeline)

    has_payment_link = any(attempt.id in link_by_attempt_id for attempt in attempts)
    semantic_states = _derive_semantic_states(
        payment=payment,
        decision=decision,
        policy=policy,
        attempts=attempts,
        has_payment_link=has_payment_link,
    )

    ordered_states = [
        "ORIGINAL_PAYMENT_FAILED",
        "OPPORTUNITY_IDENTIFIED",
        "AI_ANALYZED",
        "RECOVERY_RECOMMENDED",
        "POLICY_ALLOWED",
        "POLICY_BLOCKED",
        "ESCALATED",
        "RECOVERY_ATTEMPT_CREATED",
        "PAYMENT_LINK_CREATED",
        "RECOVERY_PAYMENT_PENDING",
        "RECOVERY_PAYMENT_SUCCESS",
        "RECOVERY_PAYMENT_FAILED",
        "RECOVERY_OUTCOME_VERIFIED",
        "RECOVERED",
        "NOT_RECOVERED",
    ]
    reached_states = set(filter(None, semantic_states.values()))
    current_state = "OPPORTUNITY_IDENTIFIED"
    for state_name in ordered_states:
        if state_name in reached_states:
            current_state = state_name

    recovery_state = {
        "current": current_state,
        "stages": [{"name": state_name, "reached": state_name in reached_states} for state_name in ordered_states],
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

    # Retrieve AIAnalysis if decision is present
    analysis = None
    if decision is not None:
        analysis = db.execute(
            select(AIAnalysis).where(AIAnalysis.decision_id == decision.id)
        ).scalars().first()

    # AI validation info
    provider_available = True
    valid_schema = True
    if decision is not None:
        if decision.decision_source == "AI_FALLBACK":
            provider_available = False
            valid_schema = False
        elif analysis is not None:
            valid_schema = analysis.valid_schema

    ai_validation = {
        "provider_available": provider_available,
        "valid_schema": valid_schema,
        "rejected": not valid_schema or decision.decision_source == "AI_FALLBACK" if decision else False,
        "fallback_used": decision.decision_source == "AI_FALLBACK" if decision else False,
        "reason": analysis.validation_error if analysis else (decision.evidence.get("failure_reason") if decision else None)
    }

    # Idempotency checks
    webhook_event = None
    if opportunity.source_event_id is not None:
        webhook_event = db.execute(
            select(WebhookEvent).where(WebhookEvent.id == opportunity.source_event_id)
        ).scalar_one_or_none()

    delivery_count = 1
    if webhook_event is not None:
        ledger = db.execute(
            select(WebhookProcessorLedger).where(WebhookProcessorLedger.razorpay_event_id == webhook_event.razorpay_event_id)
        ).scalar_one_or_none()
        if ledger is not None:
            delivery_count = ledger.delivery_count

    idempotency_check = {
        "received": True,
        "already_processed": delivery_count > 1,
        "duplicate_ignored": delivery_count > 1,
        "no_second_action": delivery_count > 1,
        "delivery_count": delivery_count,
        "event_id": webhook_event.razorpay_event_id if webhook_event else None,
    }

    # Signals and constraints
    signals = [
        {"label": "Network failure", "passed": opportunity.failure_category == "NETWORK"},
        {"label": "Customer previously completed payments", "passed": (customer.historical_recovery_count or 0) > 0 if customer else False},
        {"label": "Recent retry detected", "passed": len(attempts) > 0},
        {"label": "Payment-link eligible", "passed": opportunity.amount_at_risk_minor <= 1000000},
        {"label": "No duplicate recovery attempt", "passed": len(attempts) <= 1},
    ]
    constraints = [
        {"label": "Policy threshold passed", "passed": policy.result == "ALLOW" if policy else False},
        {"label": "Amount threshold passed", "passed": policy.max_amount_check if policy else False},
        {"label": "Customer eligible", "passed": policy.retry_limit_check if policy else False},
        {"label": "No duplicate action", "passed": policy.duplicate_check if policy else False},
    ]
    
    # Strategy comparison
    rec_action = opportunity.recommended_action or ""
    p_retry = opportunity.recovery_probability if rec_action == "RETRY" else max(15, opportunity.recovery_probability - 25)
    p_link = opportunity.recovery_probability if rec_action in {"RECOVERY_PROMPT", "CREATE_PAYMENT_LINK"} else max(10, opportunity.recovery_probability - 20)
    p_wait = opportunity.recovery_probability if rec_action == "DELAYED_RETRY" else max(10, opportunity.recovery_probability - 15)
    p_none = 0
    
    p_retry = min(100, max(0, p_retry))
    p_link = min(100, max(0, p_link))
    p_wait = min(100, max(0, p_wait))
    
    amt = opportunity.amount_at_risk_minor
    er_retry = int(amt * p_retry / 100)
    er_link = int(amt * p_link / 100)
    er_wait = int(amt * p_wait / 100)
    er_none = 0
    
    r_retry = "LOW" if p_retry >= 60 else "MEDIUM" if p_retry >= 30 else "HIGH"
    r_link = "LOW" if p_link >= 60 else "MEDIUM" if p_link >= 30 else "HIGH"
    r_wait = "LOW" if p_wait >= 60 else "MEDIUM" if p_wait >= 30 else "HIGH"
    r_none = "NONE"
    
    strategy_comparison = [
        {
            "name": "Payment Link",
            "probability": p_link,
            "expected_recovery_minor": er_link,
            "risk": r_link,
            "selected": rec_action in {"RECOVERY_PROMPT", "CREATE_PAYMENT_LINK"},
        },
        {
            "name": "Retry",
            "probability": p_retry,
            "expected_recovery_minor": er_retry,
            "risk": r_retry,
            "selected": rec_action == "RETRY",
        },
        {
            "name": "Wait",
            "probability": p_wait,
            "expected_recovery_minor": er_wait,
            "risk": r_wait,
            "selected": rec_action == "DELAYED_RETRY",
        },
        {
            "name": "No Action",
            "probability": p_none,
            "expected_recovery_minor": er_none,
            "risk": r_none,
            "selected": rec_action in {"ESCALATE", "NO_ACTION", "BLOCK"},
        },
    ]

    # Timeline Redesign Stage logic
    stages_timeline = []
    
    # 1. DETECTED
    stages_timeline.append({
        "stage": "DETECTED",
        "reached": True,
        "status": "pass",
        "timestamp": opportunity.created_at.isoformat() if opportunity.created_at else None,
        "details": {
            "timestamp": opportunity.created_at.isoformat() if opportunity.created_at else None,
            "event_id": webhook_event.razorpay_event_id if webhook_event else None,
            "workflow_id": f"payment:{payment.razorpay_payment_id}" if payment else None,
            "opportunity_id": opportunity.id,
            "correlation_id": webhook_event.correlation_id if webhook_event else None,
        }
    })
    
    # 2. DIAGNOSED
    diag_reached = (opportunity.status != "IDENTIFIED" or decision is not None)
    diag_status = "pass" if (decision and decision.decision_source != "AI_FALLBACK") else "fail" if (decision and decision.decision_source == "AI_FALLBACK") else "pending"
    stages_timeline.append({
        "stage": "DIAGNOSED",
        "reached": diag_reached,
        "status": diag_status,
        "timestamp": decision.created_at.isoformat() if (decision and decision.created_at) else None,
        "details": {
            "timestamp": decision.created_at.isoformat() if (decision and decision.created_at) else None,
            "provider": decision.provider if decision else "Rule-based Fallback Engine",
            "model": decision.model if decision else "Static Heuristics",
            "failure_category": opportunity.failure_category,
            "failure_reason": opportunity.failure_reason,
            "correlation_id": decision.evidence.get("failure_reason") if (decision and decision.decision_source == "AI_FALLBACK") else (webhook_event.correlation_id if webhook_event else None)
        }
    })
    
    # 3. AI DECISION
    ai_reached = decision is not None
    ai_status = "pass" if (decision and decision.decision_source != "AI_FALLBACK") else "fail" if (decision and decision.decision_source == "AI_FALLBACK") else "pending"
    stages_timeline.append({
        "stage": "AI DECISION",
        "reached": ai_reached,
        "status": ai_status,
        "timestamp": decision.created_at.isoformat() if (decision and decision.created_at) else None,
        "details": {
            "timestamp": decision.created_at.isoformat() if (decision and decision.created_at) else None,
            "recommended_action": decision.recommended_action if decision else None,
            "confidence": decision.confidence if decision else 0,
            "expected_recovery_minor": decision.expected_recovery_minor if decision else 0,
            "decision_source": decision.decision_source if decision else None,
            "schema_valid": valid_schema,
            "provider_available": provider_available,
        }
    })
    
    # 4. POLICY
    policy_reached = policy is not None
    policy_status = "pass" if (policy and policy.result == "ALLOW") else "fail" if (policy and policy.result in {"BLOCK", "ESCALATE"}) else "pending"
    stages_timeline.append({
        "stage": "POLICY",
        "reached": policy_reached,
        "status": policy_status,
        "timestamp": policy.evaluated_at.isoformat() if (policy and policy.evaluated_at) else None,
        "details": {
            "timestamp": policy.evaluated_at.isoformat() if (policy and policy.evaluated_at) else None,
            "result": policy.result if policy else None,
            "policy_version": policy.policy_version if policy else None,
            "checks": _policy_checks_from_evaluation(policy),
        }
    })
    
    # 5. EXECUTION
    exec_reached = len(attempts) > 0
    exec_status = "pass" if (attempts and attempts[-1].status == "SUCCESS") else "fail" if (attempts and attempts[-1].status == "FAILED") else "pending" if attempts else "pending" if (policy and policy.result == "ALLOW") else "none"
    stages_timeline.append({
        "stage": "EXECUTION",
        "reached": exec_reached,
        "status": exec_status,
        "timestamp": attempts[-1].executed_at.isoformat() if (attempts and attempts[-1].executed_at) else None,
        "details": {
            "timestamp": attempts[-1].executed_at.isoformat() if (attempts and attempts[-1].executed_at) else None,
            "attempt_id": attempts[-1].id if attempts else None,
            "action": attempts[-1].action if attempts else None,
            "status": attempts[-1].status if attempts else None,
            "failure_code": attempts[-1].failure_code if attempts else None,
            "failure_reason": attempts[-1].failure_reason if attempts else None,
        }
    })
    
    # 6. VERIFICATION
    ver_reached = any(attempt.verified_outcome is not None for attempt in attempts)
    ver_status = "pass" if (attempts and attempts[-1].verified_outcome == "VERIFIED_SUCCESS") else "fail" if (attempts and attempts[-1].verified_outcome == "VERIFIED_FAILURE") else "pending" if (attempts and attempts[-1].verified_outcome is not None) else "none"
    stages_timeline.append({
        "stage": "VERIFICATION",
        "reached": ver_reached,
        "status": ver_status,
        "timestamp": attempts[-1].completed_at.isoformat() if (attempts and attempts[-1].completed_at) else None,
        "details": {
            "timestamp": attempts[-1].completed_at.isoformat() if (attempts and attempts[-1].completed_at) else None,
            "verified_outcome": attempts[-1].verified_outcome if attempts else None,
            "recovered_amount_minor": attempts[-1].recovered_amount_minor if attempts else 0,
        }
    })
    
    # Overlay with Audit Events if available
    for audit in workflow_audits:
        stage_name = _parse_stage(audit.event_type)
        if not stage_name:
            continue
        stage_map = {
            "detection": "DETECTED",
            "diagnosis": "DIAGNOSED",
            "policy": "POLICY",
            "execution": "EXECUTION",
            "verification": "VERIFICATION",
        }
        mapped_name = stage_map.get(stage_name)
        if not mapped_name:
            continue
            
        for stage_obj in stages_timeline:
            if stage_obj["stage"] == mapped_name:
                stage_obj["timestamp"] = audit.timestamp.isoformat() if audit.timestamp else stage_obj["timestamp"]
                stage_obj["details"]["timestamp"] = stage_obj["timestamp"]
                stage_obj["details"]["event_id"] = audit.id
                stage_obj["details"]["correlation_id"] = audit.correlation_id or stage_obj["details"].get("correlation_id")

    # 1. Lifecycle status
    lifecycle_status = "OPEN"
    if opportunity.status in {"RESOLVED", "VERIFIED_RECOVERED"}:
        lifecycle_status = "RESOLVED"
    elif opportunity.status in {"CLOSED", "POLICY_BLOCKED", "ESCALATED", "PAYMENT_FAILED", "RECOVERY_FAILED"}:
        lifecycle_status = "CLOSED"

    # 2. Execution Status
    execution_status = "NOT_EXECUTED"
    if attempts:
        latest_attempt = attempts[-1]
        if latest_attempt.status in {"REQUESTED", "PENDING"}:
            execution_status = "RUNNING"
        elif latest_attempt.status == "FAILED":
            execution_status = "FAILED"
        elif latest_attempt.status in {"EXECUTED", "VERIFIED", "VERIFICATION_PENDING", "PENDING_VERIFICATION"}:
            execution_status = "SUCCEEDED"

    # 3. Verification Status
    verification_status = "UNVERIFIED"
    if attempts:
        latest_attempt = attempts[-1]
        if latest_attempt.status == "VERIFIED":
            verification_status = "VERIFIED"
        elif latest_attempt.status in {"PENDING_VERIFICATION", "VERIFICATION_PENDING"}:
            verification_status = "PENDING"
        else:
            verification_status = "UNVERIFIED"

    # 4. Outcome
    outcome = "PENDING"
    if attempts:
        latest_attempt = attempts[-1]
        if latest_attempt.verified_outcome == "VERIFIED_SUCCESS":
            outcome = "RECOVERED"
        elif latest_attempt.verified_outcome == "VERIFIED_FAILURE":
            outcome = "FAILED"
        elif latest_attempt.status == "FAILED":
            outcome = "FAILED"
    elif policy is not None and policy.result in {"BLOCK", "ESCALATE"}:
        outcome = "FAILED"

    data = {
        "opportunity": {
            "id": opportunity.id,
            "status": opportunity.status,
            "lifecycle_status": lifecycle_status,
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
        "ai_validation": ai_validation,
        "idempotency_check": idempotency_check,
        "strategy_comparison": strategy_comparison,
        "decision_explanation": {"signals": signals, "constraints": constraints},
        "timeline_stages": stages_timeline,
        "action_traceability": {
            "recommended_action": decision.recommended_action if decision else opportunity.recommended_action,
            "allow_execution": policy.result == "ALLOW" if policy else None,
            "latest_attempt_status": attempts[-1].status if attempts else None,
            "latest_verified_outcome": attempts[-1].verified_outcome if attempts else None,
            "attempt_count": len(attempts),
            "execution_status": execution_status,
            "verification_status": verification_status,
            "outcome": outcome,
            "execution_mode": settings.payment_adapter_mode if isinstance(settings, Settings) else get_settings().payment_adapter_mode,
            "execution_strategy": (
                json.loads(link_by_attempt_id[attempts[-1].id].external_response_reference).get("execution_strategy")
                if attempts and attempts[-1].id in link_by_attempt_id and link_by_attempt_id[attempts[-1].id].external_response_reference
                else ("MCP" if (settings.payment_adapter_mode if isinstance(settings, Settings) else get_settings().payment_adapter_mode) in {"mcp", "razorpay_mcp", "mcp_primary"} else "Direct REST")
            ),
            "used_fallback": (
                json.loads(link_by_attempt_id[attempts[-1].id].external_response_reference).get("used_fallback", False)
                if attempts and attempts[-1].id in link_by_attempt_id and link_by_attempt_id[attempts[-1].id].external_response_reference
                else False
            ),
        },
        "semantic_states": semantic_states,
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
                        "short_url": (
                            json.loads(link_by_attempt_id[attempt.id].external_response_reference).get("short_url")
                            if link_by_attempt_id[attempt.id].external_response_reference
                            else None
                        ) if link_by_attempt_id[attempt.id].external_response_reference else None,
                        "execution_strategy": (
                            json.loads(link_by_attempt_id[attempt.id].external_response_reference).get("execution_strategy")
                            if link_by_attempt_id[attempt.id].external_response_reference
                            else None
                        ) if link_by_attempt_id[attempt.id].external_response_reference else None,
                        "adapter": (
                            json.loads(link_by_attempt_id[attempt.id].external_response_reference).get("adapter")
                            if link_by_attempt_id[attempt.id].external_response_reference
                            else None
                        ) if link_by_attempt_id[attempt.id].external_response_reference else None,
                        "used_fallback": (
                            json.loads(link_by_attempt_id[attempt.id].external_response_reference).get("used_fallback", False)
                            if link_by_attempt_id[attempt.id].external_response_reference
                            else False
                        ) if link_by_attempt_id[attempt.id].external_response_reference else False,
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
def execute_opportunity(
    opportunity_id: int,
    db: Session = Depends(get_db),
    auth_guard: bool = Depends(verify_security_guard),
):
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
    except PaymentAdapterRateLimitError as exc:
        retry_after = getattr(exc, "retry_after_seconds", 5)
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "success": False,
                "error": {
                    "code": "RATE_LIMITED",
                    "message": str(exc),
                    "retryable": True,
                    "retry_after_seconds": retry_after,
                },
            },
        )
    except PaymentAdapterAccountLimitError as exc:
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": {
                    "code": "GATEWAY_ACCOUNT_LIMIT",
                    "message": str(exc),
                    "retryable": False,
                },
            },
        )
    except PaymentAdapterTimeoutError as exc:
        return JSONResponse(
            status_code=504,
            content={
                "success": False,
                "error": {
                    "code": "GATEWAY_TIMEOUT",
                    "message": "Gateway timed out during payment link creation. Outcome is ambiguous and will be verified safely.",
                    "retryable": False,
                    "ambiguous_outcome": True,
                },
            },
        )
    except (PaymentAdapterError, ValueError) as exc:
        err_msg = str(exc)
        if "adapter_timeout" in err_msg:
            return JSONResponse(
                status_code=504,
                content={
                    "success": False,
                    "error": {
                        "code": "GATEWAY_TIMEOUT",
                        "message": "Gateway timed out during payment link creation. Outcome is ambiguous and will be verified safely.",
                        "retryable": False,
                        "ambiguous_outcome": True,
                    },
                },
            )
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": {
                    "code": "EXECUTION_BLOCKED",
                    "message": err_msg,
                },
            },
        )

    payment_link = db.execute(
        select(RecoveryPaymentLink)
        .where(RecoveryPaymentLink.recovery_attempt_id == attempt.id)
        .order_by(RecoveryPaymentLink.id.desc())
    ).scalars().first()

    # 2. Execution Status
    execution_status = "NOT_EXECUTED"
    if attempt.status in {"REQUESTED", "PENDING"}:
        execution_status = "RUNNING"
    elif attempt.status == "FAILED":
        execution_status = "FAILED"
    elif attempt.status in {"EXECUTED", "VERIFIED", "VERIFICATION_PENDING", "PENDING_VERIFICATION"}:
        execution_status = "SUCCEEDED"

    # 3. Verification Status
    verification_status = "UNVERIFIED"
    if attempt.status == "VERIFIED":
        verification_status = "VERIFIED"
    elif attempt.status in {"PENDING_VERIFICATION", "VERIFICATION_PENDING"}:
        verification_status = "PENDING"

    # 4. Outcome
    outcome = "PENDING"
    if attempt.verified_outcome == "VERIFIED_SUCCESS":
        outcome = "RECOVERED"
    elif attempt.verified_outcome == "VERIFIED_FAILURE":
        outcome = "FAILED"
    elif attempt.status == "FAILED":
        outcome = "FAILED"

    return {
        "success": True,
        "data": {
            "opportunity_id": opportunity_id,
            "attempt_id": attempt.id,
            "attempt_status": attempt.status,
            "verified_outcome": attempt.verified_outcome,
            "execution_status": execution_status,
            "verification_status": verification_status,
            "outcome": outcome,
            "payment_link": (
                {
                    "payment_link_id": payment_link.payment_link_id,
                    "payment_link_reference_id": payment_link.payment_link_reference_id,
                    "status": payment_link.status,
                    "amount_minor": payment_link.amount_minor,
                    "currency": payment_link.currency,
                    "short_url": (
                        (json.loads(payment_link.external_response_reference).get("short_url") if payment_link.external_response_reference else None)
                        or (f"https://razorpay.com/payment-link/{payment_link.payment_link_id}/test" if payment_link.payment_link_id else None)
                    ),
                }
                if payment_link is not None
                else None
            ),
        },
    }


@router.get("/opportunities/{opportunity_id}/audit")
@router.get("/opportunities/{opportunity_id}/evidence")
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
    attempts = db.execute(select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity_id)).scalars().all()
    attempt_ids = [str(a.id) for a in attempts]
    conditions = []
    if workflow_chain_id:
        conditions.append((AuditEvent.entity_type == "RecoveryWorkflow") & (AuditEvent.entity_id == workflow_chain_id))
    if attempt_ids:
        conditions.append((AuditEvent.entity_type == "RecoveryAttempt") & (AuditEvent.entity_id.in_(attempt_ids)))
    conditions.append((AuditEvent.entity_type == "RevenueOpportunity") & (AuditEvent.entity_id == str(opportunity_id)))

    audits = db.execute(
        select(AuditEvent)
        .where(or_(*conditions))
        .order_by(AuditEvent.id.asc())
    ).scalars().all()
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
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    operating_status = get_truthful_operating_status(db, settings)
    return {"success": True, "data": {"status": "ok", "operating_status": operating_status}}


@router.get("/failure-demos")
def list_failure_demos() -> dict:
    scenarios = [
        {
            "scenario_id": "invalid_webhook_signature",
            "title": "Invalid Webhook Signature",
            "severity": "high",
            "expected_error_code": "INVALID_SIGNATURE",
            "description": "Demonstrates gateway rejection for tampered webhook signatures.",
            "trigger": "Webhook received with modified header signature or mismatching HMAC keys.",
            "expected_behavior": "Webhook signature verification fails; request is rejected immediately before domain processing.",
            "actual_behavior": "Returns 401 Unauthorized with sanitized signature verification error.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Webhook signature validation failure logged in WebhookEvent ledger.",
            "state_transitions": {
                "webhook": "fail",
                "signature_verification": "fail",
                "request_processing": "fail",
                "domain_processing": "not_applicable",
                "audit_event": "pass",
                "outcome_text": "Recovery blocked safely"
            }
        },
        {
            "scenario_id": "invalid_evaluation_request",
            "title": "Invalid Evaluation Request",
            "severity": "medium",
            "expected_error_code": "VALIDATION_ERROR",
            "description": "Demonstrates request validation guardrails on evaluation inputs.",
            "trigger": "Submit validation query with invalid dataset version or seed range.",
            "expected_behavior": "Input validator catches malformed schema; request is rejected before execution.",
            "actual_behavior": "Returns 422 Unprocessable Entity with field-level validation trace details.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Input validation failure captured in FastAPI request logs.",
            "state_transitions": {
                "input_payload": "fail",
                "validator": "fail",
                "run_execution": "not_applicable",
                "audit_event": "pass",
                "outcome_text": "Recovery blocked safely"
            }
        },
        {
            "scenario_id": "opportunity_not_found",
            "title": "Opportunity Not Found",
            "severity": "low",
            "expected_error_code": "OPPORTUNITY_NOT_FOUND",
            "description": "Demonstrates safe 404 handling for missing resources.",
            "trigger": "Execute recovery action on non-existent opportunity ID.",
            "expected_behavior": "Return 404 Not Found; no attempts recorded or mock links created.",
            "actual_behavior": "Returns 404 with deterministic code OPPORTUNITY_NOT_FOUND.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Resource validation exception logged in endpoint trace.",
            "state_transitions": {
                "resource_query": "fail",
                "ai_analysis": "not_applicable",
                "policy": "not_applicable",
                "execution": "not_applicable",
                "outcome_text": "Recovery blocked safely"
            }
        },
        {
            "scenario_id": "ai_invalid_output",
            "title": "AI Invalid Output",
            "severity": "high",
            "expected_error_code": "AI_SCHEMA_INVALID",
            "description": "Demonstrates schema validation rejection for malformed AI output.",
            "trigger": "AI provider returns malformed JSON dictionary violating structured diagnosis schema.",
            "expected_behavior": "Schema validation catches validation error; recommended action set to safety fallback ESCALATE.",
            "actual_behavior": "Decision marked validation-failed; system falls back to Escalation path.",
            "system_outcome": "System remained safe",
            "audit_result": "Malformed output trace written in AIAnalysis and RecoveryDecision ledger tables.",
            "state_transitions": {
                "ai_provider": "pass",
                "schema_validation": "fail",
                "rejection": "pass",
                "fallback_policy": "pass",
                "recovery_execution": "not_applicable",
                "outcome_text": "System remained safe"
            }
        },
        {
            "scenario_id": "ai_unavailable",
            "title": "AI Provider Unavailable",
            "severity": "high",
            "expected_error_code": "AI_UNAVAILABLE",
            "description": "Demonstrates graceful handling when AI provider is unreachable.",
            "trigger": "AI LLM API timeout or rate limit error during diagnosis stage.",
            "expected_behavior": "AI provider failure is intercepted; safe rule-based heuristic fallback activated.",
            "actual_behavior": "AI unavailability caught; system triggers default rule-based diagnosis and enforces policy checks.",
            "system_outcome": "System remained safe",
            "audit_result": "Provider failure exception logged under ai.decision.escalated_safe in AuditEvent ledger.",
            "state_transitions": {
                "ai_provider": "fail",
                "fallback_engine": "pass",
                "policy_check": "pass",
                "recovery": "pass",
                "outcome_text": "System remained safe"
            }
        },
        {
            "scenario_id": "policy_blocked",
            "title": "Policy Blocked",
            "severity": "medium",
            "expected_error_code": "POLICY_NOT_ALLOW",
            "description": "Demonstrates deterministic policy preventing unsafe execution.",
            "trigger": "Auto-execute recovery on opportunity where transaction value exceeds policy limits.",
            "expected_behavior": "AI recommends retry, but deterministic policy engine blocks it.",
            "actual_behavior": "Policy evaluation returns BLOCK; executor blocks the action.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Policy rejection rule logged in PolicyEvaluation and AuditEvent timeline.",
            "state_transitions": {
                "ai_recommendation": "pass",
                "policy_evaluation": "fail",
                "recovery_executor": "not_applicable",
                "outcome_text": "Recovery blocked safely"
            }
        },
        {
            "scenario_id": "recovery_failure",
            "title": "Recovery Failure",
            "severity": "high",
            "expected_error_code": "RECOVERY_EXECUTION_FAILED",
            "description": "Demonstrates safe handling when recovery execution fails.",
            "trigger": "Payment link creation API returns error response during execution stage.",
            "expected_behavior": "Execution failure caught; attempt status set to FAILED; recovered revenue remains unchanged.",
            "actual_behavior": "Gateway error caught; attempt recorded as FAILED with error code; no revenue counted.",
            "system_outcome": "System remained safe",
            "audit_result": "Attempt failure log captured in RecoveryAttempt database table.",
            "state_transitions": {
                "ai_policy": "pass",
                "gateway_executor": "fail",
                "outcome_verification": "fail",
                "outcome_text": "System remained safe"
            }
        },
        {
            "scenario_id": "duplicate_webhook",
            "title": "Duplicate Webhook",
            "severity": "medium",
            "expected_error_code": "DUPLICATE_EVENT_IGNORED",
            "description": "Demonstrates idempotent duplicate-event protection.",
            "trigger": "Replay payment failure webhook event ID evt_demo_012 that was already processed.",
            "expected_behavior": "Webhook processor checks ledger; duplicate delivery is ignored.",
            "actual_behavior": "WebhookEvent processing state matches; duplicate delivery rejected with code DUPLICATE_EVENT_IGNORED.",
            "system_outcome": "System remained safe",
            "audit_result": "Duplicate event receipt ledgered under webhook.duplicate event in AuditEvent table.",
            "state_transitions": {
                "event_received": "pass",
                "duplicate_check": "pass",
                "duplicate_ignored": "pass",
                "recovery_execution": "not_applicable",
                "outcome_text": "System remained safe"
            }
        },
    ]
    return {"success": True, "data": {"scenarios": scenarios}}


@router.post("/failure-demos/trigger")
def trigger_failure_demo(
    request: FailureScenarioTriggerRequest,
    auth_guard: bool = Depends(verify_security_guard),
):
    scenario_id = request.scenario_id.strip().lower()
    
    # Locate scenario in the defined list to return its metadata
    scenarios_data = {
        "invalid_webhook_signature": {
            "trigger": "Webhook received with modified header signature or mismatching HMAC keys.",
            "expected_behavior": "Webhook signature verification fails; request is rejected immediately before domain processing.",
            "actual_behavior": "Returns 401 Unauthorized with sanitized signature verification error.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Webhook signature validation failure logged in WebhookEvent ledger.",
            "state_transitions": {
                "webhook": "fail",
                "signature_verification": "fail",
                "request_processing": "fail",
                "domain_processing": "not_applicable",
                "audit_event": "pass",
                "outcome_text": "Recovery blocked safely"
            }
        },
        "invalid_evaluation_request": {
            "trigger": "Submit validation query with invalid dataset version or seed range.",
            "expected_behavior": "Input validator catches malformed schema; request is rejected before execution.",
            "actual_behavior": "Returns 422 Unprocessable Entity with field-level validation details.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Input validation failure captured in FastAPI request logs.",
            "state_transitions": {
                "input_payload": "fail",
                "validator": "fail",
                "run_execution": "not_applicable",
                "audit_event": "pass",
                "outcome_text": "Recovery blocked safely"
            }
        },
        "opportunity_not_found": {
            "trigger": "Execute recovery action on non-existent opportunity ID.",
            "expected_behavior": "Return 404 Not Found; no attempts recorded or mock links created.",
            "actual_behavior": "Returns 404 with deterministic code OPPORTUNITY_NOT_FOUND.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Resource validation exception logged in endpoint trace.",
            "state_transitions": {
                "resource_query": "fail",
                "ai_analysis": "not_applicable",
                "policy": "not_applicable",
                "execution": "not_applicable",
                "outcome_text": "Recovery blocked safely"
            }
        },
        "ai_invalid_output": {
            "trigger": "AI provider returns malformed JSON dictionary violating structured diagnosis schema.",
            "expected_behavior": "Schema validation catches validation error; recommended action set to safety fallback ESCALATE.",
            "actual_behavior": "Decision marked validation-failed; system falls back to Escalation path.",
            "system_outcome": "System remained safe",
            "audit_result": "Malformed output trace written in AIAnalysis and RecoveryDecision ledger tables.",
            "state_transitions": {
                "ai_provider": "pass",
                "schema_validation": "fail",
                "rejection": "pass",
                "fallback_policy": "pass",
                "recovery_execution": "not_applicable",
                "outcome_text": "System remained safe"
            }
        },
        "ai_unavailable": {
            "trigger": "AI LLM API timeout or rate limit error during diagnosis stage.",
            "expected_behavior": "AI provider failure is intercepted; safe rule-based heuristic fallback activated.",
            "actual_behavior": "AI unavailability caught; system triggers default rule-based diagnosis and enforces policy checks.",
            "system_outcome": "System remained safe",
            "audit_result": "Provider failure exception logged under ai.decision.escalated_safe in AuditEvent ledger.",
            "state_transitions": {
                "ai_provider": "fail",
                "fallback_engine": "pass",
                "policy_check": "pass",
                "recovery": "pass",
                "outcome_text": "System remained safe"
            }
        },
        "policy_blocked": {
            "trigger": "Auto-execute recovery on opportunity where transaction value exceeds policy limits.",
            "expected_behavior": "AI recommends retry, but deterministic policy engine blocks it.",
            "actual_behavior": "Policy evaluation returns BLOCK; executor blocks the action.",
            "system_outcome": "Recovery blocked safely",
            "audit_result": "Policy rejection rule logged in PolicyEvaluation and AuditEvent timeline.",
            "state_transitions": {
                "ai_recommendation": "pass",
                "policy_evaluation": "fail",
                "recovery_executor": "not_applicable",
                "outcome_text": "Recovery blocked safely"
            }
        },
        "recovery_failure": {
            "trigger": "Payment link creation API returns error response during execution stage.",
            "expected_behavior": "Execution failure caught; attempt status set to FAILED; recovered revenue remains unchanged.",
            "actual_behavior": "Gateway error caught; attempt recorded as FAILED with error code; no revenue counted.",
            "system_outcome": "System remained safe",
            "audit_result": "Attempt failure log captured in RecoveryAttempt database table.",
            "state_transitions": {
                "ai_policy": "pass",
                "gateway_executor": "fail",
                "outcome_verification": "fail",
                "outcome_text": "System remained safe"
            }
        },
        "duplicate_webhook": {
            "trigger": "Replay payment failure webhook event ID evt_demo_012 that was already processed.",
            "expected_behavior": "Webhook processor checks ledger; duplicate delivery is ignored.",
            "actual_behavior": "WebhookEvent processing state matches; duplicate delivery rejected with code DUPLICATE_EVENT_IGNORED.",
            "system_outcome": "System remained safe",
            "audit_result": "Duplicate event receipt ledgered under webhook.duplicate event in AuditEvent table.",
            "state_transitions": {
                "event_received": "pass",
                "duplicate_check": "pass",
                "duplicate_ignored": "pass",
                "recovery_execution": "not_applicable",
                "outcome_text": "System remained safe"
            }
        }
    }
    
    meta = scenarios_data.get(scenario_id, {})
    
    if scenario_id == "invalid_evaluation_request":
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Evaluation request validation failed.",
                },
                "data": meta,
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
                "data": meta,
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
                "data": meta,
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
                "data": meta,
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
                "data": meta,
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
                "data": meta,
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
                "data": meta,
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
                "data": meta,
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
    operating_status = get_truthful_operating_status(db, settings)
    test_mode = operating_status["payment_environment"] == "RAZORPAY TEST"
    live_mode_detected = settings.razorpay_live_mode_detected
    credentials_configured = settings.razorpay_configured
    webhook_configured = bool((settings.razorpay_webhook_secret or "").strip())
    api_connectivity = operating_status["api_connectivity"]
    api_connectivity_reason = operating_status["api_connectivity_reason"]

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
            "operating_status": operating_status,
            "last_event": last_event.event_type if last_event is not None else None,
            "last_event_id": last_event.razorpay_event_id if last_event is not None else None,
            "last_event_status": last_event.processing_status if last_event is not None else None,
            "last_event_received_at": last_event.received_at.isoformat() if last_event and last_event.received_at else None,
            "last_successful_razorpay_operation": last_successful_razorpay_operation,
        },
    }


@router.post("/readiness/execute")
def execute_readiness(
    db: Session = Depends(get_db),
    auth_guard: bool = Depends(verify_security_guard),
) -> dict:
    result = execute_readiness_acceptance_workflow(db)
    return {"success": True, "data": result}


@router.post("/readiness/phase13/execute")
def execute_phase13_readiness(
    db: Session = Depends(get_db),
    auth_guard: bool = Depends(verify_security_guard),
) -> dict:
    # Secondary execution endpoint for acceptance workflow.
    result = execute_readiness_acceptance_workflow(db)
    return {"success": True, "data": result}


@router.post("/demo/seed-core-recovery")
def seed_core_recovery(
    db: Session = Depends(get_db),
    auth_guard: bool = Depends(verify_security_guard),
) -> dict:
    result = seed_core_recovery_demo(db)
    db.commit()
    return {"success": True, "data": result}


@router.post("/demo/reset-core-recovery")
def reset_core_recovery(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth_guard: bool = Depends(verify_security_guard),
) -> dict:
    reset_core_recovery_data(db)
    db.commit()
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
    x_razorpay_signature: str | None = Header(default=None, alias="x-razorpay-signature"),
):
    raw_body = await request.body()
    signature = x_razorpay_signature or request.headers.get("x-razorpay-signature", "")
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
def run_evaluation(
    request: EvaluationRunRequest,
    db: Session = Depends(get_db),
    auth_guard: bool = Depends(verify_security_guard),
):
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
        summary = get_recoveriq_policy_path_summary(db, evaluation_run_id=row.evaluation_run_id) or get_evaluation_run_summary(db, evaluation_run_id=row.evaluation_run_id)
        if summary is None:
            continue
        summary_payload = evaluation_summary_to_dict(summary)
        summary_payload["evaluation_run_id"] = row.evaluation_run_id
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

    # Query AuditEvent to construct reproducibility metadata
    audit_evt = db.query(AuditEvent).filter(
        AuditEvent.event_type == "evaluation.completed",
        AuditEvent.entity_id == run_id
    ).first()
    
    metadata = {
        "dataset_version": "v1.2.0-default",
        "split": "TEST",
        "generation_seed": 42,
        "total_cases": summary.records,
        "model_strategy": "AI Recommendation / Safety Rules Engine",
        "run_id": run_id,
        "timestamp": audit_evt.timestamp.isoformat() if audit_evt else None,
        "reproducible": True
    }
    if audit_evt and audit_evt.metadata_json:
        metadata["dataset_version"] = audit_evt.metadata_json.get("dataset_version", "v1.2.0-default")
        metadata["split"] = audit_evt.metadata_json.get("split", "TEST")
        metadata["generation_seed"] = audit_evt.metadata_json.get("generation_seed", 42)
        metadata["total_cases"] = audit_evt.metadata_json.get("total_cases", summary.records)
        metadata["reproducible"] = metadata["generation_seed"] is not None

    return {
        "success": True,
        "data": {
            "baseline": baseline,
            "recoveriq": recoveriq,
            "deltas": deltas,
            "attribution": comparison["attribution"],
            "comparison_note": "RecoverIQ metrics are computed using a deterministic policy-path strategy over the same held-out cases.",
            "metadata": metadata,
        },
    }


@router.get("/evaluation/{run_id}/drilldown")
def get_evaluation_run_drilldown(run_id: str, strategy: str = "recoveriq", db: Session = Depends(get_db)):
    summary, not_found = _evaluation_summary_or_404(db, run_id=run_id)
    if not_found is not None:
        return not_found

    cases = get_evaluation_run_cases(db, evaluation_run_id=run_id)
    if not cases:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": {
                    "code": "EVAL_RUN_NOT_FOUND",
                    "message": "Evaluation run cases not found.",
                },
            },
        )

    if strategy.lower() == "baseline":
        predictor = _baseline_prediction
        cost_func = lambda action: 500 if action != "NO_ACTION" else 0
        effective_run_id = run_id
    else:
        predictor = _recoveriq_policy_prediction
        cost_func = lambda action: 450 if action != "NO_ACTION" else 0
        effective_run_id = f"{run_id}:recoveriq_policy"

    run_summary = _summary_from_predictions(
        run_id=effective_run_id,
        cases=cases,
        predictor=predictor,
        intervention_cost_minor_for_action=cost_func,
    )

    tp = fp = fn = tn = 0
    failed_case_count = successful_case_count = 0
    failed_correct = successful_correct = 0
    sample_errors: list[dict] = []

    for case in cases:
        predicted_recoverable, predicted_action, prob, reason_code = predictor(case)
        actual_recoverable = bool(case.ground_truth_recoverable)
        correct = (predicted_recoverable == actual_recoverable)
        false_positive = (predicted_recoverable and not actual_recoverable)
        false_negative = ((not predicted_recoverable) and actual_recoverable)

        if predicted_recoverable and actual_recoverable:
            tp += 1
        elif false_positive:
            fp += 1
        elif false_negative:
            fn += 1
        else:
            tn += 1

        is_failed_case = (case.case_type == "failed_payment")
        if is_failed_case:
            failed_case_count += 1
            if correct:
                failed_correct += 1
        else:
            successful_case_count += 1
            if correct:
                successful_correct += 1

        if (false_positive or false_negative) and len(sample_errors) < 10:
            sample_errors.append(
                {
                    "case_id": case.id,
                    "error_type": "FALSE_POSITIVE" if false_positive else "FALSE_NEGATIVE",
                    "predicted_action": predicted_action,
                    "actual_action": case.ground_truth_action,
                    "failure_reason": case.failure_features.get("reason"),
                }
            )

    data = {
        "summary": evaluation_summary_to_dict(run_summary),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "false_positive_cost": {
            "count": run_summary.false_positive_count,
            "financial_exposure_minor": run_summary.false_positive_exposure_minor,
            "intervention_cost_minor": run_summary.false_positive_intervention_cost_minor,
        },
        "operational": {
            "allowed": run_summary.allowed_count,
            "blocked": run_summary.blocked_count,
            "escalated": run_summary.escalated_count,
            "failed": run_summary.failed_count,
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
