import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_db_runtime
from app.main import create_app


def _build_client(tmp_path: Path) -> TestClient:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'phase11.db'}"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app())


def _run_eval(client: TestClient, *, run_id: str) -> None:
    response = client.post(
        "/api/v1/evaluation/run",
        json={
            "dataset_version": "phase11_dataset",
            "split": "TEST",
            "generation_seed": 41,
            "total_cases": 40,
            "evaluation_run_id": run_id,
            "generate_if_missing": True,
        },
    )
    assert response.status_code == 200


def test_evaluation_history_comparison_and_drilldown(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    _run_eval(client, run_id="phase11_run_001")

    history_response = client.get("/api/v1/evaluation/history?limit=5")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert history_payload["success"] is True
    assert history_payload["data"]["count"] >= 1
    assert history_payload["data"]["items"][0]["evaluation_run_id"] == "phase11_run_001"

    comparison_response = client.get("/api/v1/evaluation/phase11_run_001/comparison")
    assert comparison_response.status_code == 200
    comparison_payload = comparison_response.json()
    assert comparison_payload["success"] is True
    assert comparison_payload["data"]["baseline"]["evaluation_run_id"] == "phase11_run_001"
    assert comparison_payload["data"]["recoveriq"]["evaluation_run_id"] == "phase11_run_001:recoveriq_policy"
    assert "f1_delta" in comparison_payload["data"]["deltas"]
    assert "false_positive_rate_delta" in comparison_payload["data"]["deltas"]
    assert "false_positive_exposure_minor_delta" in comparison_payload["data"]["deltas"]
    assert "action_level_deltas" in comparison_payload["data"]["attribution"]
    assert "policy_reason_deltas" in comparison_payload["data"]["attribution"]
    deltas = comparison_payload["data"]["deltas"]
    assert any(
        abs(deltas[key]) > 0
        for key in ["precision_delta", "recall_delta", "f1_delta", "net_recovered_minor_delta"]
    )

    drilldown_response = client.get("/api/v1/evaluation/phase11_run_001/drilldown")
    assert drilldown_response.status_code == 200
    drilldown_payload = drilldown_response.json()
    assert drilldown_payload["success"] is True
    assert "confusion_matrix" in drilldown_payload["data"]
    assert "metric_drilldown" in drilldown_payload["data"]
    assert "false_positive_cost" in drilldown_payload["data"]
    assert "operational" in drilldown_payload["data"]


def test_evaluation_comparison_not_found(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    response = client.get("/api/v1/evaluation/missing_run/comparison")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "EVAL_RUN_NOT_FOUND"


def test_evaluation_mathematical_consistency_and_confusion_matrix(tmp_path: Path) -> None:
    """Verify exact mathematical relations between TP/FP/FN/TN, Precision, Recall, F1, Accuracy, and Economics."""
    client = _build_client(tmp_path)
    run_id = "math_eval_run_001"
    response = client.post(
        "/api/v1/evaluation/run",
        json={
            "dataset_version": "math_dataset_v1",
            "split": "TEST",
            "generation_seed": 42,
            "total_cases": 1000,
            "evaluation_run_id": run_id,
            "generate_if_missing": True,
        },
    )
    assert response.status_code == 200

    drilldown_res = client.get(f"/api/v1/evaluation/{run_id}/drilldown")
    assert drilldown_res.status_code == 200
    drilldown = drilldown_res.json()["data"]

    cm = drilldown["confusion_matrix"]
    tp, fp, fn, tn = cm["tp"], cm["fp"], cm["fn"], cm["tn"]
    summary = drilldown["summary"]
    total = summary["records"]

    # 1. Total conservation
    assert tp + fp + fn + tn == total

    # 2. Precision = TP / (TP + FP)
    expected_precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    assert abs(summary["precision"] - expected_precision) < 1e-6

    # 3. Recall = TP / (TP + FN)
    expected_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    assert abs(summary["recall"] - expected_recall) < 1e-6

    # 4. F1 = 2 * P * R / (P + R)
    expected_f1 = (
        (2 * expected_precision * expected_recall / (expected_precision + expected_recall))
        if (expected_precision + expected_recall) > 0
        else 0.0
    )
    assert abs(summary["f1"] - expected_f1) < 1e-6

    # 5. False positive counts & errors
    assert summary["false_positive_count"] == fp
    assert drilldown["false_positive_cost"]["count"] == fp
    assert drilldown["metric_drilldown"]["total_errors"] == fp + fn

    # 6. Economic net yield consistency: net = gross - intervention_cost
    assert summary["net_recovered_minor"] == summary["gross_recovered_minor"] - summary["intervention_cost_minor"]

    # 7. Comparison consistency
    comp_res = client.get(f"/api/v1/evaluation/{run_id}/comparison")
    assert comp_res.status_code == 200
    comp_data = comp_res.json()["data"]
    assert comp_data["recoveriq"]["precision"] == summary["precision"]
    assert comp_data["recoveriq"]["recall"] == summary["recall"]
    assert comp_data["recoveriq"]["f1"] == summary["f1"]
    assert comp_data["recoveriq"]["net_recovered_minor"] == summary["net_recovered_minor"]


