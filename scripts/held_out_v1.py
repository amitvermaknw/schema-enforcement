"""
held_out_v1 — held-out schema tier for the generality experiment (Review 3, D2).

Design rules, all deliberate departures from the medium tier so that this is a
genuinely new constraint surface rather than a relabelling of the old one:

  1. Different identifier family. medium uses lowercase snake_case
     (^[a-z][a-z0-9_]{2,30}$). Here identifiers are dash-joined uppercase
     record codes (^[A-Z]{2,4}-[0-9]{2,4}$). A model that produced conforming
     snake_case identifiers has to satisfy a different shape.
  2. Length is NOT expressible through the pattern. Per our own §5 advice, the
     quantifiers here bound structure, and free-text length is carried by a
     separate max_length. A length overflow must therefore surface as
     length_bound, never as regex_pattern. This is the sharpest prediction the
     experiment makes.
  3. Different field names and nesting depth (records/claims/verdict rather than
     entities/facts/answer), so prompt wording cannot be reused verbatim.
  4. Constraint families kept, so every taxonomy category remains reachable:
     pattern, enum, length, list bounds, numeric range, required fields,
     and one cross-field check per node.
  5. Caps set from observed output lengths, not guessed: see CAP_NOTE.

CAP_NOTE: medium's 250-char coverage_notes cap sat below Sonnet 4.6's output
length and produced a length-dominant profile. The caps here (600/500) sit above
the medium-tier observed distribution for every model, so length_bound is
reachable but not pre-loaded. State this in the paper: the caps were chosen
before the runs and not tuned afterwards.

Assumption to check against your harness: this module mirrors the public shape of
schemas/medium.py — three top-level output models, a module-level pattern
constant, and model_validator(mode="after") for cross-field checks. Register it
in schemas/__init__.py alongside the other tiers.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Structure only: no length semantics live in this pattern.
RECORD_ID_PATTERN = r"^[A-Z]{2,4}-[0-9]{2,4}$"
_ID_RE = re.compile(RECORD_ID_PATTERN)

RECORD_KIND = Literal["person", "organisation", "place", "work", "event"]
STANCE = Literal["supports", "refutes", "insufficient"]


# --------------------------------------------------------------------- node 1
class Record(BaseModel):
    record_id: str = Field(
        pattern=RECORD_ID_PATTERN,
        description="Record code: 2-4 uppercase letters, a hyphen, 2-4 digits, e.g. AB-01.",
    )
    label: str = Field(min_length=2, max_length=120)
    kind: RECORD_KIND
    salience: int = Field(ge=0, le=100, description="Integer 0-100.")


class SurveyOutput(BaseModel):
    """Node 1: survey the question and evidence, emitting candidate records."""

    records: list[Record] = Field(min_length=1, max_length=8)
    record_count: int = Field(ge=1, le=8)
    focus_record_id: str = Field(pattern=RECORD_ID_PATTERN)

    @model_validator(mode="after")
    def _check(self):
        ids = [r.record_id for r in self.records]
        if self.focus_record_id not in ids:
            raise ValueError(f"focus_record_id '{self.focus_record_id}' not in records record_ids")
        if self.record_count != len(self.records):
            raise ValueError(f"record_count={self.record_count} != len(records)={len(self.records)}")
        if len(set(ids)) != len(ids):
            raise ValueError("record_ids are not unique")
        return self


# --------------------------------------------------------------------- node 2
class Claim(BaseModel):
    record_id: str = Field(pattern=RECORD_ID_PATTERN)
    claim: str = Field(min_length=10, max_length=600)
    stance: STANCE
    evidence_span: str = Field(min_length=3, max_length=200)


class AssembleOutput(BaseModel):
    """Node 2: assemble claims keyed to the surveyed records."""

    claims: list[Claim] = Field(min_length=1, max_length=10)
    claim_count: int = Field(ge=1, le=10)
    method_note: str = Field(min_length=20, max_length=500)

    @model_validator(mode="after")
    def _check(self):
        if self.claim_count != len(self.claims):
            raise ValueError(f"claim_count={self.claim_count} != len(claims)={len(self.claims)}")
        return self


# --------------------------------------------------------------------- node 3
class VerdictOutput(BaseModel):
    """Node 3: return the verdict with its supporting record codes."""

    verdict: str = Field(min_length=1, max_length=500)
    certainty: int = Field(ge=0, le=100)
    certainty_band: Literal["low", "medium", "high"]
    supporting_record_ids: list[str] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def _check(self):
        for rid in self.supporting_record_ids:
            if not _ID_RE.match(rid):
                raise ValueError(f"'{rid}' fails record_id pattern '{RECORD_ID_PATTERN}'")
        want = "low" if self.certainty < 34 else "medium" if self.certainty < 67 else "high"
        if self.certainty_band != want:
            raise ValueError(f"certainty={self.certainty} implies certainty_band='{want}'")
        return self