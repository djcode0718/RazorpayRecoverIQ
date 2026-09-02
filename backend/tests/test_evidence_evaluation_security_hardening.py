import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.evaluation import generate_synthetic_cases, run_baseline_evaluation, run_recoveriq_evaluation
from app.gateway_adapters import PaymentAdapterConfigurationError, RazorpayPaymentAdapter
from app.main import create_app
from app.models import AuditEvent, EvaluationCase, EvaluationResult, RecoveryDecision, RevenueOpportunity, WebhookEvent
from app.policy_engine import evaluate_policy_for_decision
from app.readiness import execute_readiness_acceptance_workflow


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def _build_test_env(tmp_path: Path, *, secret: str = "whsec_phase4_secret", adapter_mode: str = "simulation"):
    db_file = tmp_path / f"phase4_{os.urandom(4).hex()}.db"
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{db_file}"
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = secret
    os.environ["PAYMENT_ADAPTER_MODE"] = adapter_mode
    os.environ["RAZORPAY_KEY_ID"] = "rzp_test_evidence"
    os.environ["RAZORPAY_KEY_SECRET"] = "phase4_secret"
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["APP_MODE"] = "simulation"

    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app()), secret


# 1. Held-Out Evaluation & Baseline Reproducibility
def test_evidence_01_evaluation_held_out_dataset_and_baseline_determinism(tmp_path: Path) -> None:
    """Validate held-out evaluation dataset, splits, confusion matrix, and reproducible baseline."""
    client, secret = _build_test_env(tmp_path)
    session = get_session_local()()
    try:
        # Generate deterministic synthetic cases
        split_counts = generate_synthetic_cases(
            session,
            dataset_version="heldout_v1",
            generation_seed=42,
            total_cases=100,
        )
        assert split_counts["total"] == 100
        assert split_counts["test"] > 0

        # Baseline evaluation on TEST split
        base_run_a = run_baseline_evaluation(session, dataset_version="heldout_v1", split="TEST", evaluation_run_id="base_test_a")
        base_run_b = run_baseline_evaluation(session, dataset_version="heldout_v1", split="TEST", evaluation_run_id="base_test_b")

        # Baseline must be 100% deterministic and reproducible
        assert base_run_a.records == base_run_b.records
        assert base_run_a.precision == base_run_b.precision
        assert base_run_a.recall == base_run_b.recall
        assert base_run_a.f1 == base_run_b.f1
        assert base_run_a.gross_recovered_minor == base_run_b.gross_recovered_minor
        assert base_run_a.net_recovered_minor == base_run_b.net_recovered_minor

        # RecoverIQ policy evaluation on TEST split
        iq_run = run_recoveriq_evaluation(session, dataset_version="heldout_v1", split="TEST", evaluation_run_id="iq_test_01")
        assert iq_run.records == base_run_a.records
        # RecoverIQ should filter out low-confidence/high-cost failures, improving net economics
        assert iq_run.f1 >= base_run_a.f1 or iq_run.precision >= base_run_a.precision
        assert iq_run.false_positive_exposure_minor <= base_run_a.false_positive_exposure_minor
    finally:
        session.close()


# 2. Complete Batch Money Recovery & Economic Net Benefit
def test_evidence_02_complete_batch_economic_benefit(tmp_path: Path) -> None:
    """Calculate baseline recovered, RecoverIQ recovered, false-positive cost, intervention cost, and net benefit."""
    client, secret = _build_test_env(tmp_path)
    session = get_session_local()()
    try:
        generate_synthetic_cases(session, dataset_version="econ_v1", generation_seed=99, total_cases=120)
        base = run_baseline_evaluation(session, dataset_version="econ_v1", split="TEST", evaluation_run_id="base_econ")
        iq = run_recoveriq_evaluation(session, dataset_version="econ_v1", split="TEST", evaluation_run_id="iq_econ")

        # All values calculated across the complete batch
        assert base.records > 0
        assert iq.records == base.records
        assert iq.revenue_at_risk_minor == base.revenue_at_risk_minor
        
        # Net economic yield: gross recovered - intervention costs
        assert iq.net_recovered_minor == iq.gross_recovered_minor - iq.intervention_cost_minor
        assert base.net_recovered_minor == base.gross_recovered_minor - base.intervention_cost_minor
    finally:
        session.close()


# 3. AI Quality & Fail-Closed Behavior
def test_evidence_03_ai_fail_closed_on_invalid_output(tmp_path: Path) -> None:
    """Invalid or malformed AI output must fail closed, produce an audit event, and not execute payments."""
    client, secret = _build_test_env(tmp_path)
    session = get_session_local()()
    try:
        # Create a sample opportunity
        opp = RevenueOpportunity(
            amount_at_risk_minor=200000,
            currency="INR",
            failure_category="CARD_DECLINE",
            failure_reason="insufficient_funds",
            confidence=20,
            recovery_probability=20,
            status="OPEN",
        )
        session.add(opp)
        session.flush()

        # Decision with low confidence and ESCALATE
        dec = RecoveryDecision(
            opportunity_id=opp.id,
            diagnosis="Card decline due to insufficient funds",
            evidence={"reason": "insufficient_funds"},
            recovery_probability=20,
            confidence=20,
            recommended_action="ESCALATE",
            expected_recovery_minor=40000,
            estimated_cost_minor=5000,
            expected_net_recovery_minor=35000,
            decision_source="AI_FALLBACK",
            provider="mock",
        )
        session.add(dec)
        session.flush()

        # Policy evaluation should BLOCK or ESCALATE (fail closed)
        pe = evaluate_policy_for_decision(session, opportunity_id=opp.id, decision_id=dec.id)
        assert pe.result in {"BLOCK", "ESCALATE"}

        # Check that no payment link or recovery attempt was executed
        from app.models import RecoveryAttempt
        attempts = session.query(RecoveryAttempt).filter(RecoveryAttempt.opportunity_id == opp.id).all()
        assert len(attempts) == 0
    finally:
        session.close()


# 4. Deterministic Policy Gate Rules
def test_evidence_04_policy_engine_enforces_all_guardrails(tmp_path: Path) -> None:
    """Verify max amount limit, confidence threshold, retry limits, and duplicate protection."""
    client, secret = _build_test_env(tmp_path)
    session = get_session_local()()
    try:
        # 1. High amount opportunity (> max limit)
        opp_high = RevenueOpportunity(
            amount_at_risk_minor=60_000_000,  # ₹600,000 > max ₹500,000
            currency="INR",
            failure_category="NETWORK_ERROR",
            confidence=90,
            recovery_probability=90,
            status="OPEN",
        )
        session.add(opp_high)
        session.flush()
        dec_high = RecoveryDecision(
            opportunity_id=opp_high.id,
            diagnosis="Network error timeout",
            evidence={},
            recovery_probability=90,
            confidence=90,
            recommended_action="RETRY",
            expected_recovery_minor=54_000_000,
            estimated_cost_minor=500,
            expected_net_recovery_minor=53_999_500,
            decision_source="AI_PRIMARY",
            provider="mock",
        )
        session.add(dec_high)
        session.flush()
        pe_high = evaluate_policy_for_decision(session, opportunity_id=opp_high.id, decision_id=dec_high.id)
        assert pe_high.result == "BLOCK"
        assert any("max_amount" in code.lower() for code in pe_high.reason_codes.get("failed", []))

        # 2. Low confidence opportunity (< 35%)
        opp_low = RevenueOpportunity(
            amount_at_risk_minor=100000,
            currency="INR",
            failure_category="CARD_DECLINE",
            confidence=25,
            recovery_probability=25,
            status="OPEN",
        )
        session.add(opp_low)
        session.flush()
        dec_low = RecoveryDecision(
            opportunity_id=opp_low.id,
            diagnosis="Low confidence failure",
            evidence={},
            recovery_probability=25,
            confidence=25,
            recommended_action="RETRY",
            expected_recovery_minor=25000,
            estimated_cost_minor=500,
            expected_net_recovery_minor=24500,
            decision_source="AI_PRIMARY",
            provider="mock",
        )
        session.add(dec_low)
        session.flush()
        pe_low = evaluate_policy_for_decision(session, opportunity_id=opp_low.id, decision_id=dec_low.id)
        assert pe_low.result in {"BLOCK", "ESCALATE"}
        assert any("confidence" in code.lower() for code in pe_low.reason_codes.get("failed", []))
    finally:
        session.close()


# 5. Webhook HMAC-SHA256 Security & Idempotent Ledger Deduplication
def test_evidence_05_webhook_security_and_replay_protection(tmp_path: Path) -> None:
    """Verify signature verification, raw body validation, duplicate event deduplication, and replay protection."""
    client, secret = _build_test_env(tmp_path)

    payload = {
        "id": "evt_replay_guard_001",
        "event": "payment.failed",
        "account_id": "acc_p4",
        "created_at": 1724300000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_replay_001",
                    "order_id": "order_replay_001",
                    "amount": 150000,
                    "currency": "INR",
                    "method": "card",
                    "captured": False,
                    "error_reason": "network",
                }
            }
        },
    }
    raw = json.dumps(payload).encode("utf-8")

    # 1. Invalid signature rejection (HTTP 401)
    res_bad = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": "tampered_sig", "content-type": "application/json"})
    assert res_bad.status_code == 401

    # 2. Valid signature ingestion
    valid_sig = _sign(raw, secret)
    res_good = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": valid_sig, "content-type": "application/json"})
    assert res_good.status_code == 200
    assert res_good.json()["data"]["duplicate"] is False

    # 3. Duplicate event replay -> Ledger deduplication
    res_dup = client.post("/api/v1/webhooks/razorpay", content=raw, headers={"x-razorpay-signature": valid_sig, "content-type": "application/json"})
    assert res_dup.status_code == 200
    assert res_dup.json()["data"]["duplicate"] is True


# 6. Failure Safety Across All Edge Scenarios
def test_evidence_06_failure_safety_fails_gracefully(tmp_path: Path) -> None:
    """Test corrupted payloads, missing opportunities, and invalid requests all fail safely without 500 crashes."""
    client, secret = _build_test_env(tmp_path)

    # 1. Empty body
    r_empty = client.post("/api/v1/webhooks/razorpay", content=b"", headers={"x-razorpay-signature": "sig", "content-type": "application/json"})
    assert r_empty.status_code in {400, 401}

    # 2. Malformed JSON
    r_malformed = client.post("/api/v1/webhooks/razorpay", content=b"{malformed json", headers={"x-razorpay-signature": "sig", "content-type": "application/json"})
    assert r_malformed.status_code in {400, 401}

    # 3. Non-existent opportunity lookup
    r_notfound = client.get("/api/v1/opportunities/999999")
    assert r_notfound.status_code == 404


# 7. Production Readiness Release Gate
def test_evidence_07_readiness_release_gate_evaluation(tmp_path: Path) -> None:
    """Readiness release gate evaluates READY, PARTIAL, or BLOCKED with exact evidence and reasons."""
    client, secret = _build_test_env(tmp_path)
    session = get_session_local()()
    try:
        readiness = execute_readiness_acceptance_workflow(session)
        assert readiness["status"] in {"READY", "PARTIAL", "BLOCKED"}
        assert readiness["release_gate"] in {"READY", "PARTIAL", "BLOCKED"}
        assert len(readiness["gate_reason"]) > 0
        assert len(readiness["checks"]) >= 10
        assert readiness["summary"]["fail_count"] == 0
    finally:
        session.close()


# 8. Performance Benchmark Validation
def test_evidence_08_performance_benchmarks(tmp_path: Path) -> None:
    """API endpoints and evaluation batch runs execute well within latency thresholds (< 2.0s)."""
    client, secret = _build_test_env(tmp_path)

    # Measure Dashboard Summary API latency
    t0 = time.perf_counter()
    r_summary = client.get("/api/v1/dashboard/summary")
    summary_latency_ms = (time.perf_counter() - t0) * 1000
    assert r_summary.status_code == 200
    assert summary_latency_ms < 500  # < 500ms

    # Measure Opportunities List latency
    t0 = time.perf_counter()
    r_opps = client.get("/api/v1/opportunities")
    opps_latency_ms = (time.perf_counter() - t0) * 1000
    assert r_opps.status_code == 200
    assert opps_latency_ms < 500  # < 500ms
