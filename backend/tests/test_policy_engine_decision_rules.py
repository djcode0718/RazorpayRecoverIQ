import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.models import Payment, RecoveryDecision, RevenueOpportunity
from app.policy_engine import evaluate_policy_for_decision


def _build_session(tmp_path: Path) -> Session:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase6_policy.db'}"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return get_session_local()()


def _seed_opportunity_and_decision(
    session: Session,
    *,
    amount_minor: int,
    confidence: int,
    expected_net_recovery_minor: int,
    action: str = "RETRY",
) -> tuple[int, int]:
    payment = Payment(
        razorpay_payment_id=f"pay_{amount_minor}_{confidence}",
        razorpay_order_id="order_phase6",
        customer_id=None,
        amount_minor=amount_minor,
        currency="INR",
        status="FAILED",
        method="card",
        captured=False,
        failure_reason="network",
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)

    opportunity = RevenueOpportunity(
        customer_id=None,
        payment_id=payment.id,
        order_id=None,
        subscription_id=None,
        source_event_id=None,
        amount_at_risk_minor=amount_minor,
        currency="INR",
        failure_category="NETWORK",
        failure_reason="network",
        recovery_probability=70,
        recovery_score=70,
        expected_recovery_minor=max(0, amount_minor // 2),
        estimated_intervention_cost_minor=200,
        expected_net_recovery_minor=expected_net_recovery_minor,
        recommended_action=action,
        confidence=confidence,
        status="DETECTED",
        expires_at=None,
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    decision = RecoveryDecision(
        opportunity_id=opportunity.id,
        diagnosis="Deterministic phase 6 policy test diagnosis that satisfies minimum length.",
        evidence={"signals": [{"signal": "failure_reason", "value": "network"}]},
        recovery_probability=70,
        confidence=confidence,
        recommended_action=action,
        expected_recovery_minor=max(0, amount_minor // 2),
        estimated_cost_minor=200,
        expected_net_recovery_minor=expected_net_recovery_minor,
        decision_source="AI",
        provider="mock",
        model="mock-v1",
        model_version="mock-v1",
        prompt_version="phase5-v1",
        schema_version="v1",
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return opportunity.id, decision.id


def test_policy_engine_allows_when_all_checks_pass(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        opportunity_id, decision_id = _seed_opportunity_and_decision(
            session,
            amount_minor=250000,
            confidence=82,
            expected_net_recovery_minor=12000,
            action="RETRY",
        )

        evaluation = evaluate_policy_for_decision(
            session,
            opportunity_id=opportunity_id,
            decision_id=decision_id,
        )

        assert evaluation.result == "ALLOW"
        assert evaluation.max_amount_check is True
        assert evaluation.confidence_check is True
        assert evaluation.retry_limit_check is True
        assert evaluation.economic_check is True
        assert evaluation.duplicate_check is True
        assert evaluation.environment_check is True
        assert evaluation.reason_codes["failed"] == []
        assert evaluation.evaluated_rules["allowlisted_action"]["passed"] is True
    finally:
        session.close()


def test_policy_engine_blocks_with_deterministic_reason_codes(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        opportunity_id, decision_id = _seed_opportunity_and_decision(
            session,
            amount_minor=1250000,
            confidence=80,
            expected_net_recovery_minor=-500,
            action="RETRY",
        )

        evaluation = evaluate_policy_for_decision(
            session,
            opportunity_id=opportunity_id,
            decision_id=decision_id,
        )

        assert evaluation.result == "BLOCK"
        assert "POLICY_max_amount_FAILED" in evaluation.reason_codes["failed"]
        assert "POLICY_expected_net_FAILED" in evaluation.reason_codes["failed"]
    finally:
        session.close()

