"""LangGraph chat runtime for AgenticStack.

The API supplies a per-turn request payload, and this module turns that into a
runtime state object. Callers can override the default behaviour by passing a
structured `state` object in ChatRequest.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Annotated, Dict, List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from api.models import ChatRequest, ChatResponse, ToolCall, ToolResultsRequest
from core.agent.tool_binder import bind_tools_to_llm
from core.llm.provider import get_llm

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    llm: BaseChatModel
    app_description: str
    memories: List[str]
    user_name: Optional[str]
    user_phone: Optional[str]
    is_new_session: bool
    turn_hints: List[str]
    state: Dict[str, Any]
    system_prompt: Optional[str]   # per-turn override OR app-level system prompt
    metadata: Dict[str, Any]


llm = get_llm()


def _render_state_block(state: Dict[str, Any] | None) -> str:
    if not state:
        return ""

    lines: list[str] = []
    for key in sorted(state.keys()):
        value = state.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list, tuple)):
            rendered = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
        else:
            rendered = str(value)
        lines.append(f"- {key}: {rendered}")
    return "\n".join(lines)


def _build_runtime_prompt(state: AgentState) -> str:
    # Use the system_prompt verbatim if provided (per-turn override or app-level)
    base_prompt = (state.get("system_prompt") or "").strip()
    if not base_prompt:
        description = (state.get("app_description") or "").strip()
        base_prompt = description or "You are a helpful assistant."

    # Append long-term memory facts
    memories = state.get("memories") or []
    if memories:
        facts = "\n".join(f"- {m.strip()}" for m in memories if m and m.strip())
        if facts:
            base_prompt = f"{base_prompt}\n\nUSER MEMORY:\n{facts}"

    # Append structured turn state
    state_block = _render_state_block(state.get("state"))
    if state_block:
        base_prompt = f"{base_prompt}\n\nTURN STATE:\n{state_block}"

    return base_prompt


def _extract_ai_message(messages: List[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _message_content(message: Any) -> str:
    if isinstance(message, list):
        text_parts: list[str] = []
        for part in message:
            if isinstance(part, dict):
                text_parts.append(str(part.get("text", "")))
            else:
                text_parts.append(str(part))
        return "".join(text_parts).strip()
    return str(message).strip()


def _tool_calls_from_message(message: AIMessage) -> List[ToolCall]:
    tool_calls: List[ToolCall] = []
    for tool_call in message.tool_calls or []:
        tool_calls.append(
            ToolCall(
                id=str(tool_call.get("id", "")),
                name=str(tool_call.get("name", "")),
                args=dict(tool_call.get("args", {}) or {}),
            )
        )
    return tool_calls


def _runtime_state_for_request(
    request: ChatRequest,
    app,
    memories: Optional[List[str]] = None,
    previous_messages: Optional[List[BaseMessage]] = None,
) -> AgentState:
    runtime_llm = bind_tools_to_llm(get_llm(), app.tools)
    human_message = HumanMessage(content=request.message)
    messages = list(previous_messages or [])
    messages.append(human_message)

    app_state = getattr(app, "state", {}) or {}
    turn_state = {**app_state, **(request.state or {})}

    # Per-turn systemPrompt overrides app-level system_prompt
    effective_system_prompt = request.systemPrompt or getattr(app, "system_prompt", None)

    return AgentState(
        messages=messages,
        llm=runtime_llm,
        app_description=getattr(app, "description", ""),
        memories=memories or [],
        user_name=request.userName,
        user_phone=request.userPhone,
        is_new_session=request.isNewSession,
        turn_hints=request.turnHints or [],
        state=turn_state,
        system_prompt=effective_system_prompt,
        metadata=request.metadata or {},
    )


async def chat_node(state: AgentState) -> AgentState:
    messages = list(state.get("messages", []))
    runtime_prompt = _build_runtime_prompt(state)
    if runtime_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
        messages = [SystemMessage(content=runtime_prompt), *messages]

    runtime_llm = state.get("llm") or llm
    response = await runtime_llm.ainvoke(messages)
    return {"messages": [response]}


graph = StateGraph(AgentState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)
workflow = graph.compile()


async def run_chat_turn(
    request: ChatRequest,
    app,
    memory,
    conv_store,
    turn_store,
) -> ChatResponse:
    previous_messages: List[BaseMessage] = []
    if conv_store:
        if request.isNewSession:
            await conv_store.clear(request.userId)
        else:
            previous_messages = await conv_store.get_history(request.userId)

    memories: List[str] = []
    if memory:
        memories = await memory.search(request.userId, request.message)

    runtime_state = _runtime_state_for_request(
        request=request,
        app=app,
        memories=memories,
        previous_messages=previous_messages,
    )

    result = await workflow.ainvoke(runtime_state)
    messages = list(result.get("messages", []))
    ai_message = _extract_ai_message(messages)

    if not ai_message:
        return ChatResponse(status="error", error="LLM returned no assistant message")

    if ai_message.tool_calls:
        turn_id = turn_store.save_turn(
            request.userId,
            messages,
            state={
                "appName": request.resolved_app_name,
                "userId": request.userId,
                "app_description": getattr(app, "description", ""),
                "app_state": getattr(app, "state", {}) or {},
                "memories": memories,
                "user_name": request.userName,
                "user_phone": request.userPhone,
                "is_new_session": request.isNewSession,
                "turn_hints": request.turnHints or [],
                "state": {**(getattr(app, "state", {}) or {}), **(request.state or {})},
                "system_prompt": request.systemPrompt or getattr(app, "system_prompt", None),
                "metadata": request.metadata or {},
            },
        )
        response = ChatResponse(
            status="tool_calls",
            toolCalls=_tool_calls_from_message(ai_message),
            turnId=turn_id,
        )
    else:
        response = ChatResponse(
            status="reply",
            reply=_message_content(ai_message.content),
        )

    if conv_store:
        turn_messages: List[BaseMessage] = [HumanMessage(content=request.message)]
        turn_messages.append(ai_message)
        await conv_store.append_and_save(request.userId, turn_messages)

    return response


async def run_tool_results_turn(
    request: ToolResultsRequest,
    app,
    memory,
    conv_store,
    turn_store,
) -> ChatResponse:
    turn = turn_store.get_turn(request.turnId)
    if not turn:
        return ChatResponse(status="error", error=f"Unknown turnId '{request.turnId}'")

    base_messages = list(turn.get("messages", []))
    tool_messages: List[ToolMessage] = []
    for tool_result in request.toolResults:
        content = tool_result.result
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=True, default=str)
        tool_messages.append(
            ToolMessage(
                content=content,
                tool_call_id=tool_result.callId,
                name=tool_result.name,
            )
        )

    saved_state = turn.get("state", {})
    runtime_state: AgentState = {
        "messages": base_messages + tool_messages,
        "llm": bind_tools_to_llm(get_llm(), app.tools),
        "app_description": saved_state.get("app_description", getattr(app, "description", "")),
        "memories": saved_state.get("memories", []),
        "user_name": saved_state.get("user_name"),
        "user_phone": saved_state.get("user_phone"),
        "is_new_session": saved_state.get("is_new_session", False),
        "turn_hints": saved_state.get("turn_hints", []),
        "state": saved_state.get("state", {}),
        "system_prompt": saved_state.get("system_prompt"),
        "metadata": saved_state.get("metadata", {}),
    }

    result = await workflow.ainvoke(runtime_state)
    messages = list(result.get("messages", []))
    ai_message = _extract_ai_message(messages)

    if not ai_message:
        return ChatResponse(status="error", error="LLM returned no assistant message")

    response = ChatResponse(
        status="reply" if not ai_message.tool_calls else "tool_calls",
        reply=None if ai_message.tool_calls else _message_content(ai_message.content),
        toolCalls=_tool_calls_from_message(ai_message) if ai_message.tool_calls else None,
    )

    if ai_message.tool_calls:
        turn_id = turn_store.save_turn(
            request.userId,
            messages,
            state=saved_state,
        )
        response.turnId = turn_id

    if conv_store:
        await conv_store.append_and_save(request.userId, tool_messages + [ai_message])

    turn_store.remove_turn(request.turnId)
    return response
