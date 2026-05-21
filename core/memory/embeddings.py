"""Embedding provider selection and initialization for long-term memory."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_embeddings(settings: Any):
    """
    Build an embeddings object for pgvector indexing.

    Embedding provider is selected independently from the chat LLM:
      EMBEDDING_PROVIDER=auto   → use llm_provider if it supports embeddings,
                                  else fall back to "none"
      EMBEDDING_PROVIDER=azure  → AzureOpenAIEmbeddings (token auto-refreshed)
      EMBEDDING_PROVIDER=openai → OpenAIEmbeddings
      EMBEDDING_PROVIDER=none   → no vector index (exact key-value only)

    This allows e.g. LLM_PROVIDER=groq + EMBEDDING_PROVIDER=openai.
    """
    ep = settings.embedding_provider.lower()
    if ep == "auto":
        ep = settings.llm_provider.lower()

    if ep == "azure" and settings.azure_openai_endpoint:
        try:
            import openai as _openai
            from azure.identity import ClientSecretCredential, get_bearer_token_provider
            from langchain_openai import AzureOpenAIEmbeddings

            credential = ClientSecretCredential(
                tenant_id=settings.azure_tenant_id,
                client_id=settings.azure_client_id,
                client_secret=settings.azure_client_secret,
            )
            token_provider = get_bearer_token_provider(
                credential,
                "https://cognitiveservices.azure.com/.default",
            )
            endpoint = (
                settings.azure_openai_embedding_endpoint
                or settings.azure_openai_endpoint
            )
            # AzureOpenAIEmbeddings reads AZURE_OPENAI_ENDPOINT from the
            # environment which points at the chat LLM resource, not the
            # embeddings resource. Build raw clients pinned to the embeddings
            # endpoint and inject them so the langchain wrapper cannot override.
            raw_sync = _openai.AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=settings.embedding_api_version,
                api_key="not-used",
            )
            raw_async = _openai.AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=settings.embedding_api_version,
                api_key="not-used",
            )
            emb = AzureOpenAIEmbeddings(
                azure_deployment=settings.embedding_model,
                openai_api_version=settings.embedding_api_version,
                api_key="dummy-not-used",
            )
            emb.client = raw_sync.embeddings
            emb.async_client = raw_async.embeddings
            logger.info(
                f"[langmem] Embeddings: azure / {settings.embedding_model} "
                f"endpoint={endpoint}"
            )
            return emb
        except Exception as e:
            logger.warning(
                f"[langmem] Azure embeddings init failed — {e}. "
                "Falling back to no-index store."
            )
            return None

    if ep == "openai":
        api_key = settings.openai_embedding_api_key or settings.openai_api_key
        if not api_key:
            logger.warning(
                "[langmem] EMBEDDING_PROVIDER=openai but no API key found. "
                "Falling back to no-index store."
            )
            return None
        try:
            from langchain_openai import OpenAIEmbeddings

            emb = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=api_key,
            )
            logger.info(
                f"[langmem] Embeddings: openai / {settings.embedding_model}"
            )
            return emb
        except Exception as e:
            logger.warning(f"[langmem] OpenAI embeddings init failed — {e}.")
            return None

    logger.info(
        f"[langmem] Embeddings: none "
        f"(provider '{ep}' has no embeddings support — exact-match only)"
    )
    return None