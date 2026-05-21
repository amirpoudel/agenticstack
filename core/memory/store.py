"""LangMem-backed long-term memory service.

The app-facing API stays small while LangMem handles extraction,
search, storage, and debounced background processing.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from langgraph.store.postgres import AsyncPostgresStore
from langmem import ReflectionExecutor, create_memory_store_manager

from config.settings import get_settings
from core.llm.provider import get_llm
from core.memory.embeddings import build_embeddings

logger = logging.getLogger(__name__)

# How long to wait before running background memory reflection.
_REFLECTION_DELAY_SECS: float = 30.0


class MemoryService:
    """Thin wrapper over LangMem's memory store manager and executor."""

    def __init__(self, store: AsyncPostgresStore) -> None:
        self._store = store
        self._manager = create_memory_store_manager(
            get_llm(),
            namespace=("memories", "{langgraph_user_id}"),
            store=store,
        )
        self._reflection = ReflectionExecutor(self._manager, store=store)

    @staticmethod
    def _config_for(user_id: str) -> Dict[str, Any]:
        return {
            "configurable": {
                "langgraph_user_id": user_id,
                "thread_id": user_id,
            }
        }

    @staticmethod
    def _extract_text(item: Any) -> str:
        value = getattr(item, "value", item)

        if hasattr(value, "content"):
            content = getattr(value, "content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, dict):
                nested = content.get("content") or content.get("text") or ""
                return str(nested).strip()

        if isinstance(value, dict):
            content = value.get("content")
            if isinstance(content, dict):
                nested = content.get("content") or content.get("text") or ""
                return str(nested).strip()
            if content is not None:
                return str(content).strip()

        return str(value).strip()

    async def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> List[str]:
        """Semantic search using LangMem's store manager."""
        try:
            results = await self._manager.asearch(
                query=query,
                limit=top_k,
                config=self._config_for(user_id),
            )
            facts = [text for text in (self._extract_text(r) for r in results) if text]
            logger.debug(f"[langmem] search({user_id}) → {len(facts)} results")
            return facts
        except Exception as e:
            logger.warning(f"[langmem] search failed — {e}")
            return []

    async def add(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        """Submit a turn to LangMem's reflection executor."""
        if not user_message:
            return
        try:
            payload = {"messages": [{"role": "user", "content": user_message}]}
            if assistant_reply:
                payload["messages"].append(
                    {"role": "assistant", "content": assistant_reply}
                )

            self._reflection.submit(
                payload,
                config=self._config_for(user_id),
                after_seconds=int(_REFLECTION_DELAY_SECS),
                thread_id=user_id,
            )
            logger.debug(
                f"[langmem] add({user_id}) — scheduled reflection in "
                f"{_REFLECTION_DELAY_SECS}s"
            )
        except Exception as e:
            logger.warning(f"[langmem] reflect scheduling failed — {e}")

    async def add_facts(
        self,
        user_id: str,
        facts: Dict[str, Any],
    ) -> None:
        """Store caller-supplied facts via LangMem's store manager."""
        if not facts:
            return
        try:
            for key, value in facts.items():
                self._manager.put(
                    key=f"explicit:{key}:{uuid.uuid4().hex}",
                    value={
                        "kind": "Memory",
                        "content": {"content": f"{key}: {value}"},
                    },
                    config=self._config_for(user_id),
                )
            logger.debug(f"[langmem] add_facts({user_id}) — {len(facts)} facts stored")
        except Exception as e:
            logger.warning(f"[langmem] add_facts failed — {e}")

    async def delete_user(self, user_id: str) -> None:
        """Delete all memories for a user."""
        try:
            items = await self._manager.asearch(
                query=None,
                limit=1000,
                config=self._config_for(user_id),
            )
            for item in items:
                await self._store.adelete(item.namespace, item.key)
            logger.info(f"[langmem] delete_user({user_id}) — {len(items)} deleted")
        except Exception as e:
            logger.warning(f"[langmem] delete_user failed — {e}")

    async def is_healthy(self) -> bool:
        """Verify store connectivity with a no-op search."""
        try:
            await self._store.asearch(("_health",), limit=1)
            return True
        except Exception:
            return False


# ── Module-level singleton ────────────────────────────────────────────────────

_service: Optional[MemoryService] = None
_store_ctx = None  # holds the async context manager


async def init_memory_service() -> None:
    """
    Create and connect the AsyncPostgresStore.
    Must be awaited from the FastAPI lifespan before any requests are served.
    Also initializes the conversation store (shared Postgres backend).
    """
    global _service, _store_ctx
    settings = get_settings()
    if not settings.memory_enabled:
        logger.info("[langmem] memory disabled — skipping init")
        return

    conn = (
        f"postgresql://{settings.langmem_postgres_user}"
        f":{settings.langmem_postgres_password}"
        f"@{settings.langmem_postgres_host}"
        f":{settings.langmem_postgres_port}"
        f"/{settings.langmem_postgres_db}"
    )

    embeddings = build_embeddings(settings)

    if embeddings:
        _store_ctx = AsyncPostgresStore.from_conn_string(
            conn,
            index={"dims": settings.embedding_dims, "embed": embeddings},
        )
    else:
        _store_ctx = AsyncPostgresStore.from_conn_string(conn)

    store = await _store_ctx.__aenter__()
    await store.setup()

    _service = MemoryService(store)
    logger.info(f"[langmem] LangMem store ready → {settings.langmem_postgres_host}")

    # Initialize conversation store using the same Postgres backend
    from core.conversation import init_conversation_store
    await init_conversation_store(store)


async def close_memory_service() -> None:
    """Close the store connection. Called from FastAPI lifespan cleanup."""
    global _service, _store_ctx

    if _service is not None:
        shutdown = getattr(_service._reflection, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown(wait=True)
            except Exception:
                pass

    if _store_ctx is not None:
        try:
            await _store_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        _store_ctx = None
    _service = None


def get_memory_service() -> Optional[MemoryService]:
    """FastAPI dependency — returns the singleton MemoryService."""
    return _service
