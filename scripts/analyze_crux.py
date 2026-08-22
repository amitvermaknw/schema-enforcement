#!/usr/bin/env python3
"""Analyze the crux experiment: does failure-mode distribution differ across models?

Groups by (model, schema_tier) so ablations show as separate rows. That way,
running the same model against `medium` and `medium_v2` gives you two rows
side-by-side, and any single-condition change is directly visible.

Usage:
    python scripts/analyze_crux.py                 # all rows in DB
    python scripts/analyze_crux.py --tier medium   # filter to one tier
    python scripts/analyze_crux.py --plot          # save PNG comparison
"""

import argparse
import os
import sys
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DB_PATH = os.getenv("DB_PATH", "results/experiments.db")


def load_attempts(conn, tier_filter: str | None = None) -> list[dict]:
    """Load per-attempt records. If tier_filter set, restrict to that tier."""
    sql = """
        SELECT r.model, r.schema_tier, a.node_name, a.attempt_num,
               a.validation_ok, a.primary_category
        FROM node_attempts a
        JOIN runs r ON a.run_id = r.run_id
        WHERE r.paradigm = 'strict_repair'
    """
    params: tuple = ()
    if tier_filter:
        sql += " AND r.schema_tier = ?"
        params = (tier_filter,)
    rows = conn.execute(sql, params).fetchall()
    return [
        {"model": r[0], "tier": r[1], "node": r[2], "attempt": r[3],
         "ok": bool(r[4]), "category": r[5]}
        for r in rows
    ]


def key_of(a: dict) -> str:
    """Composite key: model@tier. Keeps ablations visible."""
    return f"{a['model']}@{a['tier']}"


def build_taxonomy(attempts: list[dict]) -> dict:
    """Returns {model@tier: {category: count}} counting only failed attempts."""
    tax = defaultdict(Counter)
    for a in attempts:
        if a["ok"]:
            continue
        tax[key_of(a)][a["category"] or "unknown"] += 1
    return dict(tax)


def print_summary(attempts: list[dict], tax: dict) -> None:
    by_key = defaultdict(lambda: {"attempts": 0, "failures": 0})
    for a in attempts:
        k = key_of(a)
        by_key[k]["attempts"] += 1
        if not a["ok"]:
            by_key[k]["failures"] += 1

    print("=" * 80)
    print("PER-(MODEL, TIER) FAILURE RATES")
    print("=" * 80)
    print(f"{'Model @ Tier':<48} {'Attempts':>10} {'Failures':>10} {'Rate':>8}")
    print("-" * 80)
    for k, stats in sorted(by_key.items()):
        rate = stats["failures"] / stats["attempts"] if stats["attempts"] else 0
        print(f"{k:<48} {stats['attempts']:>10} {stats['failures']:>10} {rate:>7.1%}")

    print()
    print("=" * 80)
    print("FAILURE TAXONOMY (counts of failures by category)")
    print("=" * 80)

    all_categories = sorted({c for m in tax.values() for c in m})
    if not all_categories:
        print("No failures logged.")
        return

    keys = sorted(tax.keys())
    col_width = max(20, max(len(k) for k in keys) + 2)

    header = f"{'Category':<24}" + "".join(f"{k:>{col_width}}" for k in keys)
    print(header)
    print("-" * len(header))
    for cat in all_categories:
        line = f"{cat:<24}"
        for k in keys:
            line += f"{tax[k].get(cat, 0):>{col_width}}"
        print(line)

    print()
    print("=" * 80)
    print("FAILURE DISTRIBUTION (share of each row's failures, normalized)")
    print("=" * 80)
    print(header)
    print("-" * len(header))
    for cat in all_categories:
        line = f"{cat:<24}"
        for k in keys:
            total = sum(tax[k].values()) or 1
            share = tax[k].get(cat, 0) / total
            line += f"{share:>{col_width-1}.1%} "
        print(line)


def verdict(tax: dict) -> None:
    print()
    print("=" * 80)
    print("VERDICT")
    print("=" * 80)

    if len(tax) < 2:
        print("Need at least 2 (model, tier) rows to compare. Run more configurations.")
        return

    keys = sorted(tax.keys())
    all_categories = sorted({c for m in tax.values() for c in m})
    if not all_categories:
        print("No failures observed.")
        return

    dists = {}
    for k in keys:
        total = sum(tax[k].values()) or 1
        dists[k] = {c: tax[k].get(c, 0) / total for c in all_categories}

    print(f"Comparing failure distributions across {len(keys)} configurations.\n")

    max_divergences = []
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            diffs = {c: abs(dists[k1][c] - dists[k2][c]) for c in all_categories}
            max_cat, max_diff = max(diffs.items(), key=lambda x: x[1])
            max_divergences.append(max_diff)
            print(f"  {k1}")
            print(f"    vs {k2}")
            print(f"    max divergence: {max_diff:.1%} on '{max_cat}'")
            top3 = sorted(diffs.items(), key=lambda x: -x[1])[:3]
            print(f"    top-3: " + ", ".join(f"{c}({d:.1%})" for c, d in top3))
            print()

    overall = max(max_divergences) if max_divergences else 0
    print(f"Overall max divergence across all pairs: {overall:.1%}\n")

    if overall >= 0.20:
        print("Failure distributions differ MEANINGFULLY.")
        print("The paper's thesis is supported: failure modes shift across "
              "model tiers and/or schema tiers.")
    elif overall >= 0.10:
        print("Failure distributions differ MODERATELY.")
    else:
        print("Failure distributions are SIMILAR.")


def maybe_plot(tax: dict, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib not installed; skipping plot)")
        return

    if not tax:
        return
    keys = sorted(tax.keys())
    all_categories = sorted({c for m in tax.values() for c in m})
    if not all_categories:
        return

    fig, ax = plt.subplots(figsize=(max(8, len(all_categories) * 1.3), 5))
    width = 0.8 / len(keys)
    x = list(range(len(all_categories)))
    for i, k in enumerate(keys):
        total = sum(tax[k].values()) or 1
        heights = [tax[k].get(c, 0) / total for c in all_categories]
        offset = (i - (len(keys) - 1) / 2) * width
        ax.bar([xi + offset for xi in x], heights, width=width, label=k)

    ax.set_xticks(x)
    ax.set_xticklabels(all_categories, rotation=30, ha="right")
    ax.set_ylabel("Share of failures")
    ax.set_title("Failure-mode distribution — by (model, schema tier)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "crux_failure_taxonomy.png"
    fig.savefig(out_path, dpi=140)
    print(f"\nFigure saved: {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", action="store_true", help="Save PNG comparison figure")
    ap.add_argument("--tier", default=None, help="Filter to a single schema tier")
    args = ap.parse_args()

    if not Path(DB_PATH).exists():
        raise SystemExit(f"DB not found at {DB_PATH}. Run scripts/run_crux.py first.")

    conn = sqlite3.connect(DB_PATH)
    attempts = load_attempts(conn, tier_filter=args.tier)
    if not attempts:
        raise SystemExit("No attempts logged for that filter.")

    tax = build_taxonomy(attempts)
    print_summary(attempts, tax)
    verdict(tax)

    if args.plot:
        maybe_plot(tax, ROOT / "figures")


if __name__ == "__main__":
    main()