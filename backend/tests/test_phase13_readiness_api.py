import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import init_db, reset_db_runtime
from app.main import create_app


def _build_client(tmp_path: Path) -> TestClient:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'readiness.db'}"
    os.environ["PAYMENT_ADAPTER_MODE"] = "simulation"
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    return TestClient(create_app())


def test_readiness_workflow_returns_review_evidence(tmp_path: Path) -> None:
    client = _build_client(tmp_path)

    response = client.post("/api/v1/readiness/execute")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    data = payload["data"]
    assert data["workflow"] == "demo_readiness_validation"
    assert data["status"] in {"PASS", "PARTIAL", "FAIL"}
    assert data["summary"]["pass_count"] >= 1
    assert len(data["checks"]) >= 4

    check_ids = {check["id"] for check in data["checks"]}
    assert "db_connectivity" in check_ids
    assert "reproducibility_probe" in check_ids
    assert "security_redaction_guard" in check_ids


def test_legacy_phase13_readiness_route_remains_supported(tmp_path: Path) -> None:
    client = _build_client(tmp_path)

    response = client.post("/api/v1/readiness/phase13/execute")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["workflow"] == "demo_readiness_validation"
