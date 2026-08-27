"""Paradigm 1: strict schema + repair loop.

Supports OpenAI (gpt-*, o1-*) and Anthropic (claude-*) models via prefix
routing. Captures resolved model version from each API response.

Temperature handling: some newer OpenAI models (GPT-5.6 family, o1/o3/o4
reasoning models) only accept the default temperature and reject explicit
values. We detect these and omit the temperature parameter for them.
"""

import json
import time
from typing import Optional

from pydantic import BaseModel, ValidationError

from schemaeval.errors import summarize_parse_error, summarize_validation_error

_openai_client = None
_anthropic_client = None


# Model families that reject explicit temperature. Match by prefix.
# As of Aug 2026: GPT-5.6 family (Sol/Terra/Luna), OpenAI reasoning models,
# and Claude Sonnet 5 / Opus 4.8 (Anthropic's newest generation).
_TEMPERATURE_LOCKED_PREFIXES = (
    "gpt-5.6",
    "o1",
    "o3",
    "o4",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-fable-5",
)


def _requires_default_temperature(model: str) -> bool:
    return any(model.startswith(p) for p in _TEMPERATURE_LOCKED_PREFIXES)


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        _anthropic_client = Anthropic()
    return _anthropic_client


def _dispatch(messages: list, model: str, temperature: float) -> dict:
    """Route to the right provider based on model name prefix.

    Returns a dict with raw, input_tokens, output_tokens, resolved_model.
    """
    if model.startswith("gpt-") or model.startswith("o1-") or model.startswith("o3") or model.startswith("o4"):
        client = _get_openai()
        kwargs = {"model": model, "messages": messages}
        # Only pass temperature to models that accept it. GPT-5.6 family and
        # reasoning models require the default and reject explicit values.
        if not _requires_default_temperature(model):
            kwargs["temperature"] = temperature
        resp = client.chat.completions.create(**kwargs)
        return {
            "raw": resp.choices[0].message.content or "",
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
            "resolved_model": resp.model,
        }
    elif model.startswith("claude-"):
        client = _get_anthropic()
        system_msg = next(
            (m["content"] for m in messages if m["role"] == "system"), None
        )
        chat = [m for m in messages if m["role"] != "system"]
        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "system": system_msg or "",
            "messages": chat,
        }
        # Newer Anthropic models (Sonnet 5, Opus 4.8, Fable 5) reject
        # explicit temperature the same way GPT-5.6 does.
        if not _requires_default_temperature(model):
            kwargs["temperature"] = temperature
        resp = client.messages.create(**kwargs)
        # Newer models (Sonnet 5, Opus 4.8, Fable 5) may return multi-block
        # content: [ThinkingBlock(...), TextBlock(text=...)] when extended
        # thinking is active. Older Claude models return a single TextBlock.
        # Extract only the visible text blocks; ignore internal thinking.
        text = "".join(
            b.text for b in (resp.content or []) if hasattr(b, "text")
        )
        return {
            "raw": text,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "resolved_model": resp.model,
        }
    else:
        raise ValueError(f"Unknown model provider for: {model}")


def call_llm_strict_repair(
    prompt: str,
    schema: type[BaseModel],
    model: str = "gpt-4o-mini",
    max_retries: int = 3,
    temperature: float = 0.0,
) -> tuple[Optional[BaseModel], dict]:
    """Send prompt, validate response, repair on failure.

    Returns (validated_output_or_None, metrics).
    Each attempt entry includes resolved_model_version.
    """
    schema_json = schema.model_json_schema()
    system_msg = (
        "You must respond with a single JSON object matching this schema.\n"
        "Return ONLY the JSON — no markdown code fences, no prose, no explanation.\n\n"
        f"Schema:\n{json.dumps(schema_json, indent=2)}"
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]

    total_in = 0
    total_out = 0
    num_repairs = 0
    last_error: Optional[str] = None
    attempts: list[dict] = []
    start = time.time()

    for attempt_num in range(max_retries + 1):
        try:
            call = _dispatch(messages, model=model, temperature=temperature)
        except Exception as e:
            last_error = f"api_error: {e}"
            attempts.append({
                "attempt_num": attempt_num,
                "raw_output": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "validation_ok": False,
                "resolved_model_version": None,
                "error_summary": {
                    "categories": ["api_error"],
                    "primary_category": "api_error",
                    "errors": [{
                        "category": "api_error",
                        "loc": "", "type": type(e).__name__, "msg": str(e),
                    }],
                },
            })
            break

        total_in += call["input_tokens"]
        total_out += call["output_tokens"]
        raw = call["raw"]

        error_summary = None
        validated = None
        try:
            validated = schema.model_validate_json(raw)
        except ValidationError as ve:
            error_summary = summarize_validation_error(ve, raw_output=raw)
            last_error = str(ve)
        except (ValueError, json.JSONDecodeError) as pe:
            error_summary = summarize_parse_error(pe, raw_output=raw)
            last_error = str(pe)

        attempts.append({
            "attempt_num": attempt_num,
            "raw_output": raw,
            "input_tokens": call["input_tokens"],
            "output_tokens": call["output_tokens"],
            "validation_ok": validated is not None,
            "resolved_model_version": call.get("resolved_model"),
            "error_summary": error_summary,
        })

        if validated is not None:
            return validated, _metrics(total_in, total_out, num_repairs, start,
                                       success=True, error=None, attempts=attempts)

        num_repairs += 1
        if attempt_num < max_retries:
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": (
                    "Your JSON failed validation with these errors:\n"
                    f"{last_error}\n\n"
                    "Return corrected JSON matching the schema. "
                    "ONLY JSON, no prose."
                ),
            })

    return None, _metrics(total_in, total_out, num_repairs, start,
                          success=False, error=last_error, attempts=attempts)


def _metrics(in_tok, out_tok, repairs, start, success, error, attempts):
    return {
        "total_input_tokens": in_tok,
        "total_output_tokens": out_tok,
        "num_repairs": repairs,
        "latency_sec": round(time.time() - start, 3),
        "success": success,
        "final_error": error,
        "attempts": attempts,
    }