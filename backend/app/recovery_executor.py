from datetime import UTC, datetime
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .gateway_adapters import (
    PaymentAdapterConfigurationError,
    PaymentAdapterError,
    PaymentAdapterTimeoutError,
    PaymentLinkRequest,
    get_payment_adapter,
)
from .models import PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RecoveryPaymentLink, RevenueOpportunity
from .state_machine import RecoveryState, can_transition_recovery


EXECUTOR_VERSION = "phase6-v1"
EXECUTABLE_ACTIONS = {"CREATE_PAYMENT_LINK"}
TERMINAL_OPPORTUNITY_STATUSES = {"CLOSED", "RESOLVED"}
_LEGACY_LINK_EQUIVALENT_ACTIONS = {
    "RETRY",
    "DELAYED_RETRY",
    "RECOVERY_PROMPT",
    "ALTERNATE_PAYMENT_PATH",
}


def _normalize_executable_action(action: str) -> str:
    normalized = (action or "").strip().upper()
    if normalized in _LEGACY_LINK_EQUIVALENT_ACTIONS:
        return "CREATE_PAYMENT_LINK"
    return normalized


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def execute_recovery_attempt(
    db: Session,
    *,
    opportunity_id: int,
    decision_id: int,
    policy_evaluation_id: int,
) -> RecoveryAttempt:
    policy = db.execute(select(PolicyEvaluation).where(PolicyEvaluation.id == policy_evaluation_id)).scalar_one()
    if policy.result != "ALLOW":
        raise ValueError("policy_not_allow")

    opportunity = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)
    ).scalar_one()
    decision = db.execute(select(RecoveryDecision).where(RecoveryDecision.id == decision_id)).scalar_one()

    if opportunity.status in TERMINAL_OPPORTUNITY_STATUSES:
        raise ValueError("opportunity_not_executable")

    executable_action = _normalize_executable_action(decision.recommended_action)
    if executable_action not in EXECUTABLE_ACTIONS:
        raise ValueError("action_not_executable")

    if not decision.schema_version:
        raise ValueError("invalid_ai_decision_schema")

    settings = get_settings()
    if settings.app_mode.strip().lower() not in {"simulation", "test", "development"}:
        raise ValueError("execution_requires_test_mode")

    known_states = {item.value for item in RecoveryState}
    if opportunity.status in known_states and not can_transition_recovery(opportunity.status, "PAYMENT_LINK_CREATED"):
        raise ValueError("invalid_recovery_state_transition")

    open_attempt = db.execute(
        select(RecoveryAttempt).where(
            RecoveryAttempt.opportunity_id == opportunity_id,
            RecoveryAttempt.status.in_({"REQUESTED", "EXECUTED", "PENDING_VERIFICATION"}),
        )
    ).scalar_one_or_none()
    if open_attempt is not None:
        return open_attempt

    attempt_number = db.execute(
        select(func.count(RecoveryAttempt.id)).where(RecoveryAttempt.opportunity_id == opportunity_id)
    ).scalar_one() + 1

    attempt = RecoveryAttempt(
        opportunity_id=opportunity_id,
        action=executable_action,
        attempt_number=attempt_number,
        policy_evaluation_id=policy_evaluation_id,
        status="REQUESTED",
        amount_minor=opportunity.amount_at_risk_minor,
        currency=opportunity.currency,
        failure_code=None,
        failure_reason=None,
        verified_outcome=None,
        recovered_amount_minor=0,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    now = _utc_now_naive()
    try:
        adapter = get_payment_adapter(settings)
        link_result = adapter.create_payment_link(
            PaymentLinkRequest(
                opportunity_id=opportunity_id,
                attempt_number=attempt_number,
                amount_minor=opportunity.amount_at_risk_minor,
                currency=opportunity.currency,
                customer_reference=str(opportunity.customer_id) if opportunity.customer_id is not None else None,
            )
        )
    except PaymentAdapterTimeoutError as exc:
        attempt.status = "FAILED"
        attempt.completed_at = now
        attempt.failure_code = "ADAPTER_TIMEOUT"
        attempt.failure_reason = str(exc)
        db.commit()
        raise ValueError("adapter_timeout") from exc
    except PaymentAdapterConfigurationError as exc:
        attempt.status = "FAILED"
        attempt.completed_at = now
        attempt.failure_code = "ADAPTER_CONFIG"
        attempt.failure_reason = str(exc)
        db.commit()
        raise ValueError("adapter_configuration_error") from exc
    except PaymentAdapterError as exc:
        attempt.status = "FAILED"
        attempt.completed_at = now
        attempt.failure_code = "ADAPTER_ERROR"
        attempt.failure_reason = str(exc)
        db.commit()
        raise ValueError("adapter_request_failed") from exc

    attempt.status = "EXECUTED"
    attempt.executed_at = now
    attempt.completed_at = now
    attempt.external_reference = link_result.payment_link_id
    attempt.failure_code = None
    attempt.failure_reason = None
    opportunity.status = "PAYMENT_LINK_CREATED"
    opportunity.updated_at = now

    link = RecoveryPaymentLink(
        opportunity_id=opportunity_id,
        recovery_attempt_id=attempt.id,
        payment_link_id=link_result.payment_link_id,
        payment_link_reference_id=link_result.reference_id,
        amount_minor=opportunity.amount_at_risk_minor,
        currency=opportunity.currency,
        status=link_result.status,
        external_response_reference=json.dumps({
            "adapter": link_result.provider,
            "executor_version": EXECUTOR_VERSION,
            "attempt_id": attempt.id,
            "response": link_result.raw_response,
        }, separators=(",", ":")),
    )
    db.add(link)
    db.commit()
    db.refresh(attempt)
    return attempt
