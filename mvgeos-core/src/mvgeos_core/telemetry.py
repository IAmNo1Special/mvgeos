"""OpenTelemetry Generative AI Semantic Conventions and telemetry helpers.

Strictly follows open-telemetry/semantic-conventions-genai v1.42+ standard.
Zero external dependencies; pure standard library constants and helpers.
"""

from __future__ import annotations

from typing import Any

# GenAI Semantic Convention Attribute Keys (v1.42+)
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_TOP_P = "gen_ai.request.top_p"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_TOOL_TYPE = "gen_ai.tool.type"
GEN_AI_TOOL_DEFINITIONS = "gen_ai.tool.definitions"

# MvgeOS-specific orchestrator identifier
MVGEOS_ORCHESTRATOR = "mvgeos.orchestrator"


def derive_provider_from_model(model_id: str, realm: str = "") -> str:
    """Derive the foundation model provider from model ID prefix or realm."""
    if "/" in model_id:
        return model_id.split("/", 1)[0].lower()
    if realm:
        return realm.lower()
    return ""


def create_genai_chat_attributes(
    model: str,
    conversation_id: str = "",
    agent_name: str = "",
    realm: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> dict[str, Any]:
    """Create standard OpenTelemetry GenAI chat span attributes."""
    provider = derive_provider_from_model(model, realm=realm)
    attrs: dict[str, Any] = {
        GEN_AI_OPERATION_NAME: "chat",
        GEN_AI_SYSTEM: provider,
        GEN_AI_REQUEST_MODEL: model,
        MVGEOS_ORCHESTRATOR: "mvgeos",
    }
    if conversation_id:
        attrs[GEN_AI_CONVERSATION_ID] = conversation_id
    if agent_name:
        attrs[GEN_AI_AGENT_NAME] = agent_name
    if temperature is not None:
        attrs[GEN_AI_REQUEST_TEMPERATURE] = temperature
    if max_tokens is not None:
        attrs[GEN_AI_REQUEST_MAX_TOKENS] = max_tokens
    if top_p is not None:
        attrs[GEN_AI_REQUEST_TOP_P] = top_p
    return attrs


def create_genai_tool_attributes(
    tool_name: str,
    tool_call_id: str = "",
    tool_type: str = "function",
    tool_definitions: str = "",
) -> dict[str, Any]:
    """Create standard OpenTelemetry GenAI tool span attributes."""
    attrs: dict[str, Any] = {
        GEN_AI_OPERATION_NAME: "execute_tool",
        GEN_AI_TOOL_NAME: tool_name,
        GEN_AI_TOOL_TYPE: tool_type,
    }
    if tool_call_id:
        attrs[GEN_AI_TOOL_CALL_ID] = tool_call_id
    if tool_definitions:
        attrs[GEN_AI_TOOL_DEFINITIONS] = tool_definitions
    return attrs


__all__ = [
    "GEN_AI_AGENT_NAME",
    "GEN_AI_CONVERSATION_ID",
    "GEN_AI_OPERATION_NAME",
    "GEN_AI_REQUEST_MAX_TOKENS",
    "GEN_AI_REQUEST_MODEL",
    "GEN_AI_REQUEST_TEMPERATURE",
    "GEN_AI_REQUEST_TOP_P",
    "GEN_AI_RESPONSE_FINISH_REASONS",
    "GEN_AI_RESPONSE_MODEL",
    "GEN_AI_SYSTEM",
    "GEN_AI_TOOL_CALL_ID",
    "GEN_AI_TOOL_DEFINITIONS",
    "GEN_AI_TOOL_NAME",
    "GEN_AI_TOOL_TYPE",
    "GEN_AI_USAGE_INPUT_TOKENS",
    "GEN_AI_USAGE_OUTPUT_TOKENS",
    "GEN_AI_USAGE_TOTAL_TOKENS",
    "MVGEOS_ORCHESTRATOR",
    "create_genai_chat_attributes",
    "create_genai_tool_attributes",
    "derive_provider_from_model",
]
