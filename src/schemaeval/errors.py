"""Classify Pydantic ValidationErrors into failure-mode categories.

Categories:
    regex_pattern       — Field.pattern mismatch
    length_bound        — min_length/max_length violated (string or list)
    range_bound         — ge/le/gt/lt violated on numeric field
    enum_violation      — Literal[...] value not in allowed set
    type_error          — wrong Python type entirely
    missing_field       — required field absent
    extra_field         — unexpected field present
    parse_error         — JSON itself was malformed
    schema_mirroring    — model returned the schema definition instead of an
                          instance (root-level keys like "properties",
                          "required", "type", "title" instead of the actual
                          fields). Discovered empirically in gpt-4o.
    cross_field_ref     — model_validator: cross-reference broken
                          (e.g. primary_entity_id not in entities)
    count_mismatch      — model_validator: declared count != list length
    categorical_numeric — model_validator: bucket doesn't match numeric value
    cross_field_other   — model_validator: any other custom check
    unknown             — untagged
"""

import json
import re

from pydantic import ValidationError


# Detects markdown code fences at the start of a response, with optional
# language tag (json, JSON, etc.). Matches:  ```json\n...  or  ```\n...
_MARKDOWN_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)


_PYDANTIC_ERROR_MAP = {
    "string_pattern_mismatch": "regex_pattern",
    "string_too_short": "length_bound",
    "string_too_long": "length_bound",
    "too_short": "length_bound",
    "too_long": "length_bound",
    "less_than_equal": "range_bound",
    "greater_than_equal": "range_bound",
    "less_than": "range_bound",
    "greater_than": "range_bound",
    "literal_error": "enum_violation",
    "missing": "missing_field",
    "extra_forbidden": "extra_field",
    "json_invalid": "parse_error",
    "json_type": "parse_error",
    "int_type": "type_error",
    "string_type": "type_error",
    "float_type": "type_error",
    "bool_type": "type_error",
    "list_type": "type_error",
    "dict_type": "type_error",
}

# Root-level keys that indicate the model echoed the JSON Schema definition
# instead of returning an instance conforming to it.
_META_SCHEMA_KEYS = {
    "properties", "required", "type", "title", "description",
    "definitions", "$defs", "$ref", "additionalProperties",
    "items", "allOf", "anyOf", "oneOf",
}


def classify_error(err: dict) -> str:
    """Classify a single Pydantic error dict into a category."""
    ptype = err.get("type", "unknown")

    if ptype == "value_error":
        msg = str(err.get("msg", "")).lower()
        if "!= len(" in msg or "does not match len" in msg:
            return "count_mismatch"
        if "bucket=" in msg or "implies bucket" in msg or "confidence=" in msg:
            return "categorical_numeric"
        if "not in" in msg and (
            "canonical_id" in msg or "entities" in msg or "ids" in msg
        ):
            return "cross_field_ref"
        if "pattern" in msg or "canonical_id_pattern" in msg:
            return "regex_pattern"
        return "cross_field_other"

    return _PYDANTIC_ERROR_MAP.get(ptype, f"unknown:{ptype}")


def _looks_like_schema_mirroring(raw_output: str | None) -> bool:
    """Detect: model returned the JSON Schema definition instead of an instance.

    Heuristic: parse the JSON, check whether root-level keys are dominated by
    JSON-Schema meta-keys (properties, required, type, title, etc.).
    """
    if not raw_output:
        return False
    try:
        obj = json.loads(raw_output)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(obj, dict):
        return False
    keys = set(obj.keys())
    meta_hits = keys & _META_SCHEMA_KEYS
    # Strong signal: "properties" at root AND another meta-key
    if "properties" in keys and len(meta_hits) >= 2:
        return True
    # Fallback: majority of top-level keys are meta-keys
    if len(keys) > 0 and len(meta_hits) / len(keys) >= 0.5:
        return True
    return False


def summarize_validation_error(
    ve: ValidationError, raw_output: str | None = None
) -> dict:
    """Turn a ValidationError into a structured summary for logging.

    If raw_output is provided AND all errors are missing_field AND the raw
    output looks like a JSON Schema echo, promote the primary category to
    'schema_mirroring' — a more specific and interesting classification.
    """
    errors = []
    for e in ve.errors():
        cat = classify_error(e)
        errors.append({
            "category": cat,
            "loc": ".".join(str(x) for x in e.get("loc", [])),
            "type": e.get("type", "unknown"),
            "msg": e.get("msg", ""),
        })
    categories = list(dict.fromkeys(err["category"] for err in errors))

    if (
        raw_output is not None
        and all(c == "missing_field" for c in categories)
        and _looks_like_schema_mirroring(raw_output)
    ):
        categories = ["schema_mirroring"] + [c for c in categories if c != "schema_mirroring"]
        for err in errors:
            err["category"] = "schema_mirroring"

    return {
        "categories": categories,
        "primary_category": categories[0] if categories else "unknown",
        "errors": errors,
    }


def _looks_like_markdown_wrap(raw_output: str | None) -> bool:
    """Detect: the model returned valid JSON wrapped in ``` fences.

    We check for a leading code fence AND whether the content between fences
    would parse as JSON. If both true, this is markdown_wrap, not a true
    parse error.
    """
    if not raw_output:
        return False
    if not _MARKDOWN_FENCE_RE.match(raw_output):
        return False
    # Try to strip common fence patterns and re-parse
    stripped = re.sub(
        r"^\s*```(?:json|JSON|Json)?\s*\n?", "", raw_output.strip()
    )
    stripped = re.sub(r"\n?\s*```\s*$", "", stripped)
    try:
        json.loads(stripped)
        return True  # Valid JSON was hiding inside the fence
    except (json.JSONDecodeError, ValueError):
        return False


def summarize_parse_error(exc: Exception, raw_output: str | None = None) -> dict:
    """When the LLM returned something that isn't valid JSON at the root.

    If the root cause is markdown wrapping (fenced valid JSON), classify as
    'markdown_wrap' — a distinct and more specific failure than raw parse_error.
    """
    if _looks_like_markdown_wrap(raw_output):
        primary = "markdown_wrap"
    else:
        primary = "parse_error"
    return {
        "categories": [primary],
        "primary_category": primary,
        "errors": [{
            "category": primary,
            "loc": "",
            "type": type(exc).__name__,
            "msg": str(exc),
        }],
    }