"""
LLM Provider abstraction.

Switch LLM with a single env var: LLM_PROVIDER=groq|openai|azure|anthropic|ollama
No code changes in any other file.
"""
import logging
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache()
def get_llm() -> BaseChatModel:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    model = settings.llm_model
    temp = settings.llm_temperature
    retries = settings.llm_max_retries

    logger.info(f"[LLM] Initialising provider={provider} model={model}")

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=temp,
            max_retries=retries,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            temperature=temp,
            max_retries=retries,
        )

    if provider == "azure":
        from langchain_openai import AzureChatOpenAI
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        # DefaultAzureCredential checks (in order):
        #   managed identity → workload identity → env vars (AZURE_CLIENT_ID/SECRET/TENANT_ID)
        #   → Azure CLI → VS Code auth
        # Token caching and rotation are handled automatically.
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default",
        )
        return AzureChatOpenAI(
            azure_ad_token_provider=token_provider,
            azure_endpoint=settings.azure_openai_endpoint,
            azure_deployment=settings.azure_openai_deployment_name,
            api_version=settings.azure_openai_api_version,
            temperature=temp,
            max_retries=retries,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            temperature=temp,
            max_retries=retries,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model,
            base_url=settings.ollama_base_url,
            temperature=temp,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER='{provider}'. "
        "Valid values: groq, openai, azure, anthropic, ollama"
    )
