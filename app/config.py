"""Configuration loading and validation.

All configuration is read from environment variables (optionally sourced
from a .env file). No secrets are hard-coded, and nothing here makes a
network call.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.errors import ConfigError

ALLOWED_PROVIDERS = {"fake", "local", "approved"}


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FIRM_AI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    audit_db_path: Path = Path("data/audit.db")
    documents_dir: Path = Path("data/sample_documents")
    users_file: Path = Path("data/users.json")
    provider_name: str = "fake"
    provider_api_key: str | None = None
    provider_base_url: str | None = None
    local_chat_model: str = "Qwen3.5-2B-Q4_K_M.gguf"

    @field_validator("provider_name")
    @classmethod
    def validate_provider_name(cls, value: str) -> str:
        if value not in ALLOWED_PROVIDERS:
            raise ValueError(
                f"provider_name must be one of {sorted(ALLOWED_PROVIDERS)}, got {value!r}"
            )
        return value

    @field_validator("local_chat_model")
    @classmethod
    def validate_local_chat_model(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,100}", value):
            raise ValueError("local_chat_model contains unsupported characters")
        return value


def load_config(env_file: str | Path | None = None) -> AppConfig:
    """Load and validate configuration.

    Raises ConfigError (never a raw pydantic/OS exception) on any failure,
    so callers can handle configuration problems uniformly.
    """
    if env_file is not None:
        path = Path(env_file)
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            return AppConfig(_env_file=path)
        except ValidationError as exc:
            raise ConfigError(f"Invalid configuration: {exc}") from exc

    try:
        return AppConfig()
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc
