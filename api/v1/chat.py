"""
Chat endpoint — the primary interface for all AI conversations.

POST /v1/chat         — Send a message, get a reply or tool_calls
POST /v1/chat/tools   — Send tool results back to continue the conversation

Supports two modes:
  SYNC  — callbackUrl omitted → blocks until LLM responds
  ASYNC — callbackUrl provided → returns {status: "accepted"} immediately,
           then POSTs result to callbackUrl as a WebhookEvent
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.models import (
    ChatRequest,
    ChatResponse,
    ToolResultsRequest,
    WebhookEvent,
)
from core.registry import AppRegistry, get_registry
from core.agent.graph import run_chat_turn, run_tool_results_turn
from core.memory.store import MemoryService, get_memory_service
from core.conversation import (
    ConversationStore,
    TurnStore,
    get_conversation_store,
    get_turn_store,
)
from core.webhook import dispatch_webhook
from api.auth import check_api_key

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])


def _response_to_webhook_event(
    resp: ChatResponse,
    app_id: str,
    user_id: str,
    metadata: dict | None = None,
) -> WebhookEvent:
    """Convert a ChatResponse into a WebhookEvent for callback dispatch."""
    if resp.status == "tool_calls":
        return WebhookEvent(
            event="tool_calls",
            appId=app_id,
            userId=user_id,
            turnId=resp.turnId,
            toolCalls=resp.toolCalls,
            metadata=metadata,
        )
    elif resp.status == "reply":
        return WebhookEvent(
            event="reply",
            appId=app_id,
            userId=user_id,
            reply=resp.reply,
            metadata=metadata,
        )
    else:
        return WebhookEvent(
            event="error",
            appId=app_id,
            userId=user_id,
            error=resp.error,
            metadata=metadata,
        )


async def _process_chat_and_dispatch(
    request: ChatRequest,
    app,
    memory,
    conv_store,
    turn_store,
) -> None:
    """Background task: run LLM turn, then POST result to callbackUrl."""
    try:
        result = await run_chat_turn(
            request=request,
            app=app,
            memory=memory,
            conv_store=conv_store,
            turn_store=turn_store,
        )
        event = _response_to_webhook_event(
            result, request.appId, request.userId, request.metadata,
        )
    except Exception as e:
        logger.error(f"[chat-bg] Error processing chat: {e}", exc_info=True)
        event = WebhookEvent(
            event="error",
            appId=request.appId,
            userId=request.userId,
            error=str(e),
            metadata=request.metadata,
        )
    await dispatch_webhook(request.callbackUrl, event)


async def _process_tools_and_dispatch(
    request: ToolResultsRequest,
    app,
    memory,
    conv_store,
    turn_store,
) -> None:
    """Background task: run tool-results turn, then POST result to callbackUrl."""
    try:
        result = await run_tool_results_turn(
            request=request,
            app=app,
            memory=memory,
            conv_store=conv_store,
            turn_store=turn_store,
        )
        event = _response_to_webhook_event(
            result, request.appId, request.userId, request.metadata,
        )
    except Exception as e:
        logger.error(f"[chat/tools-bg] Error processing tools: {e}", exc_info=True)
        event = WebhookEvent(
            event="error",
            appId=request.appId,
            userId=request.userId,
            error=str(e),
            metadata=request.metadata,
        )
    await dispatch_webhook(request.callbackUrl, event)


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a message and get AI response",
    description=(
        "Send a message with appId + userId. "
        "If callbackUrl is provided, returns {status: 'accepted'} immediately and "
        "POSTs the result to callbackUrl when ready. "
        "Otherwise blocks and returns the result directly."
    ),
)
async def chat(
    request: ChatRequest,
    registry: AppRegistry = Depends(get_registry),
    memory: MemoryService = Depends(get_memory_service),
    conv_store: ConversationStore = Depends(get_conversation_store),
    turn_store: TurnStore = Depends(get_turn_store),
    _: None = Depends(check_api_key),
) -> ChatResponse:
    app_name = request.resolved_app_name
    app = await registry.get(app_name)
    if not app:
        raise HTTPException(
            status_code=400,
            detail=f"App '{app_name}' not registered. Call POST /v1/apps/register first.",
        )

    # ── Async mode: fire-and-forget, respond immediately ──
    if request.callbackUrl:
        asyncio.create_task(
            _process_chat_and_dispatch(request, app, memory, conv_store, turn_store)
        )
        return ChatResponse(status="accepted")

    # ── Sync mode: block until done ──
    try:
        return await run_chat_turn(
            request=request,
            app=app,
            memory=memory,
            conv_store=conv_store,
            turn_store=turn_store,
        )
    except Exception as e:
        logger.error(f"[chat] Unhandled error: {e}", exc_info=True)
        return ChatResponse(status="error", error=str(e))


@router.post(
    "/chat/tools",
    response_model=ChatResponse,
    summary="Send tool execution results",
    description=(
        "After executing tool calls, send the results here. "
        "Include the turnId from the original response/webhook. "
        "If callbackUrl is provided, returns {status: 'accepted'} and "
        "POSTs the next step to callbackUrl."
    ),
)
async def chat_tool_results(
    request: ToolResultsRequest,
    registry: AppRegistry = Depends(get_registry),
    memory: MemoryService = Depends(get_memory_service),
    conv_store: ConversationStore = Depends(get_conversation_store),
    turn_store: TurnStore = Depends(get_turn_store),
    _: None = Depends(check_api_key),
) -> ChatResponse:
    app = await registry.get(request.appId)
    if not app:
        raise HTTPException(
            status_code=400,
            detail=f"App '{request.appId}' not registered.",
        )

    # ── Async mode ──
    if request.callbackUrl:
        asyncio.create_task(
            _process_tools_and_dispatch(request, app, memory, conv_store, turn_store)
        )
        return ChatResponse(status="accepted")

    # ── Sync mode ──
    try:
        return await run_tool_results_turn(
            request=request,
            app=app,
            memory=memory,
            conv_store=conv_store,
            turn_store=turn_store,
        )
    except Exception as e:
        logger.error(f"[chat/tools] Unhandled error: {e}", exc_info=True)
        return ChatResponse(status="error", error=str(e))
