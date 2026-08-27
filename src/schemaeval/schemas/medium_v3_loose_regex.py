"""Medium-v3-loose-regex schema tier: perturbation ablation for Experiment G.

DIFF FROM medium.py:
    CANONICAL_ID_PATTERN:
        Original: r"^[a-z][a-z0-9_]{2,30}$"
        Loosened: r"^[a-zA-Z0-9][a-zA-Z0-9_\\-]{2,30}$"

    The loosened pattern allows:
    - Uppercase letters (e.g. 'AmazonInc')
    - Leading digits (e.g. '888_seventh_ave')
    - Hyphens (e.g. 'first-for-women')

    All other constraints — length caps, enums, cross-field validators,
    count consistency, categorical/numeric coherence — are IDENTICAL to medium.

Purpose: distinguish schema-driven failures from model-driven failures.
    - If model's dominant failure category disappears with loosened regex,
      failures were a schema artifact.
    - If failure rate stays similar but shifts to another category, model
      behavior — not our specific constraint choice — drives the failures.

Rationale: on the medium tier, gpt-5.6-sol shows regex_pattern as 88.9% of
its failures. This ablation isolates whether that dominance is intrinsic
(model choice) or extrinsic (schema calibration).
"""

import re
from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

# LOOSENED regex — allows caps, leading digits, hyphens
CANONICAL_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{2,30}$"
_ID_RE = re.compile(CANONICAL_ID_PATTERN)


class Entity(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    entity_type: Literal["person", "place", "organization", "concept", "other"]
    canonical_id: str = Field(
        pattern=CANONICAL_ID_PATTERN,
        description="alphanumeric identifier, may include hyphens/underscores",
    )


class IdentifyOutput(BaseModel):
    """Node 1: entities in the question, with a designated primary."""

    entities: List[Entity] = Field(min_length=2, max_length=5)
    question_type: Literal[
        "who", "what", "when", "where", "why", "how", "comparison"
    ]
    primary_entity_id: str = Field(
        description="Must match one of entities[].canonical_id exactly"
    )
    entity_count: int = Field(
        ge=2, le=5, description="Must equal len(entities)"
    )

    @model_validator(mode="after")
    def _consistency(self):
        ids = {e.canonical_id for e in self.entities}
        if self.primary_entity_id not in ids:
            raise ValueError(
                f"primary_entity_id '{self.primary_entity_id}' not in "
                f"entities canonical_ids {sorted(ids)}"
            )
        if self.entity_count != len(self.entities):
            raise ValueError(
                f"entity_count={self.entity_count} != "
                f"len(entities)={len(self.entities)}"
            )
        return self


class Fact(BaseModel):
    entity_id: str = Field(
        pattern=CANONICAL_ID_PATTERN,
        description="Reference to a canonical_id from the identify step",
    )
    fact: str = Field(min_length=10, max_length=400)
    relevance: float = Field(ge=0.0, le=1.0)


class GatherOutput(BaseModel):
    """Node 2: facts about entities, with consistency count."""

    facts: List[Fact] = Field(min_length=2, max_length=8)
    fact_count: int = Field(
        ge=2, le=8, description="Must equal len(facts)"
    )
    coverage_notes: str = Field(min_length=20, max_length=250)

    @model_validator(mode="after")
    def _consistency(self):
        if self.fact_count != len(self.facts):
            raise ValueError(
                f"fact_count={self.fact_count} != len(facts)={len(self.facts)}"
            )
        return self


class AnswerOutput(BaseModel):
    """Node 3: final answer with confidence and its categorical bucket."""

    answer: str = Field(min_length=20, max_length=400)
    supporting_entity_ids: List[str] = Field(min_length=1, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_bucket: Literal["low", "medium", "high"] = Field(
        description=(
            "Must match confidence numerically: "
            "confidence < 0.5 => 'low'; "
            "0.5 <= confidence <= 0.8 => 'medium'; "
            "confidence > 0.8 => 'high'"
        )
    )

    @model_validator(mode="after")
    def _consistency(self):
        expected = (
            "low" if self.confidence < 0.5
            else "high" if self.confidence > 0.8
            else "medium"
        )
        if self.confidence_bucket != expected:
            raise ValueError(
                f"confidence={self.confidence} implies bucket='{expected}', "
                f"got '{self.confidence_bucket}'"
            )
        for eid in self.supporting_entity_ids:
            if not _ID_RE.match(eid):
                raise ValueError(
                    f"supporting_entity_id '{eid}' fails canonical_id pattern "
                    f"'{CANONICAL_ID_PATTERN}'"
                )
        return self