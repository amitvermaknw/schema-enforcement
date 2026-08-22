#!/usr/bin/env python3
"""Reclassify existing parse_error rows in node_attempts.

If raw_output is stored, run the current markdown_wrap detector on each row
tagged 'parse_error' and update the category in-place. No API calls needed.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schemaeval.errors import _looks_like_markdown_wrap  # noqa: E402

DB_PATH = os.getenv("DB_PATH", "results/experiments.db")


def main():
    if not Path(DB_PATH).exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, raw_output, all_categories, error_details "
        "FROM node_attempts WHERE primary_category = 'parse_error'"
    ).fetchall()

    print(f"Found {len(rows)} rows with primary_category='parse_error'")

    updated = 0
    for row_id, raw, all_cats_json, err_json in rows:
        if not _looks_like_markdown_wrap(raw):
            continue

        # Update the row's categorization
        new_cats = json.dumps(["markdown_wrap"])
        errs = json.loads(err_json) if err_json else []
        for e in errs:
            if e.get("category") == "parse_error":
                e["category"] = "markdown_wrap"
        new_err_json = json.dumps(errs)

        conn.execute(
            """UPDATE node_attempts
               SET primary_category = 'markdown_wrap',
                   all_categories = ?,
                   error_details = ?
               WHERE id = ?""",
            (new_cats, new_err_json, row_id),
        )
        updated += 1

    conn.commit()
    print(f"Reclassified {updated}/{len(rows)} rows from parse_error -> markdown_wrap")
    print("Rerun `python scripts/analyze_crux.py` to see the updated taxonomy.")


if __name__ == "__main__":
    main()