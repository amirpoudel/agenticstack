"""
LLM Provider abstraction.

Global default: LLM_PROVIDER / LLM_MODEL / LLM_TEMPERATURE env vars.
Per-app override: pass provider / model / temperature to get_llm().
Instances are cached by (provider, model, temperature, retries) so the same
combination is only constructed once.
"""
import logging
from functools import lru_cache
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import get_settings

logger = logging.getLogger(__name__)


def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> BaseChatModel:
    """Return a (cached) LLM instance.

    Falls back to global env-var defaults for any parameter not supplied.
    """
    settings = get_settings()
    _provider = (provider or settings.llm_provider).lower()
    _model = model or settings.llm_model
    _temp = temperature if temperature is not None else settings.llm_temperature
    _retries = settings.llm_max_retries
    return _create_llm(_provider, _model, _temp, _retries)


@lru_cache(maxsize=32)
def _create_llm(provider: str, model: str, temperature: float, retries: int) -> BaseChatModel:
    """Construct and cache an LLM for the given (provider, model, temperature, retries) combo."""
    logger.info(f"[LLM] Initialising provider={provider} model={model}")

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model,
            api_key=get_settings().groq_api_key,
            temperature=temperature,
            max_retries=retries,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=get_settings().openai_api_key,
            temperature=temperature,
            max_retries=retries,
        )

    if provider == "azure":
        from langchain_openai import AzureChatOpenAI
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        settings = get_settings()
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
            temperature=temperature,
            max_retries=retries,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=get_settings().anthropic_api_key,
            temperature=temperature,
            max_retries=retries,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model,
            base_url=get_settings().ollama_base_url,
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        "Valid values: groq, openai, azure, anthropic, ollama"
    )
