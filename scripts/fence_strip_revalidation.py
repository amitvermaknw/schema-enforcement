#!/usr/bin/env python3
"""Fence-strip revalidation for markdown_wrap failures.

Question we're answering: of the N attempts currently labeled markdown_wrap,
how many are "pure formatting" failures (JSON is valid once fences are
stripped) vs "compound" failures (fence + additional schema violations)?

Method:
    For each markdown_wrap attempt in node_attempts:
      1. Strip leading/trailing ```json ... ``` fences from raw_output
      2. Load the schema tier and node schema that was in effect
      3. Attempt Pydantic validation on the stripped content
      4. Classify the outcome:
          - pure_formatting   -> validates cleanly after strip
          - compound_<cat>    -> validation still fails; categorize the new failure
          - unstrippable      -> stripping didn't yield parseable JSON

Output:
    - Terminal summary: counts per outcome category, aggregate percentages
    - New table `markdown_wrap_revalidation` in the DB with per-attempt results
    - Suitable for a paragraph in Section 5 of the paper

Non-destructive: never modifies primary_category or all_categories.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schemaeval.schemas import get_schemas
from schemaeval.errors import _heuristic_category, _pydantic_error_to_category
from pydantic import ValidationError

DB_PATH = os.getenv("DB_PATH", str(ROOT / "results" / "experiments.db"))

# Which Pydantic class corresponds to each node in the 3-node topology.
# Position 0 = identify, 1 = gather, 2 = answer for a schema tuple.
NODE_INDEX = {"identify": 0, "gather": 1, "answer": 2}


def strip_fences(raw: str) -> str:
    """Remove leading/trailing markdown code fences from a raw completion."""
    s = raw.strip()
    # Leading fence: ```json, ```JSON, ``` (bare), etc., possibly followed by newline
    s = re.sub(r"^```[a-zA-Z]*\s*\n?", "", s, count=1)
    # Trailing fence: ``` possibly preceded by newline, possibly followed by whitespace
    s = re.sub(r"\n?```\s*$", "", s, count=1)
    return s.strip()


def init_revalidation_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS markdown_wrap_revalidation (
            attempt_id INTEGER PRIMARY KEY,
            model TEXT,
            schema_tier TEXT,
            node_name TEXT,
            outcome TEXT,
            compound_category TEXT,
            compound_errors TEXT,
            FOREIGN KEY (attempt_id) REFERENCES node_attempts(id)
        )"""
    )
    conn.commit()


def revalidate_one(
    raw: str, schema_tier: str, node_name: str
) -> tuple[str, str | None, list | None]:
    """Return (outcome, compound_category_or_None, error_details_or_None)."""
    stripped = strip_fences(raw)
    if not stripped:
        return "unstrippable", None, None

    # Try to parse JSON
    try:
        json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return "unstrippable", None, None

    # Look up the schema for this node
    try:
        schemas = get_schemas(schema_tier)
    except (KeyError, ValueError):
        return "schema_lookup_failed", None, None

    node_idx = NODE_INDEX.get(node_name)
    if node_idx is None or node_idx >= len(schemas):
        return "unknown_node", None, None
    schema_class = schemas[node_idx]

    # Attempt full validation
    try:
        schema_class.model_validate_json(stripped)
        return "pure_formatting", None, None
    except ValidationError as ve:
        # Compound failure — categorize what else went wrong
        errors_list = []
        cats_seen = []
        for err in ve.errors():
            err_type = err.get("type", "unknown")
            msg = err.get("msg", "")
            cat = _pydantic_error_to_category(err_type, msg)
            cats_seen.append(cat)
            errors_list.append({
                "category": cat,
                "loc": ".".join(str(x) for x in err.get("loc", [])),
                "type": err_type,
                "msg": msg,
            })
        # Also check the stripped content against Stage 1 heuristics
        heuristic_cat = _heuristic_category(stripped)
        if heuristic_cat and heuristic_cat != "markdown_wrap":
            primary = heuristic_cat
        elif cats_seen:
            primary = Counter(cats_seen).most_common(1)[0][0]
        else:
            primary = "other_validation_error"
        return f"compound_{primary}", primary, errors_list


def main():
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true",
                     help="Show summary without writing to DB")
    grp.add_argument("--apply", action="store_true",
                     help="Also write per-attempt results to markdown_wrap_revalidation table")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if args.apply:
        init_revalidation_table(conn)
        conn.execute("DELETE FROM markdown_wrap_revalidation")
        conn.commit()

    rows = conn.execute(
        """SELECT a.id, a.node_name, a.raw_output, r.model, r.schema_tier
           FROM node_attempts a JOIN runs r ON a.run_id = r.run_id
           WHERE a.primary_category = 'markdown_wrap'
             AND a.raw_output IS NOT NULL
             AND length(a.raw_output) > 0"""
    ).fetchall()

    print(f"Revalidating {len(rows)} markdown_wrap attempts...\n")

    outcomes = Counter()
    compound_breakdown = Counter()

    for row in rows:
        outcome, comp_cat, comp_errs = revalidate_one(
            row["raw_output"], row["schema_tier"], row["node_name"]
        )
        outcomes[outcome] += 1
        if comp_cat:
            compound_breakdown[comp_cat] += 1
        if args.apply:
            conn.execute(
                """INSERT INTO markdown_wrap_revalidation
                   (attempt_id, model, schema_tier, node_name,
                    outcome, compound_category, compound_errors)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["model"], row["schema_tier"],
                 row["node_name"], outcome, comp_cat,
                 json.dumps(comp_errs) if comp_errs else None),
            )

    if args.apply:
        conn.commit()

    total = len(rows)
    print("=" * 70)
    print(f"Outcome distribution ({total} markdown_wrap attempts):")
    print("=" * 70)
    for outcome, count in outcomes.most_common():
        pct = 100 * count / total
        print(f"  {outcome:35s} {count:>6}  ({pct:>5.1f}%)")

    if compound_breakdown:
        print()
        print("Compound failure categories (underlying violations):")
        print("-" * 70)
        for cat, count in compound_breakdown.most_common():
            pct = 100 * count / total
            print(f"  {cat:35s} {count:>6}  ({pct:>5.1f}%)")

    print()
    pure = outcomes.get("pure_formatting", 0)
    compound = sum(v for k, v in outcomes.items() if k.startswith("compound_"))
    unstrip = outcomes.get("unstrippable", 0)
    print(f"Summary: {pure}/{total} ({100*pure/total:.1f}%) pure formatting  |  "
          f"{compound}/{total} ({100*compound/total:.1f}%) compound  |  "
          f"{unstrip}/{total} ({100*unstrip/total:.1f}%) unstrippable")

    if args.apply:
        print("\nPer-attempt results written to markdown_wrap_revalidation table.")
    else:
        print("\n(DRY RUN — no DB writes. Re-run with --apply to persist per-attempt results.)")

    conn.close()


if __name__ == "__main__":
    main()