"""Failure category detection.

Classification pipeline for the schema-enforcement paper. Two-stage design:

STAGE 1 — Heuristic detection on raw output (novel categories).
    Checked FIRST because a schema-mirrored or prose-wrapped output can also
    trigger Pydantic missing_field / parse_error, and we want the more specific
    category to win.

    Detected:
      - schema_mirroring : root contains >=2 JSON Schema meta-keys
      - markdown_wrap    : output starts with ``` code fence
      - prose_preamble   : output starts with prose but contains embedded JSON

STAGE 2 — Pydantic ValidationError type mapping (standard categories).
    Runs only if Stage 1 didn't fire. Maps Pydantic error types to categories:
      - string_pattern_mismatch -> regex_pattern
      - string_too_long / list_too_long -> length_bound
      - literal_error -> enum_violation
      - missing -> missing_field
      - value_error (from model_validator) -> cross_field_ref
      - float_type / int_type / ...ge / ...le -> range_bound

    For parse errors (json.JSONDecodeError), Stage 2 defaults to parse_error
    ONLY if the raw output doesn't match any Stage 1 heuristic.

Design principle: heuristics for novel behavioral categories are more
specific than Pydantic's generic error types, so they should be checked first.
This was a bug in an earlier version of this module (novel-category recall was
~0.87 on schema_mirroring and ~0.00 on prose_preamble because Pydantic errors
fired first). Fixed by running heuristics on raw_output before any Pydantic
error mapping.
"""

import json
import re
from typing import Optional

from pydantic import ValidationError


# ============================================================
# Stage 1 — heuristic detection on raw output
# ============================================================

# JSON Schema meta-keywords. If >=2 of these appear as root keys in a valid
# JSON dict output, it's schema_mirroring (model returned schema definition
# shape instead of an instance).
_SCHEMA_META_KEYS = {
    "description", "properties", "required", "title", "type",
    "additionalProperties", "$defs", "$schema", "$ref",
    "definitions", "items", "anyOf", "allOf", "oneOf",
}
_SCHEMA_META_KEY_THRESHOLD = 2

# Match code fences at the very start: ```json, ```JSON, ``` (bare), etc.
_MARKDOWN_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)

# Non-greedy extraction of the first {...} block that spans the whole string.
# Used to detect JSON embedded in prose.
_EMBEDDED_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _looks_like_schema_mirroring(raw_output: str) -> bool:
    """True if the raw output is a JSON dict whose root keys are >=2 JSON
    Schema meta-keywords (description, properties, required, title, type,
    ...). This is the gpt-4o family failure mode where the model returns
    the schema definition shape instead of an instance."""
    if not raw_output:
        return False
    try:
        parsed = json.loads(raw_output)
    except (json.JSONDecodeError, ValueError):
        # Also try stripping code fences before giving up — a markdown-wrapped
        # schema-mirroring output is rare but possible.
        stripped = _strip_code_fences(raw_output)
        if stripped == raw_output:
            return False
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return False
    if not isinstance(parsed, dict):
        return False
    root_keys = set(parsed.keys())
    return len(root_keys & _SCHEMA_META_KEYS) >= _SCHEMA_META_KEY_THRESHOLD


def _looks_like_markdown_wrap(raw_output: str) -> bool:
    """True if the raw output starts with a code fence (```json, ```, etc.)."""
    if not raw_output:
        return False
    # A bare ``` at position 0 (with optional leading whitespace) is the tell.
    stripped_start = raw_output.lstrip()
    return stripped_start.startswith("```")


def _looks_like_prose_preamble(raw_output: str) -> bool:
    """True if the raw output starts with prose but contains an embedded JSON
    object (or JSON-tail).

    Rejects:
      - Empty / None
      - Starts with { or [ (already JSON, not preamble)
      - Starts with ``` (that's markdown_wrap)
      - Contains no JSON-looking substring at all
    """
    if not raw_output:
        return False
    stripped_start = raw_output.lstrip()
    if not stripped_start:
        return False
    first_char = stripped_start[0]
    # Already-JSON outputs aren't prose_preamble.
    if first_char in ("{", "["):
        return False
    # Markdown-wrapped outputs are their own category.
    if stripped_start.startswith("```"):
        return False
    # Look for an embedded JSON object anywhere in the output. Even if it
    # doesn't parse cleanly (partial/truncated), the presence of {"key": ...}
    # after prose is the distinctive prose_preamble pattern.
    match = _EMBEDDED_JSON_RE.search(raw_output)
    if not match:
        return False
    # If a substantial portion of the output is prose (not just a stray brace
    # inside a string), it counts.
    prose_prefix_len = match.start()
    # Require at least 20 chars of prose before the JSON candidate — filters
    # out edge cases where output starts with a stray character before {.
    return prose_prefix_len >= 20


def _strip_code_fences(raw_output: str) -> str:
    """Remove leading/trailing ```json ... ``` fences if present."""
    stripped = raw_output.strip()
    if stripped.startswith("```"):
        # Remove opening fence line (```json, ```, etc.)
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped, count=1)
        # Remove trailing fence
        stripped = re.sub(r"\n?```\s*$", "", stripped, count=1)
    return stripped


def _heuristic_category(raw_output: Optional[str]) -> Optional[str]:
    """Run Stage 1 heuristics on raw_output. Returns category or None.

    Order matters: markdown_wrap wins over prose_preamble (a wrapped output
    could contain preamble-like text before ```); schema_mirroring is
    independent and checked after fence checks.
    """
    if not raw_output:
        return None
    if _looks_like_markdown_wrap(raw_output):
        return "markdown_wrap"
    if _looks_like_prose_preamble(raw_output):
        return "prose_preamble"
    if _looks_like_schema_mirroring(raw_output):
        return "schema_mirroring"
    return None


# ============================================================
# Stage 2 — Pydantic ValidationError type mapping
# ============================================================

# Maps Pydantic v2 error type strings to our failure categories.
_PYDANTIC_ERROR_MAP = {
    # regex mismatches
    "string_pattern_mismatch": "regex_pattern",
    # length violations
    "string_too_long": "length_bound",
    "string_too_short": "length_bound",
    "list_too_long": "length_bound",
    "list_too_short": "length_bound",
    "too_long": "length_bound",
    "too_short": "length_bound",
    # numeric range
    "greater_than": "range_bound",
    "greater_than_equal": "range_bound",
    "less_than": "range_bound",
    "less_than_equal": "range_bound",
    # enum / literal
    "literal_error": "enum_violation",
    "enum": "enum_violation",
    # missing fields
    "missing": "missing_field",
    # cross-field / model_validator ValueError — handled in
    # _pydantic_error_to_category with message inspection (pattern-related
    # messages route to regex_pattern instead)
    # type errors (fallback to range/length depending on details)
    "int_type": "range_bound",
    "float_type": "range_bound",
    "string_type": "missing_field",
    "list_type": "missing_field",
    "dict_type": "missing_field",
    "bool_type": "missing_field",
}


def _pydantic_error_to_category(err_type: str, msg: str = "") -> str:
    """Map a Pydantic v2 error type (and message) to our failure category.

    Special case: `value_error` and `assertion_error` come from
    @model_validator raises. These are typically cross-field checks, but
    some model_validators also enforce per-item regex constraints on list
    elements (e.g., supporting_entity_ids each matching canonical_id
    pattern). We inspect the message to distinguish:

        Value error, supporting_entity_id 'foo:bar' fails canonical_id pattern
          -> regex_pattern (item-level pattern violation, not cross-field)

        Value error, primary_entity_id 'foo' not in entities canonical_ids
          -> cross_field_ref (genuine cross-field mismatch)

        Value error, entity_count=3 != len(entities)=2
          -> cross_field_ref (count consistency violation)
    """
    if err_type in ("value_error", "assertion_error"):
        # Route pattern-related messages to regex_pattern
        msg_lower = msg.lower() if msg else ""
        if "pattern" in msg_lower or "regex" in msg_lower:
            return "regex_pattern"
        return "cross_field_ref"
    return _PYDANTIC_ERROR_MAP.get(err_type, "other_validation_error")


# ============================================================
# Public API — the two summarize_* functions used by strict_repair
# ============================================================

def summarize_validation_error(
    ve: ValidationError, raw_output: Optional[str] = None
) -> dict:
    """Summarize a Pydantic ValidationError with a primary category.

    Heuristics on raw_output win when they fire — this is the fix for the
    detection-order bug where schema_mirroring outputs were being labeled as
    missing_field because the Pydantic error type was checked first.
    """
    # STAGE 1: heuristic first
    heuristic_cat = _heuristic_category(raw_output)

    # Extract per-error details from Pydantic
    errors_list = []
    categories_seen = []
    for err in ve.errors():
        err_type = err.get("type", "unknown")
        loc = ".".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "")
        cat = _pydantic_error_to_category(err_type, msg)
        categories_seen.append(cat)
        errors_list.append({
            "category": cat,
            "loc": loc,
            "type": err_type,
            "msg": msg,
        })

    # STAGE 2: if no heuristic fired, use the most common Pydantic-mapped
    # category as primary (or first, if all unique).
    if heuristic_cat is not None:
        primary = heuristic_cat
    elif categories_seen:
        # Pick the most common category; tie-break by first-seen
        from collections import Counter
        primary = Counter(categories_seen).most_common(1)[0][0]
    else:
        primary = "other_validation_error"

    return {
        "primary_category": primary,
        "categories": list(dict.fromkeys(categories_seen)),  # dedupe, keep order
        "errors": errors_list,
    }


def summarize_parse_error(
    pe: Exception, raw_output: Optional[str] = None
) -> dict:
    """Summarize a JSON parse error.

    Heuristics on raw_output still win — a markdown-wrapped output triggers
    JSONDecodeError but is categorically markdown_wrap, not parse_error.
    Similarly for prose_preamble.
    """
    # STAGE 1: heuristic first
    heuristic_cat = _heuristic_category(raw_output)

    err_entry = {
        "category": "parse_error",
        "loc": "",
        "type": type(pe).__name__,
        "msg": str(pe),
    }

    primary = heuristic_cat if heuristic_cat is not None else "parse_error"
    return {
        "primary_category": primary,
        "categories": [primary],
        "errors": [err_entry],
    }