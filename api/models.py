"""
All Pydantic request / response schemas for AgenticStack.

These are the ONLY contracts between AgenticStack and any calling application.
No domain terms here — domain knowledge lives in the caller's toolSchemas
and appContext.agentPersonality.

Architecture:
  - AgenticStack manages ALL conversation history (working memory) and
    long-term memory internally. The caller never passes message history.
    - Tools are registered once per app name and retrieved by that name.
  - Chat is a simple POST /v1/chat with userId + message.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


#  Tool schemas (caller defines tools; AgenticStack binds them to LLM) 

class ToolSchema(BaseModel):
    """
    Caller declares what tools exist. AgenticStack binds them to the LLM.
    Execution happens in the calling app — AgenticStack only decides WHEN
    to call a tool and with WHAT args.
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str] = []


#  App registration (simplified) 

class RegisterAppRequest(BaseModel):
    """
    Register an agent app with AgenticStack.

    Fields:
      appName      — unique name for this app (e.g. "charkilla")
      description  — what this agent does; used as the system prompt base
                     when no explicit systemPrompt is provided
      systemPrompt — full custom system prompt (overrides description-based one)
      tools        — tool schemas the LLM may call
      state        — default state/context hints merged into every chat turn
    """
    appName: str
    description: str = ""
    systemPrompt: Optional[str] = None
    tools: List[ToolSchema] = Field(default_factory=list)
    state: Dict[str, Any] = Field(default_factory=dict)


class RegisterAppResponse(BaseModel):
    appName: str
    toolCount: int
    status: str  # "registered" | "already_registered"


#  Chat request (the ONLY endpoint callers use per-message) 

class ChatRequest(BaseModel):
    """
    Chat request. AgenticStack handles history + memory internally.

    Async webhook flow:
      1. Caller POSTs /v1/chat with callbackUrl → gets {status: "accepted"}
      2. AgenticStack processes in background
      3. AgenticStack POSTs result to callbackUrl as WebhookEvent

    userId should be a composite ID that includes tenant scope if needed,
    e.g. "tenant123_user456". AgenticStack treats it as an opaque string.
    """
    appId: str
    appName: Optional[str] = None
    userId: str
    message: str

    @property
    def resolved_app_name(self) -> str:
        """Return appName if set, otherwise fall back to appId."""
        return (self.appName or self.appId or "").strip()

    # Webhook URL — AgenticStack will POST results here (tool_calls or reply).
    # Required for async mode.
    callbackUrl: Optional[str] = None

    # Full system prompt from caller (business logic lives in the caller).
    # When provided, AgenticStack uses this instead of building its own.
    # AgenticStack still appends long-term memories.
    systemPrompt: Optional[str] = None

    # Optional per-turn overrides (used only if systemPrompt is NOT provided)
    userName: Optional[str] = None
    userPhone: Optional[str] = None
    isNewSession: bool = False
    turnHints: Optional[List[str]] = None
    memoryContext: Optional[Dict[str, Any]] = None

    # Optional per-turn agent state overrides merged into the graph runtime.
    # Callers can use this to pass structured flags such as propertyType,
    # listingType, locale, or any custom workflow hint.
    state: Optional[Dict[str, Any]] = None

    # Opaque metadata — passed back unchanged in webhook events.
    # Callers use this to carry request context (e.g. session ID, tenant info).
    metadata: Optional[Dict[str, Any]] = None


class ToolCall(BaseModel):
    id: str
    name: str
    args: Dict[str, Any]


class ChatResponse(BaseModel):
    """
    Chat response. Three possible states:
      - status="accepted"   → async mode; result will come via callbackUrl webhook
      - status="reply"      → sync mode; reply contains the AI response
      - status="tool_calls" → sync mode; toolCalls contains tools to execute
    """
    status: Literal["accepted", "reply", "tool_calls", "error"]
    reply: Optional[str] = None
    toolCalls: Optional[List[ToolCall]] = None
    turnId: Optional[str] = None
    error: Optional[str] = None


#  Webhook events (POSTed to callbackUrl) 

class WebhookEvent(BaseModel):
    """
    Event sent to the caller's callbackUrl.

    event types:
      - "tool_calls" → caller must execute tools and POST /v1/chat/tools
      - "reply"      → final AI reply; conversation turn is complete
      - "error"      → something went wrong
    """
    event: Literal["tool_calls", "reply", "error"]
    appId: str
    userId: str
    turnId: Optional[str] = None
    reply: Optional[str] = None
    toolCalls: Optional[List[ToolCall]] = None
    error: Optional[str] = None
    # Opaque metadata from original ChatRequest — passed back unchanged
    metadata: Optional[Dict[str, Any]] = None


#  Tool results (caller executes tools, sends results back) 

class ToolResult(BaseModel):
    callId: str
    name: str
    result: Any


class ToolResultsRequest(BaseModel):
    """Send tool execution results back to continue the conversation."""
    appId: str
    userId: str
    turnId: str
    toolResults: List[ToolResult]
    # Webhook URL for async mode — AgenticStack POSTs the next step here.
    callbackUrl: Optional[str] = None
    # Opaque metadata — passed back unchanged in webhook events.
    metadata: Optional[Dict[str, Any]] = None


#  Memory endpoints 

class MemoryResponse(BaseModel):
    userId: str
    summary: Optional[str] = None
    facts: List[str] = []


class MemoryWriteRequest(BaseModel):
    summary: Optional[str] = None


#  Health endpoints 

class HealthResponse(BaseModel):
    status: str
    llmProvider: str
    llmModel: str
    memoryEnabled: bool
    memoryConnected: bool
    registeredApps: int = 0
    version: str = "2.0.0"
