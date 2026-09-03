import os
from pathlib import Path

import pytest

from app.ai.providers import DiagnosisContext, MockDiagnosisProvider, get_provider
from app.config import get_settings
from app.diagnosis_schema import StructuredDiagnosis


def _sample_context() -> DiagnosisContext:
    return DiagnosisContext(
        opportunity_id=1,
        payment_id=2,
        amount_at_risk_minor=150000,
        currency="INR",
        failure_category="NETWORK",
        failure_reason="network",
        baseline_recommended_action="RECOVERY_PROMPT",
        baseline_recovery_probability=62,
    )


def test_registry_resolves_mock_provider(tmp_path: Path) -> None:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'test_provider.db'}"
    os.environ["AI_PROVIDER"] = "mock"
    get_settings.cache_clear()

    provider = get_provider()
    assert provider.name == "mock"


def test_mock_provider_output_passes_strict_schema_validation() -> None:
    provider = MockDiagnosisProvider()
    diagnosis = provider.generate_diagnosis(_sample_context())
    validated = StructuredDiagnosis.model_validate(diagnosis)

    assert validated.recommended_action in {
        "RETRY",
        "DELAYED_RETRY",
        "RECOVERY_PROMPT",
        "ALTERNATE_PAYMENT_PATH",
        "ESCALATE",
        "NO_ACTION",
    }
    assert validated.recovery_probability >= 0


def test_registry_resolves_groq_and_gemini_providers(tmp_path: Path) -> None:
    os.environ["RECOVERIQ_DB_URL"] = f"sqlite:///{tmp_path / 'test_provider_cloud.db'}"
    os.environ["AI_PROVIDER"] = "groq"
    os.environ["GROQ_API_KEY"] = "gsk_test_mock_key"
    get_settings.cache_clear()

    groq_provider = get_provider()
    assert groq_provider.name == "groq"

    os.environ["AI_PROVIDER"] = "gemini"
    os.environ["GEMINI_API_KEY"] = "AQ_test_mock_key"
    get_settings.cache_clear()

    gemini_provider = get_provider()
    assert gemini_provider.name == "gemini"


def test_registry_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        get_provider("does-not-exist")



