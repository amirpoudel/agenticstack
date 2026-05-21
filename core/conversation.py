"""
Conversation history store — working memory for active conversations.

Stores recent message history per user in PostgreSQL via LangGraph's
AsyncPostgresStore. This gives AgenticStack full ownership of conversation
context — callers never need to pass message history.

Each user's history is stored under namespace ("conversations", "{userId}").
A configurable window size controls how many recent messages are kept.
"""
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

# Max messages to keep in working memory per user
DEFAULT_WINDOW_SIZE = 20


def _conv_ns(user_id: str) -> tuple:
    """Namespace for a user's conversation history."""
    return ("conversations", user_id)


def serialize_message(msg: BaseMessage) -> Dict[str, Any]:
    """Convert a LangChain message to a plain dict for storage."""
    if isinstance(msg, SystemMessage):
        return {"type": "system", "content": str(msg.content)}
    elif isinstance(msg, HumanMessage):
        return {"type": "human", "content": str(msg.content)}
    elif isinstance(msg, AIMessage):
        # AIMessage.content can be a list of content parts when the model
        # returns tool_calls alongside text (Azure OpenAI behaviour).
        # Normalise to a plain string so deserialization is lossless.
        raw_content = msg.content
        if isinstance(raw_content, list):
            text_parts = [
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in raw_content
            ]
            content = "".join(text_parts)
        else:
            content = str(raw_content)
        entry: Dict[str, Any] = {"type": "ai", "content": content}
        if msg.tool_calls:
            entry["tool_calls"] = list(msg.tool_calls)
        return entry
    elif isinstance(msg, ToolMessage):
        return {
            "type": "tool",
            "content": str(msg.content),
            "tool_call_id": msg.tool_call_id,
            "name": msg.name or "",
        }
    return {"type": "unknown", "content": str(msg.content)}


def deserialize_message(raw: Dict[str, Any]) -> BaseMessage:
    """Restore a LangChain message from a plain dict."""
    t = raw.get("type")
    content = raw.get("content", "")
    if t == "system":
        return SystemMessage(content=content)
    elif t == "human":
        return HumanMessage(content=content)
    elif t == "ai":
        ai_msg = AIMessage(content=content)
        if raw.get("tool_calls"):
            ai_msg.tool_calls = raw["tool_calls"]
        return ai_msg
    elif t == "tool":
        return ToolMessage(
            content=content,
            tool_call_id=raw.get("tool_call_id", ""),
            name=raw.get("name", ""),
        )
    return HumanMessage(content=content)


class ConversationStore:
    """
    Manages conversation history (working memory) per user.

    Uses the same AsyncPostgresStore as long-term memory but with a
    different namespace prefix ("conversations" vs "memories").
    """

    def __init__(self, store, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        self._store = store
        self._window_size = window_size

    async def get_history(self, user_id: str) -> List[BaseMessage]:
        """Load the recent message history for a user."""
        ns = _conv_ns(user_id)
        try:
            # Use aget (key-value lookup) — conversation history never needs
            # vector/semantic search, and asearch() triggers embedding calls.
            result = await self._store.aget(ns, "history")
            if result:
                raw_messages = result.value.get("messages", [])
                return [deserialize_message(m) for m in raw_messages]
            return []
        except Exception as e:
            logger.warning(f"[convstore] get_history failed for {user_id}: {e}")
            return []

    async def save_history(self, user_id: str, messages: List[BaseMessage]) -> None:
        """Save the message history, trimming to window size."""
        ns = _conv_ns(user_id)
        # Keep only non-system messages in the window, trim oldest
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]
        if len(non_system) > self._window_size:
            non_system = non_system[-self._window_size:]
        # Drop any leading ToolMessages — they require a preceding AI
        # tool_calls message which may have been cut off by the trim above.
        # An orphaned ToolMessage causes a 400 from Azure OpenAI.
        while non_system and isinstance(non_system[0], ToolMessage):
            non_system = non_system[1:]

        serialized = [serialize_message(m) for m in non_system]
        try:
            # index=False — conversation history is plain key-value storage;
            # no vector embedding needed (and it would fail if embeddings
            # deployment is unavailable).
            await self._store.aput(ns, "history", {
                "messages": serialized,
                "updated_at": time.time(),
            }, index=False)
            logger.debug(f"[convstore] Saved {len(serialized)} messages for {user_id}")
        except Exception as e:
            logger.warning(f"[convstore] save_history failed for {user_id}: {e}")

    async def append_and_save(
        self,
        user_id: str,
        new_messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Load existing history, append new messages, save, and return full history."""
        existing = await self.get_history(user_id)
        combined = existing + new_messages
        await self.save_history(user_id, combined)
        return combined

    async def clear(self, user_id: str) -> None:
        """Clear conversation history for a user (e.g., new session)."""
        ns = _conv_ns(user_id)
        try:
            await self._store.adelete(ns, "history")
            logger.info(f"[convstore] Cleared history for {user_id}")
        except Exception as e:
            logger.warning(f"[convstore] clear failed for {user_id}: {e}")


# ── In-flight turn state (for tool-call loops) ───────────────────────────────

class TurnStore:
    """
    Stores in-flight turn state for tool-call loops.

    When the LLM requests tool calls, we need to preserve the message
    state until the caller sends back tool results. This is stored
    in-memory (not Postgres) since it's ephemeral and short-lived.
    """

    def __init__(self) -> None:
        self._turns: Dict[str, Dict[str, Any]] = {}

    def save_turn(
        self,
        user_id: str,
        messages: List[BaseMessage],
        state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save in-flight messages and return a turnId."""
        turn_id = str(uuid.uuid4())
        self._turns[turn_id] = {
            "user_id": user_id,
            "messages": messages,
            "state": state or {},
            "created_at": time.time(),
        }
        # Cleanup old turns (> 5 min)
        self._cleanup()
        return turn_id

    def get_turn(self, turn_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve in-flight turn state."""
        return self._turns.get(turn_id)

    def remove_turn(self, turn_id: str) -> None:
        """Remove a completed turn."""
        self._turns.pop(turn_id, None)

    def _cleanup(self) -> None:
        """Remove turns older than 5 minutes."""
        cutoff = time.time() - 300
        expired = [k for k, v in self._turns.items() if v["created_at"] < cutoff]
        for k in expired:
            del self._turns[k]


# ── Module-level singletons ──────────────────────────────────────────────────

_conv_store: Optional[ConversationStore] = None
_turn_store = TurnStore()


async def init_conversation_store(store) -> None:
    """Initialize with the same AsyncPostgresStore used for memory."""
    global _conv_store
    _conv_store = ConversationStore(store)
    logger.info("[convstore] Conversation store ready")


def get_conversation_store() -> Optional[ConversationStore]:
    return _conv_store


def get_turn_store() -> TurnStore:
    return _turn_store
