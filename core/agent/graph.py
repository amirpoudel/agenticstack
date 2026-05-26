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

from api.models import ChatRequest, ChatResponse, StructuredOutputSchema, ToolCall, ToolResultsRequest
from core.agent.tool_binder import bind_tools_to_llm
from core.llm.provider import get_llm


class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    llm: BaseChatModel
    user_context: Dict[str, Any]
    state: Dict[str, Any]
    system_prompt: Optional[str]
    structured_output: Optional[StructuredOutputSchema]


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


def _structured_output_messages(
    schema: StructuredOutputSchema,
    reply_text: str,
) -> List[BaseMessage]:
    schema_json = json.dumps(schema.schema, ensure_ascii=True, sort_keys=True, default=str)
    return [
        SystemMessage(
            content=(
                "Convert the assistant reply into the requested structured output. "
                "Return only data that conforms to the schema."
            )
        ),
        HumanMessage(
            content=(
                f"Schema name: {schema.name}\n"
                f"Schema description: {schema.description}\n"
                f"JSON schema:\n{schema_json}\n\n"
                f"Assistant reply to convert:\n{reply_text}"
            )
        ),
    ]


def _normalize_structured_response(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if isinstance(payload, (dict, list, int, float, bool)) or payload is None:
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


async def _format_structured_response(
    reply_text: str,
    schema: StructuredOutputSchema,
    app,
) -> Any:
    if not schema.schema:
        raise ValueError("structuredOutput.schema must not be empty")

    formatter_llm = get_llm(temperature=getattr(app, "llm_temperature", None))
    messages = _structured_output_messages(schema, reply_text)

    try:
        payload = await formatter_llm.with_structured_output(schema.schema).ainvoke(messages)
        return _normalize_structured_response(payload)
    except Exception:
        fallback_response = await formatter_llm.ainvoke(messages)
        return _normalize_structured_response(_message_content(fallback_response.content))


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
        structured_output=request.structuredOutput or getattr(app, "structured_output", None),
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
    print(f"Workflow result: {result}")
    messages = list(result.get("messages", []))
    ai_message = _extract_ai_message(messages)
    
    if not ai_message:
        return ChatResponse(status="error", error="LLM returned no assistant message")

    if ai_message.tool_calls:
        app_structured_output = getattr(app, "structured_output", None)
        turn_id = turn_store.save_turn(
            request.userId,
            messages,
            state={
                "user_context": request.userContext or {},
                "state": {**(getattr(app, "state", {}) or {}), **(request.state or {})},
                "system_prompt": request.systemPrompt or getattr(app, "system_prompt", None),
                "structured_output": request.structuredOutput.model_dump(mode="json") if request.structuredOutput else (app_structured_output.model_dump(mode="json") if app_structured_output else None),
            },
        )
        return ChatResponse(
            status="tool_calls",
            toolCalls=_tool_calls_from_message(ai_message),
            turnId=turn_id,
        )

    structured_output = runtime_state.get("structured_output")
    if structured_output:
        structured_response = await _format_structured_response(
            reply_text=_message_content(ai_message.content),
            schema=structured_output,
            app=app,
        )
        return ChatResponse(
            status="reply",
            reply=json.dumps(structured_response, ensure_ascii=True, default=str),
            structuredResponse=structured_response,
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
        "structured_output": (StructuredOutputSchema(**saved_state["structured_output"]) if saved_state.get("structured_output") else None),
    }

    result = await workflow.ainvoke(runtime_state)
    messages = list(result.get("messages", []))
    ai_message = _extract_ai_message(messages)

    if not ai_message:
        return ChatResponse(status="error", error="LLM returned no assistant message")

    if ai_message.tool_calls:
        response = ChatResponse(
            status="tool_calls",
            toolCalls=_tool_calls_from_message(ai_message),
        )
    else:
        structured_output = runtime_state.get("structured_output")
        if structured_output:
            structured_response = await _format_structured_response(
                reply_text=_message_content(ai_message.content),
                schema=structured_output,
                app=app,
            )
            response = ChatResponse(
                status="reply",
                reply=json.dumps(structured_response, ensure_ascii=True, default=str),
                structuredResponse=structured_response,
            )
        else:
            response = ChatResponse(
                status="reply",
                reply=_message_content(ai_message.content),
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
