from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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
}


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

    return value


def safe_error_payload(*, code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
