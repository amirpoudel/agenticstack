"""
All Pydantic request / response schemas for AgenticStack.

These are the ONLY contracts between AgenticStack and any calling application.
No domain terms here — domain knowledge lives in the caller's toolSchemas
and caller-defined prompts/tool schemas.

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
    required: List[str] = Field(default_factory=list)


class StructuredOutputSchema(BaseModel):
    """JSON Schema-like structured output contract passed to the LLM."""

    name: str = Field(default="structured_response")
    description: str = Field(default="Structured response schema for the assistant")
    schema: Dict[str, Any] = Field(default_factory=dict)


#  App registration (simplified) 

class RegisterAppRequest(BaseModel):
    """
    Register an agent app with AgenticStack.

    All behaviour is configured here — nothing is hardcoded in the stack.

    Fields:
      appName        — unique name for this app
        description    — optional app metadata (not used as runtime prompt)
        systemPrompt   — full runtime system prompt used by the model
      tools          — tool schemas the LLM may call; execution always happens
                       in the calling app
      state          — default state/context hints merged into every chat turn

      # Per-app LLM overrides (all optional — fall back to global env vars)
      llmProvider    — "groq" | "openai" | "azure" | "anthropic" | "ollama"
      llmModel       — model name (e.g. "gpt-4o", "claude-3-5-sonnet-20241022")
      llmTemperature — sampling temperature 0.0–2.0
      memoryEnabled  — whether long-term memory is active for this app;
                       defaults to the global MEMORY_ENABLED setting
    """
    appName: str
    description: str = ""
    systemPrompt: Optional[str] = None
    tools: List[ToolSchema] = Field(default_factory=list)
    state: Dict[str, Any] = Field(default_factory=dict)
    structuredOutput: Optional[StructuredOutputSchema] = None

    # Per-app overrides — fall back to global env var defaults when not set
    llmTemperature: Optional[float] = None
    memoryEnabled: Optional[bool] = None


class RegisterAppResponse(BaseModel):
    appName: str
    toolCount: int
    status: str  # "registered" | "updated" | "deleted"


class AppInfo(BaseModel):
    """Full app config returned by GET /v1/apps and GET /v1/apps/{app_name}."""
    appName: str
    description: str
    systemPrompt: Optional[str]
    tools: List[ToolSchema]
    state: Dict[str, Any]
    structuredOutput: Optional[StructuredOutputSchema]
    llmTemperature: Optional[float]
    memoryEnabled: Optional[bool]


#  Chat request (the ONLY endpoint callers use per-message) 

class ChatRequest(BaseModel):
    """
    Chat request. AgenticStack handles history + memory internally.

    Webhook flow:
      1. Caller POSTs /v1/chat with callbackUrl → gets {status: "accepted"}
      2. AgenticStack processes in background
      3. AgenticStack POSTs result to callbackUrl as WebhookEvent

    userId should be a composite ID that includes tenant scope if needed,
    e.g. "tenant123_user456". AgenticStack treats it as an opaque string.
    callbackUrl is required — all processing is asynchronous.
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
    callbackUrl: str

    # Full system prompt from caller (business logic lives in the caller).
    # When provided, AgenticStack uses this instead of the app-level system prompt.
    # AgenticStack still appends long-term memories.
    systemPrompt: Optional[str] = None

    # Arbitrary caller-defined key/value pairs identifying or describing the user.
    # Examples: {"plan": "pro", "locale": "en", "role": "admin"}
    # These are injected into the runtime prompt under a USER CONTEXT block so
    # the LLM can reference them. AgenticStack never interprets these keys.
    userContext: Optional[Dict[str, Any]] = None

    # Optional per-turn agent state overrides merged into the graph runtime.
    # Callers can use this to pass structured workflow flags (e.g. mode, filters).
    state: Optional[Dict[str, Any]] = None

    # Optional per-turn structured output override. When present, this takes
    # precedence over any app-level structuredOutput registration.
    structuredOutput: Optional[StructuredOutputSchema] = None

    # Opaque metadata — passed back unchanged in webhook events.
    # Callers use this to carry request context (e.g. session ID, tenant info).
    metadata: Optional[Dict[str, Any]] = None


class ToolCall(BaseModel):
    id: str
    name: str
    args: Dict[str, Any]


class ChatResponse(BaseModel):
    """
    Chat response. Possible states:
      - status="accepted"   → request accepted; result will come via callbackUrl webhook
      - status="reply"      → final AI reply delivered via webhook
      - status="tool_calls" → tool calls to execute, delivered via webhook
      - status="error"      → processing error
    """
    status: Literal["accepted", "reply", "tool_calls", "error"]
    reply: Optional[str] = None
    structuredResponse: Optional[Any] = None
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
    structuredResponse: Optional[Any] = None
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
    # Webhook URL — AgenticStack POSTs the next step here.
    callbackUrl: str
    # Opaque metadata — passed back unchanged in webhook events.
    metadata: Optional[Dict[str, Any]] = None


#  Memory endpoints 

class MemoryResponse(BaseModel):
    userId: str
    summary: Optional[str] = None
    facts: List[str] = Field(default_factory=list)


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
