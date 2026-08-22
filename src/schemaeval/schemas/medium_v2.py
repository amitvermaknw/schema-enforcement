"""Medium-v2 tier: same constraints as medium, with length caps relaxed
for verbose models (specifically Claude Sonnet).

DIFF FROM medium.py:
    coverage_notes: max_length 250 -> 1000
    answer:        max_length 400 -> 1200
    fact:          max_length 400 -> 800

Rationale: crux experiment (Aug 2026) showed Sonnet's length_bound failures
were dominated by coverage_notes (~64% of failures) with raw outputs
1017-1977 chars against a 250-char cap. This ablation isolates whether
Sonnet's dominant failure mode is truly verbosity-driven (surviving the
relaxation) or whether it disappears when constraints are model-appropriate.

All other constraints — regex on canonical_id, cross-field validators,
count consistency, categorical-numeric coherence — are IDENTICAL to medium.
This is the minimum-diff ablation.
"""

import re
from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

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
    fact: str = Field(min_length=10, max_length=800)      # was 400
    relevance: float = Field(ge=0.0, le=1.0)


class GatherOutput(BaseModel):
    facts: List[Fact] = Field(min_length=2, max_length=8)
    fact_count: int = Field(
        ge=2, le=8, description="Must equal len(facts)"
    )
    coverage_notes: str = Field(min_length=20, max_length=1000)  # was 250

    @model_validator(mode="after")
    def _consistency(self):
        if self.fact_count != len(self.facts):
            raise ValueError(
                f"fact_count={self.fact_count} != len(facts)={len(self.facts)}"
            )
        return self


class AnswerOutput(BaseModel):
    answer: str = Field(min_length=20, max_length=1200)   # was 400
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