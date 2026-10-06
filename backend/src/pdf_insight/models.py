"""Request/response dialects of the Workers AI text-generation models we support.

Workers AI exposes two input/output styles. Older models such as Llama 3.3 take
``response_format: {"type": "json_schema", "json_schema": <schema>}`` and return
``{"response": ...}``.
Newer models such as Gemma 4 take the OpenAI chat-completions style
``response_format: {"type": "json_schema", "json_schema": {"name", "schema", "strict"}}`` and return
``{"choices": [{"message": {"content": "<json>"}}]}``. Each supported model is listed explicitly
(per its catalog schema, checked 2026-10-05); an unknown ``AI_MODEL`` fails closed instead of being
called with a guessed format.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Style = Literal["workers", "openai"]


@dataclass(frozen=True)
class ModelProfile:
    style: Style
    extra_inputs: dict[str, Any] = field(default_factory=dict)


MODEL_PROFILES: dict[str, ModelProfile] = {
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": ModelProfile("workers"),
    # Experiment candidate (catalog checked 2026-10-06: 32 000-token context, response_format
    # json_schema, {"response": ...} output). Not the deployed model.
    "@cf/meta/llama-3.1-8b-instruct-fp8": ModelProfile("workers"),
    # Reasoning is on by default for Gemma 4; extraction does not need it and it adds latency.
    "@cf/google/gemma-4-26b-a4b-it": ModelProfile(
        "openai", {"chat_template_kwargs": {"enable_thinking": False}}
    ),
}


def profile_for(model: str) -> ModelProfile | None:
    return MODEL_PROFILES.get(model)


def build_inputs(
    profile: ModelProfile,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    if profile.style == "openai":
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {"name": "document_analysis", "schema": schema, "strict": True},
        }
    else:
        response_format = {"type": "json_schema", "json_schema": schema}
    return {
        "messages": messages,
        "response_format": response_format,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        **profile.extra_inputs,
    }


def output_content(raw: Any) -> Any:
    """Return the model's JSON payload (object or JSON string) from either response style."""
    if not isinstance(raw, dict):
        return raw
    if "response" in raw:
        return raw["response"]
    choices = raw.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            return message.get("content")
    return raw
