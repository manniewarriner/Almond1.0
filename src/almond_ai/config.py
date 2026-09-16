"""Developer-console configuration without secret display."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseModel):
    provider: Literal["fake", "ollama", "llama_cpp", "openai_compatible"] = "llama_cpp"
    model: str = "MiniCPM5-2B-Q4_K_M.gguf"
    base_url: HttpUrl = HttpUrl("http://127.0.0.1:11435")
    temperature: float = Field(0.2, ge=0, le=2)
    context_window: int = Field(8192, ge=512)
    api_key: str | None = Field(default=None, repr=False)
    # Document formatting uses the primary local model by default. Keeping
    # one model avoids a second llama-server startup and prevents a broken
    # optional document-model file from disabling PDF creation. A separate
    # model remains opt-in through ALMOND_DEV_MODEL__DOCUMENT_MODEL.
    document_model: str = "MiniCPM5-2B-Q4_K_M.gguf"


class DeveloperConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALMOND_DEV_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    model: ModelSettings = ModelSettings()
    user_id: str = "local"
    role: str = "developer"
    rag_top_k: int = Field(5, ge=1, le=20)
    embedding_model: str = "keyword-local"
    log_level: str = "INFO"
    ui_density: Literal["compact", "comfortable"] = "comfortable"
    streaming: bool = True
    # Local developer control bridge (almond_ai.control). Disabled by default
    # on every machine; set ALMOND_DEV_CONTROL_ENABLED=true to enable it.
    control_enabled: bool = False

    def safe_summary(self) -> dict[str, object]:
        data = self.model.model_dump(exclude={"api_key"}, mode="json")
        return {"model": data, "rag_top_k": self.rag_top_k, "role": self.role}


def load_developer_config() -> DeveloperConfig:
    return DeveloperConfig()
