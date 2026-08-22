import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.main import create_app
from app.models import AuditEvent, Payment, PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RevenueOpportunity


def _build_client(tmp_path: Path) -> TestClient:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase10.db'}"
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app())


def _seed_opportunity_chain() -> int:
    session = get_session_local()()
    try:
        payment = Payment(
            razorpay_payment_id="pay_phase10_001",
            razorpay_order_id="order_phase10_001",
            customer_id=1,
            amount_minor=20_000,
            currency="INR",
            status="FAILED",
            method="card",
            captured=False,
            failure_code="NETWORK",
            failure_description="gateway timeout",
            failure_source="network",
            failure_step="authorize",
            failure_reason="network_error",
        )
        session.add(payment)
        session.commit()
        session.refresh(payment)

        opportunity = RevenueOpportunity(
            customer_id=1,
            payment_id=payment.id,
            order_id=1,
            subscription_id=None,
            source_event_id=1,
            amount_at_risk_minor=20_000,
            currency="INR",
            failure_category="transient",
            failure_reason="network",
            recovery_probability=70,
            recovery_score=73,
            expected_recovery_minor=14_000,
            estimated_intervention_cost_minor=200,
            expected_net_recovery_minor=13_800,
            recommended_action="RETRY",
            confidence=79,
            status="OPEN",
            expires_at=None,
        )
        session.add(opportunity)
        session.commit()
        session.refresh(opportunity)

        decision = RecoveryDecision(
            opportunity_id=opportunity.id,
            diagnosis="customer has high success history",
            evidence={"reason": "historical success", "risk_bucket": "medium"},
            recovery_probability=70,
            confidence=79,
            recommended_action="RETRY",
            expected_recovery_minor=14_000,
            estimated_cost_minor=200,
            expected_net_recovery_minor=13_800,
            decision_source="AI_AND_RULES",
            provider="mock",
            model="mock-v2",
            model_version="v2",
            prompt_version="p2",
            schema_version="phase5-v1",
        )
        session.add(decision)
        session.commit()
        session.refresh(decision)

        policy = PolicyEvaluation(
            opportunity_id=opportunity.id,
            decision_id=decision.id,
            result="ALLOW",
            reason_codes={"failed": [], "passed": ["POLICY_economic_PASSED", "POLICY_confidence_PASSED"]},
            evaluated_rules={"seeded": {"passed": True}},
            max_amount_check=True,
            confidence_check=True,
            retry_limit_check=True,
            economic_check=True,
            duplicate_check=True,
            environment_check=True,
            policy_version="phase6-v1",
        )
        session.add(policy)
        session.commit()
        session.refresh(policy)

        attempt = RecoveryAttempt(
            opportunity_id=opportunity.id,
            action="RETRY",
            attempt_number=1,
            policy_evaluation_id=policy.id,
            status="VERIFIED",
            amount_minor=20_000,
            currency="INR",
            failure_code=None,
            failure_reason=None,
            verified_outcome="VERIFIED_SUCCESS",
            recovered_amount_minor=8_000,
        )
        session.add(attempt)

        session.add_all(
            [
                AuditEvent(
                    event_type="workflow.stage.detection",
                    actor_type="system",
                    actor_id="workflow",
                    entity_type="RecoveryWorkflow",
                    entity_id="payment:pay_phase10_001",
                    reason="failed payment detected",
                    outcome_snapshot={"status": "detected"},
                ),
                AuditEvent(
                    event_type="workflow.stage.policy",
                    actor_type="system",
                    actor_id="workflow",
                    entity_type="RecoveryWorkflow",
                    entity_id="payment:pay_phase10_001",
                    reason="policy allow",
                    outcome_snapshot={"status": "allow"},
                ),
            ]
        )

        session.commit()
        return opportunity.id
    finally:
        session.close()


def test_phase10_opportunities_list_and_detail(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    opportunity_id = _seed_opportunity_chain()

    list_response = client.get("/api/v1/opportunities")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["success"] is True
    assert list_payload["data"]["count"] == 1
    assert list_payload["data"]["items"][0]["id"] == opportunity_id
    assert list_payload["data"]["items"][0]["customer_reference"] == "CUST-1"
    assert list_payload["data"]["items"][0]["policy_result"] == "ALLOW"

    detail_response = client.get(f"/api/v1/opportunities/{opportunity_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["success"] is True
    assert detail_payload["data"]["payment"]["razorpay_payment_id"] == "pay_phase10_001"
    assert detail_payload["data"]["customer_history"]["customer_id"] == 1
    assert detail_payload["data"]["failure"]["reason"] == "network"
    assert detail_payload["data"]["evidence"]["diagnosis"] == "customer has high success history"
    assert detail_payload["data"]["economics"]["expected_recovery_minor"] == 14_000
    assert detail_payload["data"]["policy_checks"]["result"] == "ALLOW"
    assert detail_payload["data"]["policy_checks"]["checks"]["confidence_check"] is True
    assert detail_payload["data"]["policy_checks"]["checks"]["amount_check"] is True
    assert detail_payload["data"]["policy_checks"]["checks"]["expected_recovery_check"] is True
    assert detail_payload["data"]["recovery_state"]["current"] in {"Successful", "Verified", "Recovered"}
    assert detail_payload["data"]["action_traceability"]["latest_verified_outcome"] == "VERIFIED_SUCCESS"
    assert len(detail_payload["data"]["timeline"]) == 2
    assert len(detail_payload["data"]["audit_trail"]) == 2
    assert detail_payload["data"]["timeline"][0]["stage"] == "detection"
    assert detail_payload["data"]["timeline"][0]["stage_group"] == "Signal"
    assert detail_payload["data"]["timeline"][0]["outcome_status"] == "pass"
    assert detail_payload["data"]["timeline_groups"][0]["group"] == "Signal"


def test_phase10_opportunities_filters_search_and_sort(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    _ = _seed_opportunity_chain()

    list_filtered = client.get("/api/v1/opportunities?status=OPEN&action=RETRY&risk_bucket=medium&search=network&sort_by=risk_desc")
    assert list_filtered.status_code == 200
    payload = list_filtered.json()
    assert payload["success"] is True
    assert payload["data"]["count"] == 1
    assert payload["data"]["items"][0]["risk_bucket"] == "medium"
    assert payload["data"]["filters"]["sort_by"] == "risk_desc"


def test_phase10_opportunities_pagination_metadata(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    _ = _seed_opportunity_chain()

    session = get_session_local()()
    try:
        for idx in range(2, 7):
            session.add(
                RevenueOpportunity(
                    customer_id=idx,
                    payment_id=None,
                    order_id=None,
                    subscription_id=None,
                    source_event_id=None,
                    amount_at_risk_minor=10_000 + idx,
                    currency="INR",
                    failure_category="network",
                    failure_reason="retry",
                    recovery_probability=65,
                    recovery_score=66,
                    expected_recovery_minor=5_000,
                    estimated_intervention_cost_minor=200,
                    expected_net_recovery_minor=4_800,
                    recommended_action="RETRY",
                    confidence=70,
                    status="OPEN",
                    expires_at=None,
                )
            )
        session.commit()
    finally:
        session.close()

    page_one = client.get("/api/v1/opportunities?page=1&page_size=2&sort_by=updated_desc")
    assert page_one.status_code == 200
    payload_one = page_one.json()
    assert payload_one["success"] is True
    assert payload_one["data"]["count"] == 2
    assert payload_one["data"]["page"] == 1
    assert payload_one["data"]["page_size"] == 2
    assert payload_one["data"]["total_count"] == 6
    assert payload_one["data"]["total_pages"] == 3
    assert payload_one["data"]["has_next"] is True
    assert payload_one["data"]["has_prev"] is False

    page_three = client.get("/api/v1/opportunities?page=3&page_size=2&sort_by=updated_desc")
    assert page_three.status_code == 200
    payload_three = page_three.json()
    assert payload_three["data"]["count"] == 2
    assert payload_three["data"]["has_next"] is False
    assert payload_three["data"]["has_prev"] is True


def test_phase10_opportunities_cursor_pagination_mode(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    _ = _seed_opportunity_chain()

    session = get_session_local()()
    try:
        for idx in range(2, 12):
            session.add(
                RevenueOpportunity(
                    customer_id=idx,
                    payment_id=None,
                    order_id=None,
                    subscription_id=None,
                    source_event_id=None,
                    amount_at_risk_minor=10_000 + idx,
                    currency="INR",
                    failure_category="network",
                    failure_reason="retry",
                    recovery_probability=66,
                    recovery_score=67,
                    expected_recovery_minor=5_000,
                    estimated_intervention_cost_minor=200,
                    expected_net_recovery_minor=4_800,
                    recommended_action="RETRY",
                    confidence=71,
                    status="OPEN",
                    expires_at=None,
                )
            )
        session.commit()
    finally:
        session.close()

    page_one = client.get("/api/v1/opportunities?pagination_mode=cursor&page_size=3&sort_by=updated_desc")
    assert page_one.status_code == 200
    payload_one = page_one.json()
    assert payload_one["success"] is True
    assert payload_one["data"]["pagination_mode"] == "cursor"
    assert payload_one["data"]["count"] == 3
    assert payload_one["data"]["next_cursor"] is not None
    assert payload_one["data"]["has_next"] is True

    page_two = client.get(
        f"/api/v1/opportunities?pagination_mode=cursor&page_size=3&sort_by=updated_desc&cursor={payload_one['data']['next_cursor']}"
    )
    assert page_two.status_code == 200
    payload_two = page_two.json()
    assert payload_two["data"]["pagination_mode"] == "cursor"
    assert payload_two["data"]["count"] == 3
    assert payload_two["data"]["has_prev"] is True


def test_phase10_cursor_pagination_rejects_unsupported_sort(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    _ = _seed_opportunity_chain()

    response = client.get("/api/v1/opportunities?pagination_mode=cursor&page_size=3&sort_by=risk_desc")
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "CURSOR_SORT_NOT_SUPPORTED"


def test_phase10_cursor_pagination_rejects_invalid_cursor(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    _ = _seed_opportunity_chain()

    response = client.get("/api/v1/opportunities?pagination_mode=cursor&page_size=3&sort_by=updated_desc&cursor=invalid-token")
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_CURSOR"


def test_phase10_opportunity_detail_not_found(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    response = client.get("/api/v1/opportunities/999999")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "OPPORTUNITY_NOT_FOUND"


def test_phase10_opportunity_evaluate_execute_explanation_and_audit(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    opportunity_id = _seed_opportunity_chain()

    explanation_response = client.get(f"/api/v1/opportunities/{opportunity_id}/explanation")
    assert explanation_response.status_code == 200
    explanation_payload = explanation_response.json()
    assert explanation_payload["success"] is True
    assert explanation_payload["data"]["recommended_action"] is not None

    evaluate_response = client.post(f"/api/v1/opportunities/{opportunity_id}/evaluate")
    assert evaluate_response.status_code == 200
    evaluate_payload = evaluate_response.json()
    assert evaluate_payload["success"] is True
    assert evaluate_payload["data"]["policy_result"] in {"ALLOW", "BLOCK", "ESCALATE"}

    execute_response = client.post(f"/api/v1/opportunities/{opportunity_id}/execute")
    if execute_response.status_code == 200:
        execute_payload = execute_response.json()
        assert execute_payload["success"] is True
        assert execute_payload["data"]["payment_link"] is not None
    else:
        assert execute_response.status_code == 409
        execute_payload = execute_response.json()
        assert execute_payload["success"] is False
        assert execute_payload["error"]["code"] in {"POLICY_NOT_ALLOW", "EXECUTION_BLOCKED"}

    audit_response = client.get(f"/api/v1/opportunities/{opportunity_id}/audit")
    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert audit_payload["success"] is True
    assert "items" in audit_payload["data"]
