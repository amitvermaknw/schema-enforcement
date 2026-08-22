"""Medium-complexity Pydantic schemas — strengthened for measurable failure rate.

Design goal: 10-20% per-node failure rate on modern models at temperature=0.

The constraints below are drawn from real production patterns so failures
reflect realistic schema strictness, not contrived difficulty:

  1. Regex on canonical_id — models often use spaces, capitals, hyphens,
     or start with a digit.
  2. Cross-field: primary_entity_id must appear in entities[].canonical_id.
     Models sometimes invent an ID or use the name instead.
  3. Count consistency: entity_count == len(entities), fact_count == len(facts).
     Models frequently miscount or forget to update the count.
  4. Categorical coherence: confidence_bucket must match numeric confidence.
     Models often report confidence=0.85 with bucket="medium".

Note: constrained decoding (Outlines, XGrammar, JSON mode) enforces only
grammar. It cannot enforce constraints 2, 3, or 4 — that's exactly the gap
this paper measures.
"""

import re
from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

# Lowercase snake_case, 3-31 chars, must start with a letter
CANONICAL_ID_PATTERN = r"^[a-z][a-z0-9_]{2,30}$"
_ID_RE = re.compile(CANONICAL_ID_PATTERN)


class Entity(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    entity_type: Literal["person", "place", "organization", "concept", "other"]
    canonical_id: str = Field(
        pattern=CANONICAL_ID_PATTERN,
        description="lowercase_snake_case identifier, e.g. 'manchester_united'",
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
        # Numeric-categorical coherence — models frequently break this
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
        # Supporting IDs must be canonical (snake_case)
        for eid in self.supporting_entity_ids:
            if not _ID_RE.match(eid):
                raise ValueError(
                    f"supporting_entity_id '{eid}' fails canonical_id pattern "
                    f"'{CANONICAL_ID_PATTERN}'"
                )
        return self
