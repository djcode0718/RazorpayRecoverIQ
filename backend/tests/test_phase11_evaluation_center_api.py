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


def test_phase11_evaluation_history_comparison_and_drilldown(tmp_path: Path) -> None:
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


def test_phase11_evaluation_comparison_not_found(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    response = client.get("/api/v1/evaluation/missing_run/comparison")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "EVAL_RUN_NOT_FOUND"
