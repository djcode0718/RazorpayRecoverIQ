import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.main import create_app
from app.models import PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RevenueOpportunity


def _build_test_client(tmp_path: Path, *, adapter_mode: str = "simulation") -> TestClient:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'test.db'}"
    os.environ["PAYMENT_ADAPTER_MODE"] = adapter_mode
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    app = create_app()
    return TestClient(app)


def test_health_endpoint(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "ok"


def test_readiness_endpoint(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)
    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "ready"


def test_dashboard_summary_contract(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["mode"] == "simulation"
    assert payload["data"]["mode_label"] == "Simulation Mode"
    assert payload["data"]["revenue_at_risk_minor"] == 0
    assert payload["data"]["recoverable_revenue_minor"] == 0
    assert payload["data"]["recovery_attempts"] == 0
    assert payload["data"]["gross_recovered_minor"] == 0
    assert payload["data"]["net_recovered_minor"] == 0


def test_dashboard_summary_aggregates_seeded_data(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)

    session = get_session_local()()
    try:
        opportunity_open = RevenueOpportunity(
            customer_id=1,
            payment_id=1,
            order_id=1,
            subscription_id=None,
            source_event_id=None,
            amount_at_risk_minor=10_000,
            currency="INR",
            failure_category="transient",
            failure_reason="network",
            recovery_probability=75,
            recovery_score=78,
            expected_recovery_minor=7_500,
            estimated_intervention_cost_minor=200,
            expected_net_recovery_minor=7_300,
            recommended_action="RETRY",
            confidence=80,
            status="OPEN",
            expires_at=None,
        )
        opportunity_resolved = RevenueOpportunity(
            customer_id=2,
            payment_id=2,
            order_id=2,
            subscription_id=None,
            source_event_id=None,
            amount_at_risk_minor=5_000,
            currency="INR",
            failure_category="bank",
            failure_reason="insufficient_funds",
            recovery_probability=50,
            recovery_score=55,
            expected_recovery_minor=2_500,
            estimated_intervention_cost_minor=500,
            expected_net_recovery_minor=2_000,
            recommended_action="ESCALATE",
            confidence=72,
            status="RESOLVED",
            expires_at=None,
        )
        session.add_all([opportunity_open, opportunity_resolved])
        session.commit()
        session.refresh(opportunity_open)
        session.refresh(opportunity_resolved)

        decision_open = RecoveryDecision(
            opportunity_id=opportunity_open.id,
            diagnosis="retry candidate",
            evidence={"source": "test"},
            recovery_probability=75,
            confidence=80,
            recommended_action="RETRY",
            expected_recovery_minor=7_500,
            estimated_cost_minor=200,
            expected_net_recovery_minor=7_300,
            decision_source="MOCK",
            provider="mock",
            model="mock-v1",
            model_version="v1",
            prompt_version="p1",
            schema_version="phase5-v1",
        )
        decision_escalate = RecoveryDecision(
            opportunity_id=opportunity_resolved.id,
            diagnosis="manual review",
            evidence={"source": "test"},
            recovery_probability=50,
            confidence=72,
            recommended_action="ESCALATE",
            expected_recovery_minor=2_500,
            estimated_cost_minor=500,
            expected_net_recovery_minor=2_000,
            decision_source="MOCK",
            provider="mock",
            model="mock-v1",
            model_version="v1",
            prompt_version="p1",
            schema_version="v1.0",
        )
        session.add_all([decision_open, decision_escalate])
        session.commit()
        session.refresh(decision_open)
        session.refresh(decision_escalate)

        policy_allow = PolicyEvaluation(
            opportunity_id=opportunity_open.id,
            decision_id=decision_open.id,
            result="ALLOW",
            reason_codes={"failed": [], "passed": ["POLICY_test_PASSED"]},
            evaluated_rules={"seeded": {"passed": True}},
            max_amount_check=True,
            confidence_check=True,
            retry_limit_check=True,
            economic_check=True,
            duplicate_check=True,
            environment_check=True,
            policy_version="v1.0",
        )
        policy_deny = PolicyEvaluation(
            opportunity_id=opportunity_resolved.id,
            decision_id=decision_escalate.id,
            result="BLOCK",
            reason_codes={"failed": ["POLICY_test_FAILED"], "passed": []},
            evaluated_rules={"seeded": {"passed": False}},
            max_amount_check=False,
            confidence_check=True,
            retry_limit_check=True,
            economic_check=True,
            duplicate_check=True,
            environment_check=True,
            policy_version="v1.0",
        )
        session.add_all([policy_allow, policy_deny])
        session.commit()
        session.refresh(policy_allow)
        session.refresh(policy_deny)

        attempt_success = RecoveryAttempt(
            opportunity_id=opportunity_open.id,
            action="RETRY",
            attempt_number=1,
            policy_evaluation_id=policy_allow.id,
            status="VERIFIED",
            amount_minor=10_000,
            currency="INR",
            failure_code=None,
            failure_reason=None,
            verified_outcome="VERIFIED_SUCCESS",
            recovered_amount_minor=5_000,
        )
        attempt_failed = RecoveryAttempt(
            opportunity_id=opportunity_resolved.id,
            action="RECOVERY_PROMPT",
            attempt_number=1,
            policy_evaluation_id=policy_deny.id,
            status="VERIFIED",
            amount_minor=5_000,
            currency="INR",
            failure_code="DENIED",
            failure_reason="policy denied",
            verified_outcome="VERIFIED_FAILURE",
            recovered_amount_minor=0,
        )
        session.add_all([attempt_success, attempt_failed])
        session.commit()
    finally:
        session.close()

    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["revenue_at_risk_minor"] == 15_000
    assert payload["data"]["recoverable_revenue_minor"] == 10_000
    assert payload["data"]["recovery_attempts"] == 2
    assert payload["data"]["gross_recovered_minor"] == 5_000
    assert payload["data"]["net_recovered_minor"] == 4_300
    assert payload["data"]["recovery_rate"] == 0.5
    assert payload["data"]["active_opportunities"] == 1
    assert payload["data"]["approved_actions"] == 1
    assert payload["data"]["allowed_actions"] == 1
    assert payload["data"]["blocked_actions"] == 1
    assert payload["data"]["escalations"] == 1
    assert payload["data"]["escalated_actions"] == 1


def test_demo_reset_endpoint_contract(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path, adapter_mode="simulation")
    response = client.post("/api/v1/demo/reset-core-recovery")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "reset"
    assert payload["data"]["mode"] == "simulation"


def test_dashboard_summary_mode_reflects_razorpay_test(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path, adapter_mode="razorpay_test")
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["mode"] == "razorpay_test"
    assert payload["data"]["mode_label"] == "Razorpay Test Mode"


def test_dashboard_trend_endpoint_contract(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)
    response = client.get("/api/v1/dashboard/trend")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["data"], list)
    assert len(payload["data"]) == 7
    for point in payload["data"]:
        assert "date" in point
        assert "display_date" in point
        assert "revenue_at_risk_minor" in point
        assert "recovered_revenue_minor" in point
        assert "attempts_count" in point


def test_dashboard_events_endpoint_contract(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)
    response = client.get("/api/v1/dashboard/events?limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["data"], list)


