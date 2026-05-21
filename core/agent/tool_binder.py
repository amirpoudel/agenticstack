"""
Tool binder — converts caller-supplied JSON Schema tool definitions
into LangChain-compatible tools bound to the LLM.

The LLM can then decide which tools to call and with what arguments.
AgenticStack never executes tools — it only decides on them.
The calling app (NestJS, Django, etc.) executes and returns results.
"""
import logging
from typing import Any, Dict, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from api.models import ToolSchema

logger = logging.getLogger(__name__)


def _json_schema_to_pydantic(name: str, properties: Dict[str, Any], required: List[str]):
    """
    Converts a JSON Schema 'properties' dict into a Pydantic model.
    Supports: string, number, integer, boolean, array, enum.
    """
    _TYPE_MAP = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "array": list,
    }

    field_definitions: Dict[str, Any] = {}
    for field_name, field_def in properties.items():
        json_type = field_def.get("type", "string")
        py_type = _TYPE_MAP.get(json_type, str)

        # Handle enum — just keep as str for simplicity
        if "enum" in field_def:
            py_type = str

        # Optional vs required
        if field_name in required:
            field_definitions[field_name] = (py_type, ...)
        else:
            from typing import Optional
            field_definitions[field_name] = (Optional[py_type], None)  # type: ignore[assignment]

    return create_model(f"{name}_schema", **field_definitions)


def bind_tools_to_llm(
    llm: BaseChatModel,
    tool_schemas: List[ToolSchema],
) -> BaseChatModel:
    """
    Binds caller-defined tool schemas to the LLM.
    Returns the LLM with tools registered — no execution logic.
    """
    tools = []
    for schema in tool_schemas:
        try:
            pydantic_model = _json_schema_to_pydantic(
                name=schema.name,
                properties=schema.parameters.get("properties", {}),
                required=schema.required,
            )

            # Dummy async function — execution happens in calling app
            async def _noop(**kwargs: Any) -> str:
                return ""

            _noop.__name__ = schema.name

            tool = StructuredTool(
                name=schema.name,
                description=schema.description,
                args_schema=pydantic_model,
                coroutine=_noop,
            )
            tools.append(tool)
            logger.debug(f"[tools] Bound tool: {schema.name}")
        except Exception as e:
            logger.warning(f"[tools] Could not bind tool '{schema.name}': {e}")

    if not tools:
        return llm

    return llm.bind_tools(tools)
