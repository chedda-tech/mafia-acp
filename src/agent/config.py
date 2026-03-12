"""Central configuration loaded from environment variables."""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file and environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ACP
    whitelisted_wallet_private_key: str
    agent_wallet_address: str
    entity_id: int
    acp_network: str = "testnet"

    # Terminal API
    terminal_api_url: str = ""

    # LLM (OpenAI-compatible — works with OpenRouter, Together, Groq, etc.)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Monitoring config
    log_level: str = "INFO"
    status_update_interval_minutes: int = 15
    stale_data_threshold_seconds: int = 300
    max_swap_retries: int = 3
    data_refresh_interval_seconds: int = 60
    idempotency_db_path: str = ".state/idempotency.db"
    job_lock_ttl_seconds: int = 300


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
