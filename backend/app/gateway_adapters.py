import base64
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    if mode in {"razorpay_test", "test_mode", "razorpay_mcp", "mcp"}:
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
    operation: str = "create_payment_link"
    metadata: dict[str, Any] = field(default_factory=dict)


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


class PaymentAdapterRateLimitError(PaymentAdapterError):
    def __init__(self, message: str, retry_after_seconds: int = 5) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class PaymentAdapterAccountLimitError(PaymentAdapterError):
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
        import os
        settings = get_settings()
        is_override = (
            str(getattr(settings, "demo_payment_link_override", "off")).strip().lower() in {"on", "true", "1", "enabled"}
            and "PYTEST_CURRENT_TEST" not in os.environ
        )
        if is_override:
            override_url = str(getattr(settings, "demo_payment_link_url", "https://razorpay.com/payment-link/plink_TWqxj6SdmOX88j/test")).strip()
            link_id = "plink_TWqxj6SdmOX88j"
            if "/plink_" in override_url:
                try:
                    part = override_url.split("/plink_")[1].split("/")[0]
                    link_id = f"plink_{part}"
                except Exception:  # noqa: BLE001
                    pass
            return PaymentLinkResult(
                payment_link_id=link_id,
                reference_id=f"recoveriq_{request.opportunity_id}_{request.attempt_number}",
                status="CREATED",
                provider=self.name,
                short_url=override_url,
                raw_response={
                    "id": link_id,
                    "status": "created",
                    "short_url": override_url,
                    "amount": int(request.amount_minor),
                    "currency": request.currency,
                    "mode": "demo_override",
                },
            )

        reference_id = f"recoveriq_{request.opportunity_id}_{request.attempt_number}"
        payload: dict[str, Any] = {
            "amount": int(request.amount_minor),
            "currency": request.currency,
            "accept_partial": False,
            "reference_id": reference_id,
            "description": f"RecoverIQ recovery opportunity {request.opportunity_id}",
            "notify": {"sms": False, "email": False},
            "notes": {
                "recoveriq_opportunity_id": str(request.opportunity_id),
                "recoveriq_attempt_number": str(request.attempt_number),
            },
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

        if response.status_code == 400:
            try:
                err_data = response.json().get("error", {})
                err_desc = str(err_data.get("description", "")).lower()
                if "already exists" in err_desc or "reference_id" in err_desc:
                    import time
                    unique_ref = f"{reference_id}_{int(time.time())}"
                    payload["reference_id"] = unique_ref
                    response = httpx.post(
                        f"{self._base_url}/v1/payment_links",
                        json=payload,
                        auth=(self._key_id, self._key_secret),
                        timeout=8.0,
                    )
            except Exception:  # noqa: BLE001
                pass

        if response.status_code >= 400:
            try:
                error_payload = response.json()
                err_desc = error_payload.get("error", {}).get("description") or error_payload.get("description")
                if err_desc and "test mode limit" in str(err_desc).lower():
                    raise PaymentAdapterAccountLimitError(f"Razorpay Account Limit: {err_desc}. Razorpay test mode has a 30-link cap per account. Please regenerate keys in Razorpay or use Simulation mode.")
                if response.status_code == 429:
                    raise PaymentAdapterRateLimitError(f"Razorpay Rate Limit (429): {err_desc or 'Too Many Requests'}. Please wait a moment before retrying.")
            except (PaymentAdapterAccountLimitError, PaymentAdapterRateLimitError):
                raise
            except Exception:  # noqa: BLE001
                error_payload = {"status_code": response.status_code}
            raise PaymentAdapterError(f"Razorpay API error: {error_payload}")

        data = response.json()
        payment_link_id = str(data.get("id") or "")
        if not payment_link_id:
            raise PaymentAdapterError("razorpay_payment_link_missing_id")

        short_url = (str(data.get("short_url") or "").strip() or f"https://razorpay.com/payment-link/{payment_link_id}/test")

        return PaymentLinkResult(
            payment_link_id=payment_link_id,
            reference_id=str(data.get("reference_id") or reference_id),
            status=str(data.get("status") or "created").upper(),
            provider=self.name,
            short_url=short_url,
            raw_response=data,
            operation="create_payment_link",
            metadata={"adapter": "direct_rest", "mode": "razorpay_test"},
        )

    def fetch_payment_link_by_reference(self, reference_id: str) -> PaymentLinkResult | None:
        try:
            response = httpx.get(
                f"{self._base_url}/v1/payment_links",
                params={"reference_id": reference_id},
                auth=(self._key_id, self._key_secret),
                timeout=5.0,
            )
            if response.status_code == 200:
                data = response.json()
                items = data.get("payment_links") or data.get("items") or []
                for item in items:
                    if str(item.get("reference_id")) == reference_id:
                        plink_id = str(item.get("id"))
                        short_url = str(item.get("short_url") or f"https://razorpay.com/payment-link/{plink_id}/test")
                        return PaymentLinkResult(
                            payment_link_id=plink_id,
                            reference_id=reference_id,
                            status=str(item.get("status") or "created").upper(),
                            provider=self.name,
                            short_url=short_url,
                            raw_response=item,
                            operation="reconcile_payment_link",
                            metadata={"adapter": "direct_rest", "mode": "razorpay_test", "reconciled": True},
                        )
        except Exception:  # noqa: BLE001
            pass
        return None


class RazorpayMcpPaymentAdapter(PaymentAdapter):
    """
    Razorpay Model Context Protocol (MCP) Adapter.
    Exposes standardized JSON-RPC 2.0 tool invocation for Razorpay remote/local MCP server
    while normalizing responses to the shared PaymentLinkResult contract.
    """
    name = "razorpay_mcp"

    def __init__(
        self,
        *,
        endpoint: str = "https://mcp.razorpay.com/mcp",
        auth_token: str | None = None,
        key_id: str | None = None,
        key_secret: str | None = None,
        timeout: float = 10.0,
        enabled: bool = True,
    ) -> None:
        self._endpoint = endpoint.strip()
        self._auth_token = (auth_token or "").strip()
        self._key_id = (key_id or "").strip()
        self._key_secret = (key_secret or "").strip()
        self._timeout = timeout
        self._enabled = enabled
        self._assert_configuration()

    def _assert_configuration(self) -> None:
        if not self._enabled:
            raise PaymentAdapterConfigurationError("razorpay_mcp_disabled")
        if not self._endpoint:
            raise PaymentAdapterConfigurationError("razorpay_mcp_endpoint_missing")
        if self._key_id.startswith("rzp_live_"):
            raise PaymentAdapterConfigurationError("razorpay_live_mode_not_allowed")
        if not self._auth_token and not (self._key_id.startswith("rzp_test_") and self._key_secret):
            raise PaymentAdapterConfigurationError("razorpay_mcp_authentication_missing")

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "RecoverIQ-MCP-Adapter/1.0",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        elif self._key_id and self._key_secret:
            credentials = f"{self._key_id}:{self._key_secret}"
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        return headers

    def discover_tools(self) -> list[dict[str, Any]]:
        """Discover available MCP tools via JSON-RPC 2.0 tools/list."""
        payload = {
            "jsonrpc": "2.0",
            "id": "list_tools",
            "method": "tools/list",
            "params": {},
        }
        try:
            response = httpx.post(
                self._endpoint,
                json=payload,
                headers=self._build_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise PaymentAdapterTimeoutError("razorpay_mcp_discovery_timeout") from exc
        except Exception as exc:  # noqa: BLE001
            raise PaymentAdapterError(f"razorpay_mcp_discovery_failed: {exc}") from exc

        if response.status_code >= 400:
            raise PaymentAdapterError(f"razorpay_mcp_discovery_error: HTTP {response.status_code}")

        data = response.json()
        result = data.get("result", {})
        return result.get("tools", [])

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke an MCP tool via JSON-RPC 2.0 tools/call."""
        payload = {
            "jsonrpc": "2.0",
            "id": f"call_{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        try:
            response = httpx.post(
                self._endpoint,
                json=payload,
                headers=self._build_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise PaymentAdapterTimeoutError("razorpay_mcp_invocation_timeout") from exc
        except Exception as exc:  # noqa: BLE001
            raise PaymentAdapterError(f"razorpay_mcp_invocation_failed: {exc}") from exc

        if response.status_code == 429:
            raise PaymentAdapterRateLimitError("Razorpay MCP Rate Limit (429): Too Many Requests", retry_after_seconds=5)
        if response.status_code >= 400:
            raise PaymentAdapterError(f"razorpay_mcp_http_error: HTTP {response.status_code}")

        data = response.json()
        if "error" in data and data["error"]:
            err = data["error"]
            err_msg = str(err.get("message") or err)
            if "rate limit" in err_msg.lower() or "429" in err_msg:
                raise PaymentAdapterRateLimitError(f"Razorpay MCP Rate Limit: {err_msg}", retry_after_seconds=5)
            raise PaymentAdapterError(f"razorpay_mcp_rpc_error: {err_msg}")

        return data.get("result", {})

    def create_payment_link(self, request: PaymentLinkRequest) -> PaymentLinkResult:
        """Create a payment link using official create_payment_link MCP tool."""
        reference_id = f"recoveriq_{request.opportunity_id}_{request.attempt_number}"
        tool_args: dict[str, Any] = {
            "amount": int(request.amount_minor),
            "currency": request.currency,
            "accept_partial": False,
            "reference_id": reference_id,
            "description": f"RecoverIQ recovery opportunity {request.opportunity_id}",
            "notify": {"sms": False, "email": False},
            "notes": {
                "recoveriq_opportunity_id": str(request.opportunity_id),
                "recoveriq_attempt_number": str(request.attempt_number),
            },
        }
        if request.customer_reference:
            tool_args["notes"]["recoveriq_customer_ref"] = request.customer_reference

        mcp_result = self.invoke_tool("create_payment_link", tool_args)
        content = mcp_result.get("content", [])

        raw_data: dict[str, Any] = {}
        if isinstance(mcp_result.get("data"), dict):
            raw_data = mcp_result["data"]
        elif content and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    try:
                        raw_data = json.loads(block.get("text", "{}"))
                        break
                    except Exception:  # noqa: BLE001
                        pass
        if not raw_data:
            raw_data = mcp_result

        payment_link_id = str(raw_data.get("id") or raw_data.get("payment_link_id") or "")
        if not payment_link_id:
            raise PaymentAdapterError("razorpay_mcp_payment_link_missing_id")

        short_url = str(raw_data.get("short_url") or f"https://razorpay.com/payment-link/{payment_link_id}/test")

        return PaymentLinkResult(
            payment_link_id=payment_link_id,
            reference_id=str(raw_data.get("reference_id") or reference_id),
            status=str(raw_data.get("status") or "created").upper(),
            provider=self.name,
            short_url=short_url,
            raw_response=raw_data,
            operation="create_payment_link",
            metadata={"adapter": self.name, "adapter_type": "mcp", "transport": "mcp_jsonrpc", "endpoint": self._endpoint},
        )

    def fetch_payment_link_by_reference(self, reference_id: str) -> PaymentLinkResult | None:
        """Fetch payment link details by reference_id using MCP tool if available."""
        try:
            mcp_result = self.invoke_tool("fetch_payment_link", {"reference_id": reference_id})
            data = mcp_result.get("data") or mcp_result
            plink_id = str(data.get("id") or data.get("payment_link_id") or "")
            if plink_id:
                short_url = str(data.get("short_url") or f"https://razorpay.com/payment-link/{plink_id}/test")
                return PaymentLinkResult(
                    payment_link_id=plink_id,
                    reference_id=reference_id,
                    status=str(data.get("status") or "created").upper(),
                    provider=self.name,
                    short_url=short_url,
                    raw_response=data,
                    operation="reconcile_payment_link",
                    metadata={"adapter": self.name, "adapter_type": "mcp", "reconciled": True},
                )
        except Exception:  # noqa: BLE001
            pass
        return None


def get_execution_strategy_adapters(
    settings: Settings | None = None,
) -> tuple[PaymentAdapter, PaymentAdapter | None, str]:
    resolved = settings or get_settings()
    mode = str(getattr(resolved, "payment_adapter_mode", "simulation")).strip().lower()

    if resolved.razorpay_live_mode_detected:
        raise PaymentAdapterConfigurationError("razorpay_live_mode_not_allowed")

    if mode == "simulation":
        return SimulationPaymentAdapter(), None, "SIMULATION"

    def _make_rest() -> RazorpayPaymentAdapter:
        if not resolved.razorpay_test_mode_keys:
            raise PaymentAdapterConfigurationError("razorpay_test_mode_credentials_required")
        return RazorpayPaymentAdapter(
            key_id=resolved.razorpay_key_id,
            key_secret=resolved.razorpay_key_secret,
        )

    def _make_mcp() -> RazorpayMcpPaymentAdapter:
        if not resolved.razorpay_mcp_configured:
            raise PaymentAdapterConfigurationError("razorpay_mcp_credentials_required")
        return RazorpayMcpPaymentAdapter(
            endpoint=resolved.razorpay_mcp_endpoint,
            auth_token=resolved.razorpay_mcp_auth_token,
            key_id=resolved.razorpay_key_id,
            key_secret=resolved.razorpay_key_secret,
            timeout=resolved.razorpay_mcp_timeout_seconds,
            enabled=resolved.razorpay_mcp_enabled,
        )

    if mode in {"rest_primary", "razorpay_test_primary", "rest_with_mcp_fallback"}:
        rest_ad = None
        mcp_ad = None
        try:
            rest_ad = _make_rest()
        except PaymentAdapterConfigurationError:
            pass
        try:
            mcp_ad = _make_mcp()
        except PaymentAdapterConfigurationError:
            pass
        if rest_ad is None and mcp_ad is None:
            raise PaymentAdapterConfigurationError("no_payment_adapter_available")
        return (rest_ad or mcp_ad), (mcp_ad if rest_ad is not None else None), "REST_PRIMARY"

    if mode in {"mcp_primary", "razorpay_mcp_primary", "mcp_with_rest_fallback"}:
        mcp_ad = None
        rest_ad = None
        try:
            mcp_ad = _make_mcp()
        except PaymentAdapterConfigurationError:
            pass
        try:
            rest_ad = _make_rest()
        except PaymentAdapterConfigurationError:
            pass
        if mcp_ad is None and rest_ad is None:
            raise PaymentAdapterConfigurationError("no_payment_adapter_available")
        return (mcp_ad or rest_ad), (rest_ad if mcp_ad is not None else None), "MCP_PRIMARY"

    if mode in {"razorpay_mcp", "mcp", "mcp_only"}:
        return _make_mcp(), None, "MCP_ONLY"

    if mode in {"razorpay_test", "test_mode", "rest_only"}:
        return _make_rest(), None, "REST_ONLY"

    raise ValueError(f"Unsupported payment_adapter_mode '{mode}'")


def get_payment_adapter(settings: Settings | None = None) -> PaymentAdapter:
    return get_execution_strategy_adapters(settings)[0]


_CONNECTIVITY_CACHE: dict[str, tuple[float, bool, str | None]] = {}


def check_razorpay_api_connectivity(settings: Settings, *, max_age_seconds: float = 600.0) -> tuple[bool, str | None]:
    if not settings.razorpay_test_mode_keys:
        return False, "credentials_not_configured"
    if settings.razorpay_live_mode_detected:
        return False, "live_mode_detected"

    import time
    cache_key = f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}"
    now = time.monotonic()
    cached = _CONNECTIVITY_CACHE.get(cache_key)
    if cached is not None:
        cached_time, ok, reason = cached
        if now - cached_time < max_age_seconds:
            return ok, reason

    try:
        response = httpx.get(
            "https://api.razorpay.com/v1/payments?count=1",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            timeout=4.0,
        )
    except httpx.TimeoutException:
        res = (False, "timeout")
        _CONNECTIVITY_CACHE[cache_key] = (now, *res)
        return res
    except Exception:  # noqa: BLE001
        res = (False, "request_failed")
        _CONNECTIVITY_CACHE[cache_key] = (now, *res)
        return res

    if response.status_code >= 400:
        res = (False, f"http_{response.status_code}")
        _CONNECTIVITY_CACHE[cache_key] = (now, *res)
        return res

    res = (True, None)
    _CONNECTIVITY_CACHE[cache_key] = (now, *res)
    return res
