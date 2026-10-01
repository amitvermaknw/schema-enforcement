#!/usr/bin/env python3
"""Revalidate every stored completion against its node schema under the
installed Pydantic and compare with the stored validation outcome.

Read-only: the database is opened with SQLite's mode=ro. No model calls.
Exit 0 if every checked completion reproduces its stored outcome, else 1.

Usage:
    python scripts/revalidate_all.py --db results/archive/paper1_FINAL_DATA_locked_v4_20260913.db
"""
import argparse
import importlib
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pydantic
import pydantic_core
from pydantic import ValidationError

NODE_CLS = {"identify": "IdentifyOutput", "gather": "GatherOutput", "answer": "AnswerOutput"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    a = ap.parse_args()

    con = sqlite3.connect(f"file:{Path(a.db).resolve()}?mode=ro", uri=True)
    rows = con.execute(
        """SELECT a.id, a.node_name, a.raw_output, a.validation_ok,
                  a.primary_category, r.schema_tier
           FROM node_attempts a JOIN runs r ON r.run_id = a.run_id"""
    ).fetchall()

    cache: dict = {}
    tally: Counter = Counter()
    mismatches = []
    for aid, node, raw, ok, cat, tier in rows:
        if raw is None or cat == "api_error":
            tally["skipped (no completion or api_error)"] += 1
            continue
        key = (tier, node)
        if key not in cache:
            mod = importlib.import_module(f"schemaeval.schemas.{tier}")
            cache[key] = getattr(mod, NODE_CLS[node])
        try:
            cache[key].model_validate_json(raw)
            new = 1
        except ValidationError:
            new = 0
        tally["checked"] += 1
        if new == int(ok):
            tally["agree"] += 1
        else:
            tally["disagree"] += 1
            mismatches.append((aid, tier, node, int(ok), new, cat))

    print(f"pydantic {pydantic.VERSION} | pydantic-core {pydantic_core.__version__}")
    print(f"rows: {len(rows)}")
    for k, v in tally.items():
        print(f"{k}: {v}")
    for m in mismatches[:20]:
        print("  mismatch (id, tier, node, stored_ok, now_ok, category):", m)
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()