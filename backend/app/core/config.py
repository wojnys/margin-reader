from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]


def chat_reasoning_effort(value: object) -> ReasoningEffort:
    """Normalize the former numeric minimum for the chat endpoint's named enum."""
    if not isinstance(value, bool) and (value == 1 or value == "1"):
        return "low"
    if isinstance(value, str) and value in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
        return cast(ReasoningEffort, value)
    raise ValueError("Use a named reasoning effort: none, minimal, low, medium, high, xhigh, or max")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    deepinfra_api_key: SecretStr = SecretStr("")
    deepinfra_model: str = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
    deepinfra_base_url: str = "https://api.deepinfra.com/v1/openai"
    deepinfra_input_price: float = 0.098
    deepinfra_output_price: float = 0.294
    deepinfra_reasoning_effort: ReasoningEffort = "low"
    deepinfra_temperature: float = 1.0
    deepinfra_top_p: float = 0.95
    database_url: str = "postgresql+psycopg://margin:margin_local_dev@127.0.0.1:5437/margin"
    data_dir: Path = Path("data")
    temporal_address: str = "127.0.0.1:7323"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "margin-reading"
    phone_base_url: str = ""
    knowledge_enabled: bool = True
    knowledge_task_queue: str = "margin-knowledge"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    knowledge_evidence_tokens: int = 6000
    knowledge_reasoning_effort: ReasoningEffort = "none"

    @field_validator("deepinfra_reasoning_effort", "knowledge_reasoning_effort", mode="before")
    @classmethod
    def parse_reasoning_effort(cls, value: object) -> ReasoningEffort:
        return chat_reasoning_effort(value)


@lru_cache
def settings() -> Settings:
    return Settings()
