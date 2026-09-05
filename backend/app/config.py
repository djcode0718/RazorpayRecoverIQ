from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "RecoverIQ"
    app_env: str = "development"
    app_mode: str = "simulation"
    api_prefix: str = "/api/v1"
    recoveriq_db_url: str = "sqlite:///./recoveriq.db"

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    ai_provider: str = "mock"
    ollama_model: str = "llama3.2:3b"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    razorpay_mcp_enabled: bool = False
    razorpay_mcp_endpoint: str = "https://mcp.razorpay.com/mcp"
    razorpay_mcp_auth_token: str = ""
    razorpay_mcp_timeout_seconds: float = 10.0

    payment_adapter_mode: str = "simulation"
    demo_payment_link_override: str = "off"
    demo_payment_link_url: str = "https://razorpay.com/payment-link/plink_TWqxj6SdmOX88j/test"
    internal_webhook_replay_enabled: bool = True
    log_level: str = "DEBUG"
    log_sql_queries: bool = True

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def razorpay_test_mode_keys(self) -> bool:
        key_id = (self.razorpay_key_id or "").strip()
        key_secret = (self.razorpay_key_secret or "").strip()
        if not key_id or not key_secret:
            return False
        return key_id.startswith("rzp_test_") and not key_id.startswith("rzp_live_")

    @property
    def razorpay_live_mode_detected(self) -> bool:
        return (self.razorpay_key_id or "").strip().startswith("rzp_live_")

    @property
    def razorpay_mcp_configured(self) -> bool:
        if not self.razorpay_mcp_enabled:
            return False
        if not self.razorpay_mcp_endpoint.strip():
            return False
        return bool(self.razorpay_mcp_auth_token.strip() or self.razorpay_test_mode_keys)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
