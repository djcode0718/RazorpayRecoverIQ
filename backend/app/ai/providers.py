import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from ..config import Settings, get_settings


@dataclass(frozen=True)
class DiagnosisContext:
    opportunity_id: int
    payment_id: int | None
    amount_at_risk_minor: int
    currency: str
    failure_category: str
    failure_reason: str
    baseline_recommended_action: str
    baseline_recovery_probability: int


class DiagnosisProvider(ABC):
    name: str
    model_name: str | None = None

    @abstractmethod
    def generate_diagnosis(self, context: DiagnosisContext) -> dict[str, Any]:
        raise NotImplementedError


class MockDiagnosisProvider(DiagnosisProvider):
    name = "mock"
    model_name = "mock-v1"

    def generate_diagnosis(self, context: DiagnosisContext) -> dict[str, Any]:
        probability = max(5, min(95, context.baseline_recovery_probability + 3))
        confidence = max(50, min(95, 60 + abs(probability - 50) // 2))
        action = context.baseline_recommended_action
        if context.failure_reason == "insufficient_funds":
            action = "DELAYED_RETRY"

        return {
            "diagnosis": (
                "Payment failed due to a recoverable pathway. "
                f"Signals indicate {context.failure_reason} with amount risk {context.amount_at_risk_minor}."
            ),
            "failure_category": context.failure_category or "UNKNOWN",
            "recommended_action": action,
            "recovery_probability": probability,
            "confidence": confidence,
            "reason": "Deterministic fallback strategy selected from payment failure features.",
            "uncertainties": [
                "No issuer-side retry window data in webhook payload.",
            ],
            "evidence": [
                {
                    "signal": "failure_reason",
                    "observation": context.failure_reason or "unknown",
                    "impact": "HIGH",
                },
                {
                    "signal": "baseline_action",
                    "observation": context.baseline_recommended_action,
                    "impact": "MEDIUM",
                },
            ],
            "provider_metadata": {
                "strategy": "deterministic_mock",
            },
        }


class OllamaDiagnosisProvider(DiagnosisProvider):
    name = "ollama"

    def __init__(self, *, model: str, base_url: str = "http://127.0.0.1:11434") -> None:
        self.model_name = model
        self._base_url = base_url.rstrip("/")

    def generate_diagnosis(self, context: DiagnosisContext) -> dict[str, Any]:
        system_prompt = (
            "Return only valid JSON for a recovery diagnosis with keys: "
            "diagnosis, failure_category, recommended_action, recovery_probability, confidence, evidence, provider_metadata."
        )
        user_prompt = (
            "Use this context and keep response concise: "
            f"{json.dumps(context.__dict__, separators=(',', ':'))}"
        )
        payload = {
            "model": self.model_name,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
        }

        try:
            response = httpx.post(f"{self._base_url}/api/chat", json=payload, timeout=8.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"ollama_request_failed: {exc}") from exc

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("ollama_empty_response")

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ollama_invalid_json_response") from exc


ProviderFactory = Callable[[Settings], DiagnosisProvider]


def _mock_provider_factory(_: Settings) -> DiagnosisProvider:
    return MockDiagnosisProvider()


def _ollama_provider_factory(settings: Settings) -> DiagnosisProvider:
    return OllamaDiagnosisProvider(model=settings.ollama_model)


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "mock": _mock_provider_factory,
    "local": _ollama_provider_factory,
    "ollama": _ollama_provider_factory,
}


def get_provider(provider_name: str | None = None, *, settings: Settings | None = None) -> DiagnosisProvider:
    resolved_settings = settings or get_settings()
    selected = (provider_name or resolved_settings.ai_provider).strip().lower()
    factory = PROVIDER_FACTORIES.get(selected)
    if factory is None:
        supported = ", ".join(sorted(PROVIDER_FACTORIES.keys()))
        raise ValueError(f"Unsupported ai_provider '{selected}'. Supported providers: {supported}")
    return factory(resolved_settings)
