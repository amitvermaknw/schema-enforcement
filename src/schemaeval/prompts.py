"""Prompt variants for schema-strict paradigm.

Experiment E tests whether Anthropic Haiku's markdown_wrap behavior is
prompt-driven or model-driven. Three variants of the system prompt:

    baseline   The standard "return ONLY the JSON, no markdown" instruction
               (control — all main experiments use this)
    aggressive Multi-line, capitalized, explicit anti-markdown enforcement
    few_shot   Baseline + CORRECT/INCORRECT format examples

Interpretation of Experiment E results:
    If markdown_wrap rate stays above ~40% across all three variants,
        the behavior is a model property that cannot be fixed by
        reasonable prompt engineering. This kills the reviewer
        objection "better prompting would fix it."
    If markdown_wrap drops below ~15% with aggressive or few_shot,
        the behavior is prompt-mitigatable and the paper reports it as
        a mitigation finding rather than an intrinsic model property.
"""

import json

_BACKTICK_FENCE = "`" * 3


def _baseline(schema_json_str: str) -> str:
    return (
        "You must respond with a single JSON object matching this schema.\n"
        "Return ONLY the JSON — no markdown code fences, no prose, no explanation.\n\n"
        f"Schema:\n{schema_json_str}"
    )


def _aggressive(schema_json_str: str) -> str:
    return (
        "CRITICAL: You MUST respond with a single JSON object matching the "
        "schema below.\n"
        "Do NOT use markdown formatting.\n"
        f"Do NOT wrap your response in code fences ({_BACKTICK_FENCE}json "
        f"or {_BACKTICK_FENCE}).\n"
        "Do NOT include any prose, explanation, or commentary.\n"
        "Your response MUST begin with { as the very first character.\n"
        "Any response starting with backticks or prose will be rejected.\n\n"
        f"Schema:\n{schema_json_str}"
    )


def _few_shot(schema_json_str: str) -> str:
    return (
        "You must respond with a single JSON object matching this schema.\n"
        "Return ONLY the JSON — no markdown code fences, no prose, no explanation.\n\n"
        "Example of a CORRECT response format:\n"
        '{"example_field": "example_value", "count": 3}\n\n'
        "Example of an INCORRECT response format (do not do this):\n"
        f"{_BACKTICK_FENCE}json\n"
        '{"example_field": "example_value", "count": 3}\n'
        f"{_BACKTICK_FENCE}\n\n"
        "The second example is wrong because it uses markdown code fences. "
        "Do not wrap JSON in backticks or code blocks.\n\n"
        f"Schema:\n{schema_json_str}"
    )


_PROMPT_BUILDERS = {
    "baseline": _baseline,
    "aggressive": _aggressive,
    "few_shot": _few_shot,
}


def build_system_prompt(schema: type, variant: str = "baseline") -> str:
    """Return the system prompt for the given schema and variant."""
    if variant not in _PROMPT_BUILDERS:
        raise ValueError(
            f"Unknown prompt variant '{variant}'. "
            f"Available: {sorted(_PROMPT_BUILDERS.keys())}"
        )
    schema_json_str = json.dumps(schema.model_json_schema(), indent=2)
    return _PROMPT_BUILDERS[variant](schema_json_str)


def available_variants() -> list[str]:
    return sorted(_PROMPT_BUILDERS.keys())