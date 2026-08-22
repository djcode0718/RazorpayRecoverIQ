import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import get_session_local, init_db, reset_db_runtime
from app.evaluation import generate_synthetic_cases, run_baseline_evaluation
from app.main import create_app
from app.models import AuditEvent, EvaluationCase, EvaluationResult


def _build_session(tmp_path: Path):
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase3.db'}"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return get_session_local()()


def _build_client(tmp_path: Path) -> TestClient:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase3_api.db'}"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app())


def test_generate_synthetic_cases_is_deterministic(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        split_counts = generate_synthetic_cases(
            session,
            dataset_version="v1",
            generation_seed=42,
            total_cases=40,
        )
        assert split_counts == {"total": 40, "development": 28, "validation": 6, "test": 6}

        first_run = session.execute(
            select(EvaluationCase)
            .where(EvaluationCase.dataset_version == "v1")
            .order_by(EvaluationCase.id)
        ).scalars().all()
        first_snapshot = [
            (
                c.case_type,
                c.payment_features["amount_minor"],
                c.failure_features["reason"],
                c.ground_truth_recoverable,
                c.split,
            )
            for c in first_run[:8]
        ]

        split_counts_again = generate_synthetic_cases(
            session,
            dataset_version="v1",
            generation_seed=42,
            total_cases=40,
        )
        assert split_counts_again == split_counts

        second_run = session.execute(
            select(EvaluationCase)
            .where(EvaluationCase.dataset_version == "v1")
            .order_by(EvaluationCase.id)
        ).scalars().all()
        second_snapshot = [
            (
                c.case_type,
                c.payment_features["amount_minor"],
                c.failure_features["reason"],
                c.ground_truth_recoverable,
                c.split,
            )
            for c in second_run[:8]
        ]

        assert first_snapshot == second_snapshot
    finally:
        session.close()


def test_run_baseline_evaluation_uses_same_dataset_and_persists_results(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    try:
        generate_synthetic_cases(session, dataset_version="v_eval", generation_seed=7, total_cases=60)
        summary = run_baseline_evaluation(session, dataset_version="v_eval", split="TEST", evaluation_run_id="run_test_001")

        test_case_count = session.execute(
            select(func.count()).select_from(EvaluationCase).where(EvaluationCase.dataset_version == "v_eval").where(EvaluationCase.split == "TEST")
        ).scalar_one()
        result_count = session.execute(
            select(func.count()).select_from(EvaluationResult).where(EvaluationResult.evaluation_run_id == "run_test_001")
        ).scalar_one()

        assert summary.records == test_case_count
        assert result_count == test_case_count
        assert summary.evaluation_run_id == "run_test_001"
        assert 0.0 <= summary.precision <= 1.0
        assert 0.0 <= summary.recall <= 1.0
        assert 0.0 <= summary.f1 <= 1.0
        assert summary.revenue_at_risk_minor >= summary.gross_recovered_minor
        assert summary.false_positive_count >= 0
        assert summary.false_positive_exposure_minor >= 0
        assert summary.recovery_rate >= 0.0
    finally:
        session.close()


def test_evaluation_run_endpoint_executes_and_returns_summary(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    response = client.post(
        "/api/v1/evaluation/run",
        json={
            "dataset_version": "api_eval_v1",
            "split": "TEST",
            "generation_seed": 17,
            "total_cases": 40,
            "evaluation_run_id": "run_api_001",
            "generate_if_missing": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["evaluation_run_id"] == "run_api_001"
    assert payload["data"]["records"] == 6
    assert 0.0 <= payload["data"]["precision"] <= 1.0
    assert "operational" in payload["data"]

    session = get_session_local()()
    try:
        audits = session.execute(
            select(AuditEvent).where(AuditEvent.event_type == "evaluation.completed")
        ).scalars().all()
        assert len(audits) == 1
        assert audits[0].entity_type == "EvaluationRun"
    finally:
        session.close()


def test_evaluation_get_endpoint_returns_existing_run_and_404_for_missing(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    run_response = client.post(
        "/api/v1/evaluation/run",
        json={
            "dataset_version": "api_eval_v2",
            "split": "TEST",
            "generation_seed": 23,
            "total_cases": 40,
            "evaluation_run_id": "run_api_002",
            "generate_if_missing": True,
        },
    )
    assert run_response.status_code == 200

    get_ok = client.get("/api/v1/evaluation/run_api_002")
    assert get_ok.status_code == 200
    ok_payload = get_ok.json()
    assert ok_payload["success"] is True
    assert ok_payload["data"]["evaluation_run_id"] == "run_api_002"
    assert ok_payload["data"]["records"] == 6

    get_missing = client.get("/api/v1/evaluation/not_found_run")
    assert get_missing.status_code == 404
    missing_payload = get_missing.json()
    assert missing_payload["success"] is False
    assert missing_payload["error"]["code"] == "EVAL_RUN_NOT_FOUND"
