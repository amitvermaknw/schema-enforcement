"""Pydantic schemas organized by complexity tier and topology.

Access patterns:
    from schemaeval.schemas import IdentifyOutput, GatherOutput, AnswerOutput
    # -> resolves to `medium` tier (backward compat)

    from schemaeval.schemas import get_schemas
    IdentifyOutput, GatherOutput, AnswerOutput = get_schemas("medium")
    IdentifyOutput, GatherOutput, AnswerOutput = get_schemas("medium_v2")

    # For the 6-node topology:
    from schemaeval.schemas.medium_6node import (
        DecomposeOutput, VerifyOutput, RefineOutput
    )
"""

from . import medium
from . import medium_v2
from . import medium_v3_loose_regex

from schemaeval.schemas.medium import (
    IdentifyOutput,
    GatherOutput,
    AnswerOutput,
)


SCHEMA_REGISTRY: dict[str, tuple] = {
    "medium": (
        medium.IdentifyOutput,
        medium.GatherOutput,
        medium.AnswerOutput,
    ),
    "medium_v2": (
        medium_v2.IdentifyOutput,
        medium_v2.GatherOutput,
        medium_v2.AnswerOutput,
    ),
    "medium_v3_loose_regex": (
        medium_v3_loose_regex.IdentifyOutput,
        medium_v3_loose_regex.GatherOutput,
        medium_v3_loose_regex.AnswerOutput,
    ),
}


def get_schemas(tier: str) -> tuple:
    """Return (IdentifyOutput, GatherOutput, AnswerOutput) for a tier."""
    if tier not in SCHEMA_REGISTRY:
        raise ValueError(
            f"Unknown schema tier '{tier}'. "
            f"Available: {sorted(SCHEMA_REGISTRY.keys())}"
        )
    return SCHEMA_REGISTRY[tier]


def available_tiers() -> list[str]:
    return sorted(SCHEMA_REGISTRY.keys())


__all__ = [
    "IdentifyOutput", "GatherOutput", "AnswerOutput",
    "SCHEMA_REGISTRY", "get_schemas", "available_tiers",
]