#!/usr/bin/env python3
"""Re-run the fixed classifier over all existing node_attempts rows.

Purpose: after fixing the detection-order bug in errors.py, we need to
re-classify the raw_outputs of every failed attempt in the DB. No new API
calls are made — the raw_outputs were already logged.

What this changes:
    node_attempts.primary_category  <- updated if the fixed classifier
                                       produces a different label
    node_attempts.all_categories    <- refreshed to match

What this does NOT change:
    - Raw outputs (unchanged)
    - Token counts, latency, success flags
    - Any hand_labels rows
    - Anything in `runs` or `node_runs`

Usage:
    python scripts/reclassify_all.py --dry-run   # preview changes
    python scripts/reclassify_all.py --apply     # actually update the DB

Always run --dry-run first. Snapshot the DB before --apply.
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schemaeval.errors import _heuristic_category  # STAGE 1
from schemaeval.errors import _pydantic_error_to_category  # STAGE 2

DB_PATH = os.getenv("DB_PATH", str(ROOT / "results" / "experiments.db"))


def reclassify_row(
    raw_output: str | None,
    error_details_json: str | None,
    current_category: str | None,
) -> tuple[str | None, list[str]]:
    """Compute the corrected primary_category + all_categories for a row.

    Returns (new_primary, new_all_categories). Returns (current_category, [])
    if we can't reclassify (e.g., successful attempt with no error info).
    """
    # STAGE 1: heuristic on raw_output
    heuristic_cat = _heuristic_category(raw_output) if raw_output else None

    # STAGE 2: parse the stored error_details (list of dicts as JSON)
    try:
        errors_list = json.loads(error_details_json) if error_details_json else []
    except (json.JSONDecodeError, TypeError):
        errors_list = []

    pydantic_cats: list[str] = []
    for err in errors_list:
        if not isinstance(err, dict):
            continue
        err_type = err.get("type", "")
        msg = err.get("msg", "")
        # Skip meta-entries like {"category": "api_error", ...}
        if not err_type:
            continue

        stored_cat = err.get("category", "")
        if stored_cat in ("parse_error", "api_error"):
            pydantic_cats.append(stored_cat)
            continue
        
        # Re-map by err_type + msg; the stored "category" field may be stale
        pydantic_cats.append(_pydantic_error_to_category(err_type, msg))

    # Combine: heuristic wins, else most common Pydantic mapping
    if heuristic_cat is not None:
        primary = heuristic_cat
    elif pydantic_cats:
        primary = Counter(pydantic_cats).most_common(1)[0][0]
    elif current_category == "api_error":
        # Preserve api_error labeling (harness-level failures, not classifier's domain)
        primary = "api_error"
    elif current_category:
        # No error info + not api_error: probably a success row, leave alone
        return current_category, []
    else:
        return None, []

    all_cats = list(dict.fromkeys([primary] + pydantic_cats))
    return primary, all_cats


def main():
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true",
                     help="Preview changes without modifying the DB")
    grp.add_argument("--apply", action="store_true",
                     help="Actually update the DB (snapshot first!)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT id, raw_output, error_details, primary_category, validation_ok
           FROM node_attempts
           WHERE validation_ok = 0"""  # only failed attempts have categories
    ).fetchall()

    print(f"Examining {len(rows)} failed attempts...\n")

    changes: list[tuple[int, str, str]] = []  # (id, old, new)
    transitions: Counter = Counter()

    for row in rows:
        old = row["primary_category"]
        new_primary, new_all = reclassify_row(
            row["raw_output"], row["error_details"], old
        )
        if new_primary != old:
            changes.append((row["id"], old or "None", new_primary or "None"))
            transitions[(old or "None", new_primary or "None")] += 1
            if args.apply:
                conn.execute(
                    "UPDATE node_attempts SET primary_category = ?, "
                    "all_categories = ? WHERE id = ?",
                    (new_primary, json.dumps(new_all), row["id"]),
                )

    if args.apply:
        conn.commit()

    # Report
    print(f"Total rows examined:  {len(rows)}")
    print(f"Rows to update:       {len(changes)}")
    print(f"Rows unchanged:       {len(rows) - len(changes)}\n")

    if transitions:
        print("Transitions (old -> new : count):")
        for (old, new), count in sorted(
            transitions.items(), key=lambda x: -x[1]
        ):
            print(f"  {old:20s} -> {new:20s}: {count}")

    if args.dry_run:
        print("\n(DRY RUN — no changes written. Re-run with --apply to update.)")
    else:
        print("\nDB updated. Verify with `python scripts/analyze_crux.py`.")

    conn.close()


if __name__ == "__main__":
    main()