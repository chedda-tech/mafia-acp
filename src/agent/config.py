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

    # Database (Supabase PostgreSQL — required for Railway, optional for local dev)
    database_url: str = ""

    # Mafia API
    mafia_api_base_url: str = ""

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


class _BelowWarning(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application.

    Records below WARNING go to stdout; WARNING and above go to stderr,
    subject to the configured global log level.
    """
    import sys

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(numeric_level)
    stdout_handler.addFilter(_BelowWarning())
    stdout_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
    root.handlers.clear()
    root.setLevel(numeric_level)
    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)
