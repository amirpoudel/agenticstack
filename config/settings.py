from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: str = "groq"          # groq | openai | azure | anthropic | ollama
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.2
    llm_max_retries: int = 2

    # Groq
    groq_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Azure OpenAI — only ENDPOINT and DEPLOYMENT_NAME are required.
    # Auth uses DefaultAzureCredential (managed identity / workload identity /
    # CLI / VS Code). For service-principal auth, set the three vars below and
    # DefaultAzureCredential will pick them up automatically via env vars.
    azure_openai_endpoint: str = ""
    azure_openai_deployment_name: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"
    # Optional — only needed for service-principal auth fallback:
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # ── Embeddings (independent of chat LLM provider) ─────────────────────────
    # embedding_provider controls which service handles vector embeddings for
    # long-term memory search. Can differ from llm_provider — e.g. chat=groq
    # with embeddings=openai, or chat=azure with embeddings=azure.
    # Supported: azure | openai | none  (default: auto — inherits llm_provider
    # if it supports embeddings, otherwise falls back to "none").
    embedding_provider: str = "auto"     # auto | azure | openai | none
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536
    # Azure embeddings use a separate API version from the chat LLM —
    # embeddings require 2024-02-01 (stable) not the preview chat version.
    embedding_api_version: str = "2024-02-01"
    # Azure embedding resource endpoint — may differ from the chat LLM resource.
    # Falls back to AZURE_OPENAI_ENDPOINT if not set.
    azure_openai_embedding_endpoint: str = ""
    # OpenAI embedding key — falls back to openai_api_key if not set.
    openai_embedding_api_key: str = ""

    # ── App database (registered_apps table, conversation history) ────────────
    # Plain PostgreSQL — no pgvector needed.
    app_postgres_host: str = "app_postgres"
    app_postgres_port: int = 5432
    app_postgres_db: str = "agenticstack"
    app_postgres_user: str = "agenticstack"
    app_postgres_password: str = "agenticstacksecret"

    # ── Memory (LangMem — LangGraph AsyncPostgresStore + pgvector) ───────────
    memory_enabled: bool = True
    langmem_postgres_host: str = "langmem_postgres"
    langmem_postgres_port: int = 5432
    langmem_postgres_db: str = "langmem"
    langmem_postgres_user: str = "langmem"
    langmem_postgres_password: str = "langmemsecret"

    # ── API ───────────────────────────────────────────────────────────────────
    api_key: str = ""                       # if set, all requests need X-Api-Key header
    cors_origins: List[str] = ["*"]
    log_level: str = "info"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
