from __future__ import annotations

from mvgeos_core.telemetry import (
    GEN_AI_AGENT_NAME,
    GEN_AI_CONVERSATION_ID,
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_REQUEST_TEMPERATURE,
    GEN_AI_REQUEST_TOP_P,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_SYSTEM,
    GEN_AI_TOOL_CALL_ID,
    GEN_AI_TOOL_DEFINITIONS,
    GEN_AI_TOOL_NAME,
    GEN_AI_TOOL_TYPE,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    GEN_AI_USAGE_TOTAL_TOKENS,
    MVGEOS_ORCHESTRATOR,
    create_genai_chat_attributes,
    create_genai_tool_attributes,
    derive_provider_from_model,
)


def test_genai_semantic_convention_constants() -> None:
    assert GEN_AI_SYSTEM == "gen_ai.system"
    assert GEN_AI_OPERATION_NAME == "gen_ai.operation.name"
    assert GEN_AI_AGENT_NAME == "gen_ai.agent.name"
    assert GEN_AI_CONVERSATION_ID == "gen_ai.conversation.id"
    assert GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
    assert GEN_AI_RESPONSE_MODEL == "gen_ai.response.model"
    assert GEN_AI_REQUEST_TEMPERATURE == "gen_ai.request.temperature"
    assert GEN_AI_REQUEST_MAX_TOKENS == "gen_ai.request.max_tokens"
    assert GEN_AI_REQUEST_TOP_P == "gen_ai.request.top_p"
    assert GEN_AI_USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"
    assert GEN_AI_USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"
    assert GEN_AI_USAGE_TOTAL_TOKENS == "gen_ai.usage.total_tokens"
    assert GEN_AI_RESPONSE_FINISH_REASONS == "gen_ai.response.finish_reasons"
    assert GEN_AI_TOOL_NAME == "gen_ai.tool.name"
    assert GEN_AI_TOOL_CALL_ID == "gen_ai.tool.call.id"
    assert GEN_AI_TOOL_TYPE == "gen_ai.tool.type"
    assert GEN_AI_TOOL_DEFINITIONS == "gen_ai.tool.definitions"
    assert MVGEOS_ORCHESTRATOR == "mvgeos.orchestrator"


def test_derive_provider_from_model() -> None:
    assert derive_provider_from_model("anthropic/claude-opus-4.6") == "anthropic"
    assert derive_provider_from_model("openai/gpt-4o") == "openai"
    assert derive_provider_from_model("google/gemini-2.5-pro") == "google"
    assert (
        derive_provider_from_model("claude-3-sonnet", realm="anthropic") == "anthropic"
    )
    assert derive_provider_from_model("custom-model") == ""


def test_create_genai_chat_attributes() -> None:
    attrs = create_genai_chat_attributes(
        model="anthropic/claude-opus-4.6",
        conversation_id="tome-123",
        agent_name="coding_mvge",
        temperature=0.7,
        max_tokens=4096,
        top_p=0.9,
    )
    assert attrs[GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GEN_AI_SYSTEM] == "anthropic"
    assert attrs[GEN_AI_REQUEST_MODEL] == "anthropic/claude-opus-4.6"
    assert attrs[GEN_AI_CONVERSATION_ID] == "tome-123"
    assert attrs[GEN_AI_AGENT_NAME] == "coding_mvge"
    assert attrs[GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert attrs[GEN_AI_REQUEST_MAX_TOKENS] == 4096
    assert attrs[GEN_AI_REQUEST_TOP_P] == 0.9
    assert attrs[MVGEOS_ORCHESTRATOR] == "mvgeos"


def test_create_genai_chat_attributes_defaults() -> None:
    attrs = create_genai_chat_attributes(model="openai/gpt-4o")
    assert attrs[GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GEN_AI_SYSTEM] == "openai"
    assert attrs[GEN_AI_REQUEST_MODEL] == "openai/gpt-4o"
    assert attrs[MVGEOS_ORCHESTRATOR] == "mvgeos"
    assert GEN_AI_CONVERSATION_ID not in attrs
    assert GEN_AI_AGENT_NAME not in attrs
    assert GEN_AI_REQUEST_TEMPERATURE not in attrs
    assert GEN_AI_REQUEST_MAX_TOKENS not in attrs
    assert GEN_AI_REQUEST_TOP_P not in attrs


def test_create_genai_tool_attributes() -> None:
    attrs = create_genai_tool_attributes(
        tool_name="read_file",
        tool_call_id="call_abc123",
        tool_definitions='{"type": "object"}',
    )
    assert attrs[GEN_AI_OPERATION_NAME] == "execute_tool"
    assert attrs[GEN_AI_TOOL_NAME] == "read_file"
    assert attrs[GEN_AI_TOOL_CALL_ID] == "call_abc123"
    assert attrs[GEN_AI_TOOL_TYPE] == "function"
    assert attrs[GEN_AI_TOOL_DEFINITIONS] == '{"type": "object"}'


def test_create_genai_tool_attributes_minimal() -> None:
    attrs = create_genai_tool_attributes(tool_name="list_dir")
    assert attrs[GEN_AI_OPERATION_NAME] == "execute_tool"
    assert attrs[GEN_AI_TOOL_NAME] == "list_dir"
    assert attrs[GEN_AI_TOOL_TYPE] == "function"
    assert GEN_AI_TOOL_CALL_ID not in attrs
    assert GEN_AI_TOOL_DEFINITIONS not in attrs
