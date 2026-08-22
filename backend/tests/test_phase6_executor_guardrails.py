import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.gateway_adapters import PaymentAdapterTimeoutError
from app.models import Payment, PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RecoveryPaymentLink, RevenueOpportunity
from app.recovery_executor import execute_recovery_attempt


def _build_session(tmp_path: Path) -> Session:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase6_executor.db'}"
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return get_session_local()()


def _seed_entities(session: Session, *, action: str, policy_result: str) -> tuple[int, int, int]:
    payment = Payment(
        razorpay_payment_id=f"pay_executor_{action}_{policy_result}",
        razorpay_order_id="order_executor",
        customer_id=None,
        amount_minor=225000,
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
        amount_at_risk_minor=225000,
        currency="INR",
        failure_category="NETWORK",
        failure_reason="network",
        recovery_probability=72,
        recovery_score=72,
        expected_recovery_minor=162000,
        estimated_intervention_cost_minor=200,
        expected_net_recovery_minor=161800,
        recommended_action=action,
        confidence=85,
        status="DETECTED",
        expires_at=None,
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    decision = RecoveryDecision(
        opportunity_id=opportunity.id,
        diagnosis="Deterministic phase 6 executor test diagnosis with enough characters.",
        evidence={"signals": [{"signal": "failure_reason", "value": "network"}]},
        recovery_probability=72,
        confidence=85,
        recommended_action=action,
        expected_recovery_minor=162000,
        estimated_cost_minor=200,
        expected_net_recovery_minor=161800,
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

    evaluation = PolicyEvaluation(
        opportunity_id=opportunity.id,
        decision_id=decision.id,
        result=policy_result,
        reason_codes={"failed": [], "passed": ["all"]},
        evaluated_rules={"seeded": {"passed": True}},
        max_amount_check=True,
        confidence_check=True,
        retry_limit_check=True,
        economic_check=True,
        duplicate_check=True,
        environment_check=True,
        policy_version="phase6-v1",
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)
    return opportunity.id, decision.id, evaluation.id


def test_executor_blocks_when_policy_not_allow(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        opportunity_id, decision_id, evaluation_id = _seed_entities(
            session,
            action="RETRY",
            policy_result="BLOCK",
        )

        with pytest.raises(ValueError, match="policy_not_allow"):
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity_id,
                decision_id=decision_id,
                policy_evaluation_id=evaluation_id,
            )

        attempts = session.execute(select(RecoveryAttempt)).scalars().all()
        assert attempts == []
    finally:
        session.close()


def test_executor_guardrail_blocks_non_executable_action(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        opportunity_id, decision_id, evaluation_id = _seed_entities(
            session,
            action="ESCALATE",
            policy_result="ALLOW",
        )

        with pytest.raises(ValueError, match="action_not_executable"):
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity_id,
                decision_id=decision_id,
                policy_evaluation_id=evaluation_id,
            )

        attempts = session.execute(select(RecoveryAttempt)).scalars().all()
        assert attempts == []
    finally:
        session.close()


def test_executor_creates_attempt_for_allow_with_guardrails(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        opportunity_id, decision_id, evaluation_id = _seed_entities(
            session,
            action="RETRY",
            policy_result="ALLOW",
        )

        attempt = execute_recovery_attempt(
            session,
            opportunity_id=opportunity_id,
            decision_id=decision_id,
            policy_evaluation_id=evaluation_id,
        )

        assert attempt.status == "EXECUTED"
        assert attempt.attempt_number == 1
        assert attempt.action == "CREATE_PAYMENT_LINK"
        assert attempt.recovered_amount_minor == 0
        assert attempt.external_reference is not None

        link = session.execute(
            select(RecoveryPaymentLink).where(RecoveryPaymentLink.recovery_attempt_id == attempt.id)
        ).scalar_one()
        assert link.payment_link_id == attempt.external_reference
        assert link.status == "CREATED"
    finally:
        session.close()


def test_executor_reuses_existing_open_payment_link_attempt(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        opportunity_id, decision_id, evaluation_id = _seed_entities(
            session,
            action="RETRY",
            policy_result="ALLOW",
        )

        first = execute_recovery_attempt(
            session,
            opportunity_id=opportunity_id,
            decision_id=decision_id,
            policy_evaluation_id=evaluation_id,
        )
        second = execute_recovery_attempt(
            session,
            opportunity_id=opportunity_id,
            decision_id=decision_id,
            policy_evaluation_id=evaluation_id,
        )

        assert second.id == first.id
        attempts = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity_id)
        ).scalars().all()
        assert len(attempts) == 1
        links = session.execute(
            select(RecoveryPaymentLink).where(RecoveryPaymentLink.opportunity_id == opportunity_id)
        ).scalars().all()
        assert len(links) == 1
    finally:
        session.close()


def test_executor_marks_attempt_failed_on_adapter_timeout(tmp_path: Path, monkeypatch) -> None:
    class _TimeoutAdapter:
        def create_payment_link(self, request):
            raise PaymentAdapterTimeoutError("timeout")

    session = _build_session(tmp_path)
    try:
        opportunity_id, decision_id, evaluation_id = _seed_entities(
            session,
            action="RETRY",
            policy_result="ALLOW",
        )

        monkeypatch.setattr("app.recovery_executor.get_payment_adapter", lambda settings: _TimeoutAdapter())

        with pytest.raises(ValueError, match="adapter_timeout"):
            execute_recovery_attempt(
                session,
                opportunity_id=opportunity_id,
                decision_id=decision_id,
                policy_evaluation_id=evaluation_id,
            )

        attempts = session.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity_id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].status == "FAILED"
        assert attempts[0].failure_code == "ADAPTER_TIMEOUT"

        links = session.execute(
            select(RecoveryPaymentLink).where(RecoveryPaymentLink.opportunity_id == opportunity_id)
        ).scalars().all()
        assert links == []
    finally:
        session.close()
