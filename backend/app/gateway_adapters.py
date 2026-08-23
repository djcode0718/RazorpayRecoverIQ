from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings, get_settings


@dataclass(frozen=True)
class AdapterValidationResult:
    ok: bool
    reason: str | None = None


class GatewayAdapter(ABC):
    name: str

    @abstractmethod
    def map_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate_retrieval_consistency(self, payload: dict[str, Any]) -> AdapterValidationResult:
        raise NotImplementedError


class SimulationGatewayAdapter(GatewayAdapter):
    name = "simulation"

    def map_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Simulation mode keeps incoming payload unchanged for deterministic local flows.
        return payload

    def validate_retrieval_consistency(self, payload: dict[str, Any]) -> AdapterValidationResult:
        return AdapterValidationResult(ok=True)


class RazorpayTestModeGatewayAdapter(GatewayAdapter):
    name = "razorpay_test"

    def map_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        mapped = dict(payload)
        event = str(mapped.get("event") or "")
        if event.startswith("payment."):
            payment_entity = mapped.get("payload", {}).get("payment", {}).get("entity")
            if not isinstance(payment_entity, dict):
                raise ValueError("missing_payment_entity")
            if not payment_entity.get("id"):
                raise ValueError("missing_payment_id")
        return mapped

    def validate_retrieval_consistency(self, payload: dict[str, Any]) -> AdapterValidationResult:
        event = str(payload.get("event") or "")
        if not event.startswith("payment."):
            return AdapterValidationResult(ok=True)

        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity")
        if not isinstance(payment_entity, dict):
            return AdapterValidationResult(ok=False, reason="missing_payment_entity")

        retrieved = payload.get("recoveriq_test_mode", {}).get("retrieved_payment")
        if retrieved is None:
            # Real Razorpay webhooks do not provide recovered test payload mirrors.
            return AdapterValidationResult(ok=True)
        if not isinstance(retrieved, dict):
            return AdapterValidationResult(ok=False, reason="retrieval_unavailable")

        checks = {
            "id": str(payment_entity.get("id") or "") == str(retrieved.get("id") or ""),
            "order_id": str(payment_entity.get("order_id") or "") == str(retrieved.get("order_id") or ""),
            "amount": int(payment_entity.get("amount") or 0) == int(retrieved.get("amount") or 0),
            "currency": str(payment_entity.get("currency") or "") == str(retrieved.get("currency") or ""),
        }
        for key, passed in checks.items():
            if not passed:
                return AdapterValidationResult(ok=False, reason=f"retrieval_mismatch_{key}")
        return AdapterValidationResult(ok=True)


def get_gateway_adapter(settings: Settings | None = None) -> GatewayAdapter:
    resolved = settings or get_settings()
    mode = str(getattr(resolved, "payment_adapter_mode", "simulation")).strip().lower()
    if mode == "simulation":
        return SimulationGatewayAdapter()
    if mode in {"razorpay_test", "test_mode"}:
        return RazorpayTestModeGatewayAdapter()
    raise ValueError(f"Unsupported payment_adapter_mode '{mode}'")


@dataclass(frozen=True)
class PaymentLinkRequest:
    opportunity_id: int
    attempt_number: int
    amount_minor: int
    currency: str
    customer_reference: str | None = None


@dataclass(frozen=True)
class PaymentLinkResult:
    payment_link_id: str
    reference_id: str
    status: str
    provider: str
    short_url: str | None
    raw_response: dict[str, Any]


class PaymentAdapter(ABC):
    name: str

    @abstractmethod
    def create_payment_link(self, request: PaymentLinkRequest) -> PaymentLinkResult:
        raise NotImplementedError


class PaymentAdapterError(RuntimeError):
    pass


class PaymentAdapterTimeoutError(PaymentAdapterError):
    pass


class PaymentAdapterConfigurationError(PaymentAdapterError):
    pass


class SimulationPaymentAdapter(PaymentAdapter):
    name = "simulation"

    def create_payment_link(self, request: PaymentLinkRequest) -> PaymentLinkResult:
        payment_link_id = f"plink_sim_{request.opportunity_id}_{request.attempt_number}"
        reference_id = f"recoveriq_{request.opportunity_id}_{request.attempt_number}"
        return PaymentLinkResult(
            payment_link_id=payment_link_id,
            reference_id=reference_id,
            status="CREATED",
            provider=self.name,
            short_url=None,
            raw_response={
                "mode": "simulation",
                "amount_minor": request.amount_minor,
                "currency": request.currency,
            },
        )


class RazorpayPaymentAdapter(PaymentAdapter):
    name = "razorpay_test"

    def __init__(self, *, key_id: str, key_secret: str, base_url: str = "https://api.razorpay.com") -> None:
        self._key_id = key_id.strip()
        self._key_secret = key_secret.strip()
        self._base_url = base_url.rstrip("/")
        self._assert_test_mode_credentials()

    def _assert_test_mode_credentials(self) -> None:
        if not self._key_id or not self._key_secret:
            raise PaymentAdapterConfigurationError("razorpay_credentials_missing")
        if self._key_id.startswith("rzp_live_"):
            raise PaymentAdapterConfigurationError("razorpay_live_mode_not_allowed")
        if not self._key_id.startswith("rzp_test_"):
            raise PaymentAdapterConfigurationError("razorpay_test_mode_credentials_required")

    def create_payment_link(self, request: PaymentLinkRequest) -> PaymentLinkResult:
        reference_id = f"recoveriq_{request.opportunity_id}_{request.attempt_number}"
        payload: dict[str, Any] = {
            "amount": int(request.amount_minor),
            "currency": request.currency,
            "accept_partial": False,
            "reference_id": reference_id,
            "description": f"RecoverIQ recovery opportunity {request.opportunity_id}",
            "notify": {"sms": False, "email": False},
            "notes": {"recoveriq_opportunity_id": str(request.opportunity_id)},
        }
        if request.customer_reference:
            payload["notes"]["recoveriq_customer_ref"] = request.customer_reference

        try:
            response = httpx.post(
                f"{self._base_url}/v1/payment_links",
                json=payload,
                auth=(self._key_id, self._key_secret),
                timeout=8.0,
            )
        except httpx.TimeoutException as exc:
            raise PaymentAdapterTimeoutError("razorpay_payment_link_timeout") from exc
        except Exception as exc:  # noqa: BLE001
            raise PaymentAdapterError(f"razorpay_payment_link_request_failed:{exc}") from exc

        if response.status_code >= 400:
            try:
                error_payload = response.json()
            except Exception:  # noqa: BLE001
                error_payload = {"status_code": response.status_code}
            raise PaymentAdapterError(f"razorpay_payment_link_error:{error_payload}")

        data = response.json()
        payment_link_id = str(data.get("id") or "")
        if not payment_link_id:
            raise PaymentAdapterError("razorpay_payment_link_missing_id")

        return PaymentLinkResult(
            payment_link_id=payment_link_id,
            reference_id=str(data.get("reference_id") or reference_id),
            status=str(data.get("status") or "created").upper(),
            provider=self.name,
            short_url=(str(data.get("short_url") or "").strip() or None),
            raw_response=data,
        )


def get_payment_adapter(settings: Settings | None = None) -> PaymentAdapter:
    resolved = settings or get_settings()
    mode = str(getattr(resolved, "payment_adapter_mode", "simulation")).strip().lower()
    if mode == "simulation":
        return SimulationPaymentAdapter()
    if mode in {"razorpay_test", "test_mode"}:
        if resolved.razorpay_live_mode_detected:
            raise PaymentAdapterConfigurationError("razorpay_live_mode_not_allowed")
        if not resolved.razorpay_test_mode_keys:
            raise PaymentAdapterConfigurationError("razorpay_test_mode_credentials_required")
        return RazorpayPaymentAdapter(
            key_id=resolved.razorpay_key_id,
            key_secret=resolved.razorpay_key_secret,
        )
    raise ValueError(f"Unsupported payment_adapter_mode '{mode}'")


def check_razorpay_api_connectivity(settings: Settings) -> tuple[bool, str | None]:
    if not settings.razorpay_test_mode_keys:
        return False, "credentials_not_configured"
    if settings.razorpay_live_mode_detected:
        return False, "live_mode_detected"

    try:
        response = httpx.get(
            "https://api.razorpay.com/v1/payments?count=1",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            timeout=4.0,
        )
    except httpx.TimeoutException:
        return False, "timeout"
    except Exception:  # noqa: BLE001
        return False, "request_failed"

    if response.status_code >= 400:
        return False, f"http_{response.status_code}"
    return True, None
