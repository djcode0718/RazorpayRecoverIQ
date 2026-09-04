import os
from pathlib import Path
import httpx
import pytest

from app.config import Settings, get_settings
from app.gateway_adapters import (
    PaymentAdapterConfigurationError,
    PaymentAdapterError,
    PaymentAdapterRateLimitError,
    PaymentAdapterTimeoutError,
    PaymentLinkRequest,
    PaymentLinkResult,
    RazorpayMcpPaymentAdapter,
    RazorpayPaymentAdapter,
    SimulationPaymentAdapter,
    get_payment_adapter,
)


def test_mcp_adapter_initialization_with_token() -> None:
    """Test MCP adapter initializes correctly with bearer token."""
    adapter = RazorpayMcpPaymentAdapter(
        endpoint="https://mcp.razorpay.com/mcp",
        auth_token="mcp_test_token_123",
        timeout=8.0,
        enabled=True,
    )
    assert adapter.name == "razorpay_mcp"
    headers = adapter._build_headers()
    assert headers["Authorization"] == "Bearer mcp_test_token_123"
    assert headers["Content-Type"] == "application/json"


def test_mcp_adapter_initialization_with_keys() -> None:
    """Test MCP adapter initializes correctly with API key and secret."""
    adapter = RazorpayMcpPaymentAdapter(
        endpoint="https://mcp.razorpay.com/mcp",
        key_id="rzp_test_mcp_key",
        key_secret="mcp_secret_pass",
        timeout=10.0,
        enabled=True,
    )
    assert adapter.name == "razorpay_mcp"
    headers = adapter._build_headers()
    assert headers["Authorization"].startswith("Basic ")


def test_mcp_adapter_disabled_raises_configuration_error() -> None:
    """Test MCP adapter raises configuration error when disabled."""
    with pytest.raises(PaymentAdapterConfigurationError, match="razorpay_mcp_disabled"):
        RazorpayMcpPaymentAdapter(
            endpoint="https://mcp.razorpay.com/mcp",
            auth_token="token",
            enabled=False,
        )


def test_mcp_adapter_missing_auth_raises_configuration_error() -> None:
    """Test MCP adapter raises error when both token and keys are missing."""
    with pytest.raises(PaymentAdapterConfigurationError, match="razorpay_mcp_authentication_missing"):
        RazorpayMcpPaymentAdapter(
            endpoint="https://mcp.razorpay.com/mcp",
            auth_token="",
            key_id="",
            key_secret="",
            enabled=True,
        )


def test_mcp_adapter_live_mode_raises_configuration_error() -> None:
    """Test MCP adapter blocks live mode keys."""
    with pytest.raises(PaymentAdapterConfigurationError, match="razorpay_live_mode_not_allowed"):
        RazorpayMcpPaymentAdapter(
            endpoint="https://mcp.razorpay.com/mcp",
            key_id="rzp_live_forbidden",
            key_secret="secret",
            enabled=True,
        )


def test_mcp_adapter_discover_tools(monkeypatch) -> None:
    """Test MCP tool discovery via JSON-RPC 2.0 tools/list."""
    def _mock_post(url, *, json, headers, timeout):
        assert json["method"] == "tools/list"
        assert json["jsonrpc"] == "2.0"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json["id"],
                "result": {
                    "tools": [
                        {"name": "create_payment_link", "description": "Create standard payment link"},
                        {"name": "fetch_payment_link", "description": "Fetch payment link details"},
                        {"name": "fetch_payment", "description": "Fetch payment details"},
                    ]
                },
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_post)

    adapter = RazorpayMcpPaymentAdapter(
        endpoint="https://mcp.razorpay.com/mcp",
        auth_token="test_token",
        enabled=True,
    )
    tools = adapter.discover_tools()
    assert len(tools) == 3
    tool_names = [t["name"] for t in tools]
    assert "create_payment_link" in tool_names
    assert "fetch_payment_link" in tool_names


def test_mcp_adapter_create_payment_link_normalizes_result(monkeypatch) -> None:
    """Test MCP create_payment_link invokes tool and normalizes to PaymentLinkResult."""
    captured_payload = {}

    def _mock_post(url, *, json, headers, timeout):
        captured_payload["url"] = url
        captured_payload["json"] = json
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": json["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                '{"id": "plink_mcp_mock_999", "status": "created", '
                                '"short_url": "https://rzp.io/i/mockmcp", "reference_id": "recoveriq_42_1", '
                                '"amount": 500000, "currency": "INR"}'
                            ),
                        }
                    ],
                    "data": {
                        "id": "plink_mcp_mock_999",
                        "status": "created",
                        "short_url": "https://rzp.io/i/mockmcp",
                        "reference_id": "recoveriq_42_1",
                    },
                },
            },
        )

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_post)

    adapter = RazorpayMcpPaymentAdapter(
        endpoint="https://mcp.razorpay.com/mcp",
        auth_token="test_token",
        enabled=True,
    )
    req = PaymentLinkRequest(
        opportunity_id=42,
        attempt_number=1,
        amount_minor=500000,
        currency="INR",
        customer_reference="cust_99",
    )
    result = adapter.create_payment_link(req)

    assert result.payment_link_id == "plink_mcp_mock_999"
    assert result.reference_id == "recoveriq_42_1"
    assert result.status == "CREATED"
    assert result.provider == "razorpay_mcp"
    assert result.short_url == "https://rzp.io/i/mockmcp"
    assert result.operation == "create_payment_link"
    assert result.metadata["adapter"] == "razorpay_mcp"
    assert result.metadata["adapter_type"] == "mcp"
    assert result.metadata["transport"] == "mcp_jsonrpc"


def test_mcp_adapter_rate_limit_error_mapping(monkeypatch) -> None:
    """Test HTTP 429 from MCP server maps to PaymentAdapterRateLimitError."""
    def _mock_post(url, *, json, headers, timeout):
        return httpx.Response(429, json={"error": {"code": -32000, "message": "Too Many Requests"}})

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_post)

    adapter = RazorpayMcpPaymentAdapter(
        endpoint="https://mcp.razorpay.com/mcp",
        auth_token="test_token",
        enabled=True,
    )
    with pytest.raises(PaymentAdapterRateLimitError) as exc_info:
        adapter.invoke_tool("create_payment_link", {"amount": 10000})
    assert exc_info.value.retry_after_seconds == 5


def test_mcp_adapter_timeout_mapping(monkeypatch) -> None:
    """Test timeout from MCP server maps to PaymentAdapterTimeoutError."""
    def _mock_post(url, *, json, headers, timeout):
        raise httpx.TimeoutException("MCP connection timed out")

    monkeypatch.setattr("app.gateway_adapters.httpx.post", _mock_post)

    adapter = RazorpayMcpPaymentAdapter(
        endpoint="https://mcp.razorpay.com/mcp",
        auth_token="test_token",
        enabled=True,
    )
    with pytest.raises(PaymentAdapterTimeoutError):
        adapter.invoke_tool("create_payment_link", {"amount": 10000})


def test_get_payment_adapter_factory_mcp_mode() -> None:
    """Test factory resolves RazorpayMcpPaymentAdapter when configured."""
    settings = Settings(
        payment_adapter_mode="razorpay_mcp",
        razorpay_mcp_enabled=True,
        razorpay_mcp_endpoint="https://mcp.razorpay.com/mcp",
        razorpay_mcp_auth_token="valid_mcp_token",
    )
    adapter = get_payment_adapter(settings)
    assert isinstance(adapter, RazorpayMcpPaymentAdapter)
    assert adapter.name == "razorpay_mcp"


def test_get_payment_adapter_preserves_direct_rest_mode() -> None:
    """Test factory resolves Direct REST RazorpayPaymentAdapter without MCP interference."""
    settings = Settings(
        payment_adapter_mode="razorpay_test",
        razorpay_key_id="rzp_test_direct_rest",
        razorpay_key_secret="direct_rest_secret",
        razorpay_mcp_enabled=False,
    )
    adapter = get_payment_adapter(settings)
    assert isinstance(adapter, RazorpayPaymentAdapter)
    assert adapter.name == "razorpay_test"


def test_get_payment_adapter_preserves_simulation_mode() -> None:
    """Test factory resolves SimulationPaymentAdapter."""
    settings = Settings(
        payment_adapter_mode="simulation",
        razorpay_mcp_enabled=False,
    )
    adapter = get_payment_adapter(settings)
    assert isinstance(adapter, SimulationPaymentAdapter)
    assert adapter.name == "simulation"
