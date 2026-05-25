"""LangGraph chat runtime for AgenticStack.

The API supplies a per-turn request payload, and this module turns that into a
runtime state object. Callers can override default behaviour by passing a
structured `state` object and explicit `systemPrompt` in ChatRequest.
"""
from __future__ import annotations

import json
from typing import Any, Annotated, Dict, List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from api.models import ChatRequest, ChatResponse, ToolCall, ToolResultsRequest
from core.agent.tool_binder import bind_tools_to_llm
from core.llm.provider import get_llm


class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    llm: BaseChatModel
    user_context: Dict[str, Any]
    state: Dict[str, Any]
    system_prompt: Optional[str]


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
    # Strict mode: no description/default fallback. Prompt only comes from
    # explicit system_prompt plus optional context/state blocks.
    base_prompt = (state.get("system_prompt") or "").strip()

    user_context_block = _render_state_block(state.get("user_context"))
    if user_context_block:
        if base_prompt:
            base_prompt = f"{base_prompt}\n\nUSER CONTEXT:\n{user_context_block}"
        else:
            base_prompt = f"USER CONTEXT:\n{user_context_block}"

    state_block = _render_state_block(state.get("state"))
    if state_block:
        if base_prompt:
            base_prompt = f"{base_prompt}\n\nTURN STATE:\n{state_block}"
        else:
            base_prompt = f"TURN STATE:\n{state_block}"

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


def _runtime_state_for_request(request: ChatRequest, app) -> AgentState:
    runtime_llm = bind_tools_to_llm(
        get_llm(temperature=getattr(app, "llm_temperature", None)),
        app.tools,
    )
    app_state = getattr(app, "state", {}) or {}
    return AgentState(
        messages=[HumanMessage(content=request.message)],
        llm=runtime_llm,
        user_context=request.userContext or {},
        state={**app_state, **(request.state or {})},
        system_prompt=request.systemPrompt or getattr(app, "system_prompt", None),
    )


async def chat_node(state: AgentState) -> AgentState:
    messages = list(state.get("messages", []))
    runtime_prompt = _build_runtime_prompt(state)
    if runtime_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
        messages = [SystemMessage(content=runtime_prompt), *messages]

    runtime_llm = state.get("llm") or get_llm()
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
    turn_store,
) -> ChatResponse:
    runtime_state = _runtime_state_for_request(request=request, app=app)
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
                "user_context": request.userContext or {},
                "state": {**(getattr(app, "state", {}) or {}), **(request.state or {})},
                "system_prompt": request.systemPrompt or getattr(app, "system_prompt", None),
            },
        )
        return ChatResponse(
            status="tool_calls",
            toolCalls=_tool_calls_from_message(ai_message),
            turnId=turn_id,
        )

    return ChatResponse(
        status="reply",
        reply=_message_content(ai_message.content),
    )


async def run_tool_results_turn(
    request: ToolResultsRequest,
    app,
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
        "llm": bind_tools_to_llm(
            get_llm(temperature=getattr(app, "llm_temperature", None)),
            app.tools,
        ),
        "user_context": saved_state.get("user_context", {}),
        "state": saved_state.get("state", {}),
        "system_prompt": saved_state.get("system_prompt"),
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

    turn_store.remove_turn(request.turnId)
    return response
