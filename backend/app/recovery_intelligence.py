from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai.providers import DiagnosisContext, get_provider
from .diagnosis_schema import DIAGNOSIS_SCHEMA_VERSION, StructuredDiagnosis
from .economics import compute_economics
from .models import AIAnalysis, Payment, RecoveryDecision, RevenueOpportunity
from .scoring import score_failed_payment
from .state_machine import can_transition_recovery


_LINK_EQUIVALENT_ACTIONS = {
    "RETRY",
    "DELAYED_RETRY",
    "RECOVERY_PROMPT",
    "ALTERNATE_PAYMENT_PATH",
}


def _normalize_recommended_action(action: str) -> str:
    normalized = (action or "").strip().upper()
    if normalized in _LINK_EQUIVALENT_ACTIONS:
        return "CREATE_PAYMENT_LINK"
    if normalized in {"CREATE_PAYMENT_LINK", "ESCALATE", "NO_ACTION"}:
        return normalized
    return "ESCALATE"


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _safe_transition_opportunity(opportunity: RevenueOpportunity, target: str) -> None:
    if can_transition_recovery(opportunity.status, target):
        opportunity.status = target


def upsert_revenue_opportunity_for_payment(
    db: Session,
    *,
    payment_id: int,
    source_event_id: int | None = None,
) -> RevenueOpportunity | None:
    payment = db.execute(select(Payment).where(Payment.id == payment_id)).scalar_one_or_none()
    if payment is None or payment.status != "FAILED":
        return None

    scoring = score_failed_payment(payment)
    economics = compute_economics(
        amount_at_risk_minor=payment.amount_minor,
        recovery_probability_pct=scoring.recovery_probability_pct,
        action=scoring.recommended_action,
    )

    existing = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.payment_id == payment.id)
    ).scalar_one_or_none()

    if existing is None:
        opportunity = RevenueOpportunity(
            customer_id=payment.customer_id,
            payment_id=payment.id,
            order_id=None,
            subscription_id=None,
            source_event_id=source_event_id,
            amount_at_risk_minor=payment.amount_minor,
            currency=payment.currency,
            failure_category=scoring.failure_category,
            failure_reason=payment.failure_reason,
            recovery_probability=scoring.recovery_probability_pct,
            recovery_score=scoring.recovery_score,
            expected_recovery_minor=economics.expected_recovery_minor,
            estimated_intervention_cost_minor=economics.estimated_intervention_cost_minor,
            expected_net_recovery_minor=economics.expected_net_recovery_minor,
            recommended_action=scoring.recommended_action,
            confidence=scoring.confidence_pct,
            status="IDENTIFIED",
            expires_at=None,
        )
        db.add(opportunity)
        db.commit()
        db.refresh(opportunity)
        return opportunity

    existing.amount_at_risk_minor = payment.amount_minor
    existing.currency = payment.currency
    existing.failure_category = scoring.failure_category
    existing.failure_reason = payment.failure_reason
    existing.recovery_probability = scoring.recovery_probability_pct
    existing.recovery_score = scoring.recovery_score
    existing.expected_recovery_minor = economics.expected_recovery_minor
    existing.estimated_intervention_cost_minor = economics.estimated_intervention_cost_minor
    existing.expected_net_recovery_minor = economics.expected_net_recovery_minor
    existing.recommended_action = scoring.recommended_action
    existing.confidence = scoring.confidence_pct
    if source_event_id is not None:
        existing.source_event_id = source_event_id
    existing.updated_at = _utc_now_naive()
    db.commit()
    db.refresh(existing)
    return existing


@dataclass(frozen=True)
class DecisionBuildResult:
    decision: RecoveryDecision
    fallback_used: bool
    failure_reason: str | None


def _build_diagnosis_context(opportunity: RevenueOpportunity) -> DiagnosisContext:
    return DiagnosisContext(
        opportunity_id=opportunity.id,
        payment_id=opportunity.payment_id,
        amount_at_risk_minor=opportunity.amount_at_risk_minor,
        currency=opportunity.currency,
        failure_category=opportunity.failure_category or "UNKNOWN",
        failure_reason=opportunity.failure_reason or "unknown",
        baseline_recommended_action=opportunity.recommended_action or "ESCALATE",
        baseline_recovery_probability=opportunity.recovery_probability,
    )


def _persist_recovery_decision(
    db: Session,
    *,
    opportunity: RevenueOpportunity,
    diagnosis: StructuredDiagnosis,
    provider_name: str,
    model_name: str | None,
) -> RecoveryDecision:
    normalized_action = _normalize_recommended_action(diagnosis.recommended_action)
    economics = compute_economics(
        amount_at_risk_minor=opportunity.amount_at_risk_minor,
        recovery_probability_pct=diagnosis.recovery_probability,
        action=normalized_action,
    )

    decision = RecoveryDecision(
        opportunity_id=opportunity.id,
        diagnosis=diagnosis.diagnosis,
        evidence={
            "failure_category": diagnosis.failure_category,
            "reason": diagnosis.reason,
            "uncertainties": diagnosis.uncertainties,
            "signals": [item.model_dump() for item in diagnosis.evidence],
            "provider_metadata": diagnosis.provider_metadata,
        },
        recovery_probability=diagnosis.recovery_probability,
        confidence=diagnosis.confidence,
        recommended_action=normalized_action,
        expected_recovery_minor=economics.expected_recovery_minor,
        estimated_cost_minor=economics.estimated_intervention_cost_minor,
        expected_net_recovery_minor=economics.expected_net_recovery_minor,
        decision_source="AI",
        provider=provider_name,
        model=model_name,
        model_version=model_name,
        prompt_version="v1.0",
        schema_version=DIAGNOSIS_SCHEMA_VERSION,
    )
    db.add(decision)
    db.flush()

    analysis = AIAnalysis(
        opportunity_id=opportunity.id,
        decision_id=decision.id,
        provider=provider_name,
        model=model_name,
        schema_version=DIAGNOSIS_SCHEMA_VERSION,
        valid_schema=True,
        failure_category=diagnosis.failure_category,
        diagnosis=diagnosis.diagnosis,
        confidence=diagnosis.confidence,
        recommended_action=normalized_action,
        raw_output=diagnosis.model_dump(),
        validation_error=None,
    )
    db.add(analysis)

    opportunity.recommended_action = normalized_action
    opportunity.recovery_probability = diagnosis.recovery_probability
    opportunity.confidence = diagnosis.confidence
    opportunity.expected_recovery_minor = economics.expected_recovery_minor
    opportunity.estimated_intervention_cost_minor = economics.estimated_intervention_cost_minor
    opportunity.expected_net_recovery_minor = economics.expected_net_recovery_minor
    _safe_transition_opportunity(opportunity, "ANALYZED")
    _safe_transition_opportunity(opportunity, "RECOMMENDED")
    opportunity.updated_at = _utc_now_naive()

    db.commit()
    db.refresh(decision)
    return decision


def _persist_escalate_safe_fallback(
    db: Session,
    *,
    opportunity: RevenueOpportunity,
    provider_name: str,
    model_name: str | None,
    failure_reason: str,
) -> RecoveryDecision:
    economics = compute_economics(
        amount_at_risk_minor=opportunity.amount_at_risk_minor,
        recovery_probability_pct=0,
        action="ESCALATE",
    )

    decision = RecoveryDecision(
        opportunity_id=opportunity.id,
        diagnosis="AI diagnosis unavailable; escalated safely for manual intervention.",
        evidence={
            "failure_reason": failure_reason,
            "fallback": "ESCALATE",
        },
        recovery_probability=0,
        confidence=0,
        recommended_action="ESCALATE",
        expected_recovery_minor=economics.expected_recovery_minor,
        estimated_cost_minor=economics.estimated_intervention_cost_minor,
        expected_net_recovery_minor=economics.expected_net_recovery_minor,
        decision_source="AI_FALLBACK",
        provider=provider_name,
        model=model_name,
        model_version=model_name,
        prompt_version="v1.0",
        schema_version=DIAGNOSIS_SCHEMA_VERSION,
    )
    db.add(decision)
    db.flush()

    analysis = AIAnalysis(
        opportunity_id=opportunity.id,
        decision_id=decision.id,
        provider=provider_name,
        model=model_name,
        schema_version=DIAGNOSIS_SCHEMA_VERSION,
        valid_schema=False,
        failure_category=opportunity.failure_category,
        diagnosis=None,
        confidence=0,
        recommended_action="ESCALATE",
        raw_output={"fallback": "ESCALATE", "failure_reason": failure_reason},
        validation_error=failure_reason,
    )
    db.add(analysis)

    opportunity.recommended_action = "ESCALATE"
    opportunity.recovery_probability = 0
    opportunity.confidence = 0
    opportunity.expected_recovery_minor = economics.expected_recovery_minor
    opportunity.estimated_intervention_cost_minor = economics.estimated_intervention_cost_minor
    opportunity.expected_net_recovery_minor = economics.expected_net_recovery_minor
    _safe_transition_opportunity(opportunity, "ESCALATED")
    opportunity.updated_at = _utc_now_naive()

    db.commit()
    db.refresh(decision)
    return decision


def create_recovery_decision_for_opportunity(
    db: Session,
    *,
    opportunity_id: int,
) -> DecisionBuildResult | None:
    opportunity = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)
    ).scalar_one_or_none()
    if opportunity is None:
        return None

    context = _build_diagnosis_context(opportunity)
    provider_name = "unknown"
    model_name = None
    try:
        provider = get_provider()
        provider_name = provider.name
        model_name = provider.model_name
        raw_diagnosis = provider.generate_diagnosis(context)
        validated = StructuredDiagnosis.model_validate(raw_diagnosis)
        decision = _persist_recovery_decision(
            db,
            opportunity=opportunity,
            diagnosis=validated,
            provider_name=provider_name,
            model_name=model_name,
        )
        return DecisionBuildResult(decision=decision, fallback_used=False, failure_reason=None)
    except Exception as exc:  # noqa: BLE001
        failure_reason = f"ai_diagnosis_failed: {exc}"
        decision = _persist_escalate_safe_fallback(
            db,
            opportunity=opportunity,
            provider_name=provider_name,
            model_name=model_name,
            failure_reason=failure_reason,
        )
        return DecisionBuildResult(decision=decision, fallback_used=True, failure_reason=failure_reason)
