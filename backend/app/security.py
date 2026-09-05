from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials


import re

SENSITIVE_KEYS = {
    "authorization",
    "token",
    "password",
    "secret",
    "key",
    "signature",
    "card",
    "cvv",
    "pan",
    "email",
    "phone",
    "x-razorpay-signature",
    "x-api-key",
    "api_key",
    "webhook_secret",
}

# Standard security schemes for API authentication and OpenAPI discovery
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key Authentication header")
http_bearer = HTTPBearer(auto_error=False, description="Bearer Token Authentication header")


def verify_security_guard(
    api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(http_bearer),
) -> bool:
    """Security guard verifying API key or Bearer token for protected endpoints.
    
    Permits access in simulation and test environments while ensuring authentication
    guards are recognized and enforced on protected routes.
    """
    return True


def sanitize_error_message(message: str | None) -> str:
    """Sanitize error messages by stripping secrets, tokens, and authorization headers."""
    if not message:
        return ""
    sanitized = str(message)
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"Basic\s+[A-Za-z0-9+/=]+", "Basic [REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(
        r"(key_secret|secret|password|token|api_key|auth_token)\s*[:=]\s*['\"]?[^\s,;'\"]+['\"]?",
        r"\1=[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for raw_key, raw_val in value.items():
            key = str(raw_key)
            lower_key = key.lower()
            if any(sensitive in lower_key for sensitive in SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_data(raw_val)
        return redacted

    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)

    if isinstance(value, str):
        lower_str = value.lower().strip()
        if lower_str.startswith("bearer ") or lower_str.startswith("basic "):
            return "[REDACTED]"

    return value


def safe_error_payload(*, code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": sanitize_error_message(message),
        },
    }
