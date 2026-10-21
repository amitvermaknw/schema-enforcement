#!/usr/bin/env python3
"""Held-out, blind relabel of classifier categories (single annotator).

Reads the locked database READ-ONLY. Writes only under results/heldout/.

  available   counts per classifier category in the sampling frame (no draw)
  sample      draw the held-out set (refuses to run twice)
  label       blind interactive labelling; resumes where you stopped
  score       agreement with the stored classifier labels (run only when done)

Sampling frame: failed attempts on the reported basis (baseline prompt, cells
with >= MIN_RUNS runs), with non-empty raw output, EXCLUDING every attempt
already in hand_labels (the 144-item development set).

Blindness: the labelling screen shows exactly what label_samples.py showed
(model, dataset, tier, node, raw output truncated the same way) EXCEPT the
classifier's label; there is no default answer, and items are shuffled across
categories so their order reveals nothing. sample.csv holds attempt ids only.

Usage, from the repo root:
  .venv/bin/python scripts/heldout_relabel.py available
  .venv/bin/python scripts/heldout_relabel.py sample --quota markdown_wrap=25 length_bound=20 ...
  .venv/bin/python scripts/heldout_relabel.py label
  .venv/bin/python scripts/heldout_relabel.py score
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "results/archive/paper1_FINAL_DATA_locked_v4_20260913.db"
OUT = ROOT / "results/heldout"
SAMPLE = OUT / "sample.csv"
LABELS = OUT / "labels.csv"
SCORE = OUT / "score.json"
SEED = 20261021
MIN_RUNS = 30

sys.path.insert(0, str(ROOT / "scripts"))
from label_samples import GROUND_TRUTH_CHOICES, _pretty_print_raw  # noqa: E402  same choices and truncation


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


FRAME_SQL = f"""
WITH cells AS (
  SELECT model, schema_tier, dataset FROM runs
  WHERE prompt_variant = 'baseline'
  GROUP BY 1, 2, 3 HAVING COUNT(*) >= {MIN_RUNS}
)
SELECT a.id, a.primary_category cat
FROM node_attempts a
JOIN runs r USING (run_id)
JOIN cells c ON c.model = r.model AND c.schema_tier = r.schema_tier AND c.dataset = r.dataset
WHERE r.prompt_variant = 'baseline'
  AND a.validation_ok = 0
  AND a.raw_output IS NOT NULL AND length(a.raw_output) > 0
  AND a.id NOT IN (SELECT attempt_id FROM hand_labels)
"""


def frame(con) -> dict[str, list[int]]:
    by_cat: dict[str, list[int]] = {}
    for row in con.execute(FRAME_SQL):
        by_cat.setdefault(row["cat"], []).append(row["id"])
    return {k: sorted(v) for k, v in sorted(by_cat.items())}


def cmd_available(_args) -> None:
    con = connect()
    f = frame(con)
    dev = con.execute("SELECT COUNT(*) FROM hand_labels").fetchone()[0]
    print(f"Sampling frame (reported basis, failed, excluding the {dev} development items):")
    for cat, ids in f.items():
        print(f"  {cat:20s} {len(ids):5d}")
    print(f"  {'total':20s} {sum(map(len, f.values())):5d}")


def cmd_sample(args) -> None:
    if SAMPLE.exists():
        sys.exit(f"{SAMPLE} already exists; the held-out draw is made once. Not overwriting.")
    quota = {}
    for q in args.quota:
        cat, n = q.split("=")
        quota[cat] = int(n)
    con = connect()
    f = frame(con)
    unknown = set(quota) - set(f)
    if unknown:
        sys.exit(f"unknown or empty categories in quota: {sorted(unknown)}")
    rng = random.Random(SEED)
    drawn = []
    for cat in sorted(quota):
        n = min(quota[cat], len(f[cat]))
        drawn += rng.sample(f[cat], n)
        print(f"  {cat:20s} drew {n:3d} of {len(f[cat])}")
    rng.shuffle(drawn)
    OUT.mkdir(parents=True, exist_ok=True)
    with SAMPLE.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["order", "attempt_id"])
        w.writerows(enumerate(drawn, 1))
    print(f"wrote {len(drawn)} attempt ids (shuffled, no labels) -> {SAMPLE.relative_to(ROOT)}")


def read_sample() -> list[int]:
    if not SAMPLE.exists():
        sys.exit("no sample yet: run `sample` first")
    with SAMPLE.open() as fh:
        return [int(r["attempt_id"]) for r in csv.DictReader(fh)]


def read_labels() -> dict[int, dict]:
    if not LABELS.exists():
        return {}
    with LABELS.open() as fh:
        return {int(r["attempt_id"]): r for r in csv.DictReader(fh)}


def cmd_label(_args) -> None:
    ids, done = read_sample(), read_labels()
    todo = [i for i in ids if i not in done]
    if not todo:
        print(f"all {len(ids)} items labelled; run `score`")
        return
    con = connect()
    new = not LABELS.exists()
    with LABELS.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["attempt_id", "human_label", "notes", "labeled_at"])
        for aid in todo:
            x = con.execute(
                """SELECT a.raw_output raw, a.node_name node, r.model, r.dataset, r.schema_tier tier
                   FROM node_attempts a JOIN runs r USING (run_id) WHERE a.id = ?""", (aid,)).fetchone()
            pos = ids.index(aid) + 1
            print("=" * 70)
            print(f"Item {pos}/{len(ids)}   attempt_id={aid}")
            print(f"Model: {x['model']}   Dataset: {x['dataset']}   Tier: {x['tier']}   Node: {x['node']}")
            print("-" * 70)
            _pretty_print_raw(x["raw"] or "")
            print("=" * 70)
            for idx, choice in enumerate(GROUND_TRUTH_CHOICES, 1):
                print(f"  [{idx:2d}] {choice}")
            while True:
                resp = input(f"Your label (1-{len(GROUND_TRUTH_CHOICES)}, q to stop): ").strip().lower()
                if resp == "q":
                    print(f"stopped; {len(done)} of {len(ids)} labelled so far")
                    return
                if resp.isdigit() and 1 <= int(resp) <= len(GROUND_TRUTH_CHOICES):
                    label = GROUND_TRUTH_CHOICES[int(resp) - 1]
                    break
                print("enter a number from the list (no default)")
            notes = input("Notes (optional): ").strip()
            w.writerow([aid, label, notes, datetime.now(timezone.utc).isoformat()])
            fh.flush()
            done[aid] = {"human_label": label}
    print(f"all {len(ids)} items labelled; run `score`")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def cmd_score(_args) -> None:
    ids, labels = read_sample(), read_labels()
    missing = [i for i in ids if i not in labels]
    if missing:
        sys.exit(f"{len(missing)} of {len(ids)} items still unlabelled; finish `label` first")
    con = connect()
    cls = {r["id"]: r["primary_category"] for r in con.execute(
        f"SELECT id, primary_category FROM node_attempts WHERE id IN ({','.join('?' * len(ids))})", ids)}
    pop = {c: len(v) for c, v in frame(con).items()}
    per, agree = Counter(), Counter()
    disagreements = []
    for aid in ids:
        c, h = cls[aid], labels[aid]["human_label"]
        per[c] += 1
        if c == h:
            agree[c] += 1
        else:
            disagreements.append({"attempt_id": aid, "classifier": c, "human": h,
                                  "notes": labels[aid].get("notes", "")})
    k, n = sum(agree.values()), len(ids)
    weighted = sum(pop[c] * agree[c] / per[c] for c in per) / sum(pop[c] for c in per)
    res = {
        "n": n, "agree": k, "rate": k / n, "wilson95": wilson(k, n),
        "population_weighted_rate": weighted,
        "per_category": {c: {"n": per[c], "agree": agree[c], "frame_size": pop[c]} for c in sorted(per)},
        "disagreements": disagreements,
        "seed": SEED, "db": str(DB.relative_to(ROOT)),
    }
    SCORE.write_text(json.dumps(res, indent=2))
    lo, hi = res["wilson95"]
    print(f"held-out agreement: {k}/{n} = {k / n:.1%}  (95% Wilson CI {lo:.1%}-{hi:.1%})")
    print(f"population-weighted over the sampled categories: {weighted:.1%}")
    for c in sorted(per):
        print(f"  {c:20s} {agree[c]:3d}/{per[c]:<3d}  (frame {pop[c]})")
    print(f"{len(disagreements)} disagreement(s); details in {SCORE.relative_to(ROOT)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("available").set_defaults(fn=cmd_available)
    s = sp.add_parser("sample")
    s.add_argument("--quota", nargs="+", required=True, metavar="CATEGORY=N")
    s.set_defaults(fn=cmd_sample)
    sp.add_parser("label").set_defaults(fn=cmd_label)
    sp.add_parser("score").set_defaults(fn=cmd_score)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
