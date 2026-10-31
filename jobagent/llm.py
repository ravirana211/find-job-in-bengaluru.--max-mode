"""Thin wrapper around the Claude API for JSON-structured answers."""

import json

import anthropic

MODEL = "claude-opus-5-5"
# On a safety-classifier refusal the API retries on a suitable fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    pass


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4)
    return _client


def ask_json(system: str, user: str, schema: dict, effort: str = "low", max_tokens: int = 16000) -> dict:
    """Send one request and return the parsed JSON object matching `schema`."""
    request = dict(
        model=MODEL,
        max_tokens=max_tokens,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        # Long, stable system prompts (the candidate profile) are cached across calls.
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    try:
        with client().beta.messages.stream(**request) as stream:
            message = stream.get_final_message()
    except anthropic.RateLimitError as exc:
        raise LLMError(f"rate limited: {exc.message}") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("could not reach the Claude API") from exc

    if message.stop_reason == "refusal":
        raise LLMError("request was declined")
    if message.stop_reason == "max_tokens":
        raise LLMError("answer was cut off (max_tokens)")
    text = "".join(block.text for block in message.content if block.type == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"invalid JSON from model: {text[:200]}") from exc
