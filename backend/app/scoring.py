from dataclasses import dataclass

from .models import Payment


_FAILURE_CATEGORY_MAP = {
    "issuer_declined": "ISSUER_DECLINE",
    "network": "NETWORK",
    "insufficient_funds": "INSUFFICIENT_FUNDS",
    "3ds_failed": "AUTHENTICATION",
}


@dataclass(frozen=True)
class ScoringResult:
    failure_category: str
    recovery_probability_pct: int
    recovery_score: int
    confidence_pct: int
    recommended_action: str


def _probability_from_payment(payment: Payment) -> int:
    probability = 45
    if payment.failure_reason in {"issuer_declined", "network"}:
        probability += 20
    elif payment.failure_reason in {"insufficient_funds", "3ds_failed"}:
        probability += 10

    if payment.amount_minor <= 200_000:
        probability += 15
    elif payment.amount_minor >= 800_000:
        probability -= 15

    if payment.method in {"card", "upi", "netbanking"}:
        probability += 5

    if payment.status != "FAILED":
        probability = min(probability, 20)

    return max(5, min(95, probability))


def _recommended_action(probability_pct: int) -> str:
    if probability_pct >= 75:
        return "RETRY"
    if probability_pct >= 55:
        return "DELAYED_RETRY"
    if probability_pct >= 35:
        return "RECOVERY_PROMPT"
    return "ESCALATE"


def score_failed_payment(payment: Payment) -> ScoringResult:
    probability = _probability_from_payment(payment)
    action = _recommended_action(probability)
    confidence = max(55, min(95, 60 + abs(probability - 50) // 2))
    failure_category = _FAILURE_CATEGORY_MAP.get(payment.failure_reason or "", "UNKNOWN")

    return ScoringResult(
        failure_category=failure_category,
        recovery_probability_pct=probability,
        recovery_score=probability,
        confidence_pct=confidence,
        recommended_action=action,
    )

