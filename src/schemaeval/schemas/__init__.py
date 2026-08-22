"""Pydantic schemas organized by complexity tier.

Two access patterns are supported:

1. Direct import (legacy — used by run_pilot.py):
       from schemaeval.schemas import IdentifyOutput, GatherOutput, AnswerOutput
   These always resolve to the `medium` tier for backward compatibility.

2. Registry lookup (preferred — used by run_crux.py and future scripts):
       from schemaeval.schemas import get_schemas
       IdentifyOutput, GatherOutput, AnswerOutput = get_schemas("medium_v2")

Adding a new tier:
    1. Create schemas/<name>.py with IdentifyOutput, GatherOutput, AnswerOutput
    2. Register it in SCHEMA_REGISTRY below
"""

from schemaeval.schemas import medium, medium_v2

# Legacy direct imports — resolve to medium tier
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
}


def get_schemas(tier: str) -> tuple:
    """Return (IdentifyOutput, GatherOutput, AnswerOutput) classes for a tier."""
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