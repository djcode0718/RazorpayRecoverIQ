from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RevenueOpportunity
from .state_machine import RecoveryState, can_transition_recovery


POLICY_VERSION = "v1.0"
MAX_AMOUNT_MINOR = 900_000
MIN_CONFIDENCE_PCT = 60
MAX_RETRY_ATTEMPTS = 3
MIN_EXPECTED_NET_RECOVERY_MINOR = 1
ALLOWED_AUTOMATED_ACTIONS = {"CREATE_PAYMENT_LINK"}
_LEGACY_LINK_EQUIVALENT_ACTIONS = {
    "RETRY",
    "DELAYED_RETRY",
    "RECOVERY_PROMPT",
    "ALTERNATE_PAYMENT_PATH",
}


@dataclass(frozen=True)
class PolicyCheckResult:
    result: str
    reason_codes: dict[str, list[str]]
    evaluated_rules: dict[str, dict[str, object]]


def _build_reason_codes(checks: dict[str, bool]) -> dict[str, list[str]]:
    failed = [f"POLICY_{name}_FAILED" for name, passed in checks.items() if not passed]
    passed = [f"POLICY_{name}_PASSED" for name, passed in checks.items() if passed]
    return {"failed": failed, "passed": passed}


def _has_open_attempt(db: Session, opportunity_id: int) -> bool:
    open_statuses = {"REQUESTED", "EXECUTED", "PENDING_VERIFICATION"}
    open_count = db.execute(
        select(func.count(RecoveryAttempt.id)).where(
            RecoveryAttempt.opportunity_id == opportunity_id,
            RecoveryAttempt.status.in_(open_statuses),
        )
    ).scalar_one()
    return open_count > 0


def evaluate_policy_for_decision(
    db: Session,
    *,
    opportunity_id: int,
    decision_id: int,
) -> PolicyEvaluation:
    opportunity = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)
    ).scalar_one()
    decision = db.execute(select(RecoveryDecision).where(RecoveryDecision.id == decision_id)).scalar_one()

    retry_attempt_count = db.execute(
        select(func.count(RecoveryAttempt.id)).where(RecoveryAttempt.opportunity_id == opportunity_id)
    ).scalar_one()

    settings = get_settings()
    normalized_action = (decision.recommended_action or "").strip().upper()
    if normalized_action in _LEGACY_LINK_EQUIVALENT_ACTIONS:
        normalized_action = "CREATE_PAYMENT_LINK"
    checks = {
        "test_mode": settings.app_mode.strip().lower() in {"simulation", "test", "development"},
        "max_amount": opportunity.amount_at_risk_minor <= MAX_AMOUNT_MINOR,
        "confidence": decision.confidence >= MIN_CONFIDENCE_PCT,
        "expected_net": decision.expected_net_recovery_minor >= MIN_EXPECTED_NET_RECOVERY_MINOR,
        "retry_limit": retry_attempt_count < MAX_RETRY_ATTEMPTS,
        "duplicate": not _has_open_attempt(db, opportunity_id),
        "allowlisted_action": normalized_action in ALLOWED_AUTOMATED_ACTIONS,
    }
    reason_codes = _build_reason_codes(checks)
    escalated_failures = {
        "confidence",
        "allowlisted_action",
    }
    failed_rule_names = {name for name, passed in checks.items() if not passed}
    if not failed_rule_names:
        result = "ALLOW"
    elif failed_rule_names.intersection(escalated_failures):
        result = "ESCALATE"
    else:
        result = "BLOCK"

    known_states = {item.value for item in RecoveryState}
    state_is_known = opportunity.status in known_states

    if result == "ALLOW" and state_is_known and not can_transition_recovery(opportunity.status, "POLICY_ALLOWED"):
        result = "BLOCK"
        reason_codes["failed"].append("POLICY_state_transition_FAILED")
    elif result == "ESCALATE" and state_is_known and not can_transition_recovery(opportunity.status, "ESCALATED"):
        result = "BLOCK"
        reason_codes["failed"].append("POLICY_state_transition_FAILED")

    if result == "ALLOW":
        opportunity.status = "POLICY_ALLOWED"
    elif result == "ESCALATE":
        opportunity.status = "ESCALATED"
    else:
        if (not state_is_known) or can_transition_recovery(opportunity.status, "POLICY_BLOCKED"):
            opportunity.status = "POLICY_BLOCKED"

    evaluated_rules = {
        "test_mode": {"passed": checks["test_mode"], "threshold": ["simulation", "test", "development"], "actual": settings.app_mode},
        "max_amount": {"passed": checks["max_amount"], "threshold_minor": MAX_AMOUNT_MINOR, "actual_minor": opportunity.amount_at_risk_minor},
        "confidence": {"passed": checks["confidence"], "threshold_pct": MIN_CONFIDENCE_PCT, "actual_pct": decision.confidence},
        "expected_net": {"passed": checks["expected_net"], "threshold_minor": MIN_EXPECTED_NET_RECOVERY_MINOR, "actual_minor": decision.expected_net_recovery_minor},
        "retry_limit": {"passed": checks["retry_limit"], "max_attempts": MAX_RETRY_ATTEMPTS, "actual_attempts": retry_attempt_count},
        "duplicate": {"passed": checks["duplicate"], "actual_open_attempt": not checks["duplicate"]},
        "allowlisted_action": {"passed": checks["allowlisted_action"], "allowed": sorted(ALLOWED_AUTOMATED_ACTIONS), "actual": normalized_action},
    }

    evaluation = PolicyEvaluation(
        opportunity_id=opportunity_id,
        decision_id=decision_id,
        result=result,
        reason_codes=reason_codes,
        evaluated_rules=evaluated_rules,
        max_amount_check=checks["max_amount"],
        confidence_check=checks["confidence"],
        retry_limit_check=checks["retry_limit"],
        economic_check=checks["expected_net"],
        duplicate_check=checks["duplicate"],
        environment_check=checks["test_mode"],
        policy_version=POLICY_VERSION,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return evaluation
