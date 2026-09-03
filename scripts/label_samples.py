#!/usr/bin/env python3
"""Experiment C: hand-label 100 raw outputs stratified by primary_category.

Purpose: compute precision/recall of the automated failure classifiers
(schema_mirroring, markdown_wrap, prose_preamble) against human judgment.

Usage:
    python scripts/label_samples.py sample   # (re)build the 100-sample set
    python scripts/label_samples.py label    # label unlabeled samples one at a time
    python scripts/label_samples.py score    # compute precision/recall

The workflow is resumable: run 'label' multiple times, each session picks up
where the last left off.

Labels are written to a hand_labels table separate from the main data, so
this tool is non-destructive to your experimental DB.
"""

import argparse
import os
import random
import sqlite3
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(ROOT / "results" / "experiments.db"))

# Ground-truth labels the user can assign. Includes 'other' for cases the
# classifier missed a category, and 'ambiguous' for genuinely borderline outputs.
GROUND_TRUTH_CHOICES = [
    "schema_mirroring",
    "markdown_wrap",
    "prose_preamble",
    "regex_pattern",
    "length_bound",
    "range_bound",
    "enum_violation",
    "missing_field",
    "cross_field_ref",
    "parse_error",
    "other",
    "ambiguous",
]

# How many samples to draw per category. Adjust for your DB's category counts.
# Values chosen to give meaningful precision/recall estimates without over-
# sampling the huge categories (markdown_wrap has ~700; sampling all is
# unnecessary).
DEFAULT_QUOTA = {
    "schema_mirroring": 32,   # entire population (small category)
    "prose_preamble": 20,     # entire population if less
    "markdown_wrap": 25,      # random sample from ~700
    "regex_pattern": 15,
    "length_bound": 15,
    "enum_violation": 5,
    "missing_field": 5,
    "parse_error": 5,
    "cross_field_ref": 5,
}

RANDOM_SEED = 20260828


# ============================================================
# DB setup
# ============================================================

def init_labeling_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS hand_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            classifier_label TEXT NOT NULL,
            ground_truth TEXT,
            notes TEXT,
            labeled_at TEXT,
            UNIQUE(attempt_id),
            FOREIGN KEY (attempt_id) REFERENCES node_attempts(id)
        )"""
    )
    conn.commit()


# ============================================================
# Command: sample
# ============================================================

def cmd_sample(conn: sqlite3.Connection, force: bool = False) -> None:
    """Build the stratified 100-sample set. Idempotent unless --force."""
    init_labeling_table(conn)
    existing = conn.execute("SELECT COUNT(*) FROM hand_labels").fetchone()[0]
    if existing > 0 and not force:
        print(
            f"hand_labels already has {existing} rows. "
            "Run with --force to rebuild the sample set (destroys existing labels)."
        )
        return
    if force:
        conn.execute("DELETE FROM hand_labels")
        conn.commit()

    rng = random.Random(RANDOM_SEED)
    total = 0
    print("Building stratified sample from node_attempts...\n")

    for category, quota in DEFAULT_QUOTA.items():
        candidates = conn.execute(
            """SELECT id FROM node_attempts
               WHERE primary_category = ?
               AND raw_output IS NOT NULL
               AND length(raw_output) > 0""",
            (category,),
        ).fetchall()
        candidate_ids = [row[0] for row in candidates]
        n_available = len(candidate_ids)

        if n_available == 0:
            print(f"  {category:20s}: 0 available (skipped)")
            continue

        n_to_sample = min(quota, n_available)
        sampled_ids = rng.sample(candidate_ids, n_to_sample)

        conn.executemany(
            """INSERT INTO hand_labels
               (attempt_id, classifier_label, ground_truth, notes, labeled_at)
               VALUES (?, ?, NULL, NULL, NULL)""",
            [(aid, category) for aid in sampled_ids],
        )
        total += n_to_sample
        print(
            f"  {category:20s}: sampled {n_to_sample}/{quota} "
            f"(available: {n_available})"
        )

    conn.commit()
    print(f"\nTotal samples: {total}")
    print("Next: `python scripts/label_samples.py label`")


# ============================================================
# Command: label
# ============================================================

def cmd_label(conn: sqlite3.Connection, batch: int = 25) -> None:
    """Interactively label unlabeled samples."""
    init_labeling_table(conn)

    unlabeled = conn.execute(
        """SELECT h.id, h.attempt_id, h.classifier_label,
                  a.raw_output, a.node_name, r.model, r.dataset, r.schema_tier
           FROM hand_labels h
           JOIN node_attempts a ON a.id = h.attempt_id
           JOIN runs r ON r.run_id = a.run_id
           WHERE h.ground_truth IS NULL
           ORDER BY h.id"""
    ).fetchall()

    if not unlabeled:
        print("All samples labeled.")
        print("Next: `python scripts/label_samples.py score`")
        return

    total_remaining = len(unlabeled)
    session_batch = min(batch, total_remaining)
    print(
        f"\n{total_remaining} samples remain. "
        f"Labeling up to {session_batch} this session.\n"
        "Press Ctrl+C at any time — progress is saved after each label.\n"
    )

    for i, (
        label_id, attempt_id, cls_label,
        raw_output, node_name, model, dataset, tier
    ) in enumerate(unlabeled[:session_batch], 1):
        _show_sample(
            i, session_batch, attempt_id, cls_label,
            raw_output, node_name, model, dataset, tier
        )
        gt, notes = _prompt_for_label(cls_label)
        if gt is None:
            print("\nExiting. Progress saved.")
            return

        conn.execute(
            """UPDATE hand_labels
               SET ground_truth = ?, notes = ?,
                   labeled_at = datetime('now')
               WHERE id = ?""",
            (gt, notes, label_id),
        )
        conn.commit()

    print(
        f"\nLabeled {session_batch}. "
        f"{total_remaining - session_batch} remaining."
    )
    if total_remaining - session_batch > 0:
        print("Run `label` again to continue.")
    else:
        print("All done. Run `score` to compute precision/recall.")


def _show_sample(
    i: int, total: int, attempt_id: int, cls_label: str,
    raw: str, node_name: str, model: str, dataset: str, tier: str
) -> None:
    print("=" * 70)
    print(f"Sample {i}/{total}   attempt_id={attempt_id}")
    print(f"Model: {model}   Dataset: {dataset}   Tier: {tier}   Node: {node_name}")
    print(f"Classifier says: {cls_label}")
    print("-" * 70)
    _pretty_print_raw(raw)
    print("=" * 70)


def _pretty_print_raw(raw: str, max_chars: int = 1200) -> None:
    """Show enough of raw_output to make a judgment without overwhelming."""
    if len(raw) <= max_chars:
        print(raw)
    else:
        head = raw[: max_chars // 2]
        tail = raw[-max_chars // 2 :]
        print(head)
        print(f"\n  ... [truncated {len(raw) - max_chars} chars] ...\n")
        print(tail)


def _prompt_for_label(classifier_label: str) -> tuple[str | None, str | None]:
    """Prompt the user for the ground truth label. Returns (label, notes)."""
    print("\nGround truth options:")
    for idx, choice in enumerate(GROUND_TRUTH_CHOICES, 1):
        marker = " <- classifier" if choice == classifier_label else ""
        print(f"  [{idx:2d}] {choice}{marker}")
    print("\nEnter number (1-12), or 'q' to quit, or press Enter to accept classifier label.")

    while True:
        try:
            resp = input("Your label: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None, None

        if resp == "q":
            return None, None
        if resp == "":
            gt = classifier_label
            break
        if resp.isdigit() and 1 <= int(resp) <= len(GROUND_TRUTH_CHOICES):
            gt = GROUND_TRUTH_CHOICES[int(resp) - 1]
            break
        print(f"Invalid input '{resp}'. Enter 1-{len(GROUND_TRUTH_CHOICES)}, blank, or 'q'.")

    try:
        notes = input("Notes (optional, Enter to skip): ").strip() or None
    except (EOFError, KeyboardInterrupt):
        notes = None

    return gt, notes


# ============================================================
# Command: score
# ============================================================

def cmd_score(conn: sqlite3.Connection) -> None:
    """Compute precision/recall per classifier category."""
    init_labeling_table(conn)

    rows = conn.execute(
        """SELECT classifier_label, ground_truth
           FROM hand_labels WHERE ground_truth IS NOT NULL"""
    ).fetchall()

    if not rows:
        print("No labeled samples yet. Run `label` first.")
        return

    # Per-category confusion counts
    categories = sorted({r[0] for r in rows} | {r[1] for r in rows if r[1] != "ambiguous"})

    print(f"\nScored on {len(rows)} labeled samples.\n")

    # Overall agreement rate
    agree = sum(1 for cls, gt in rows if cls == gt)
    ambiguous = sum(1 for cls, gt in rows if gt == "ambiguous")
    print(f"Overall classifier agreement: {agree}/{len(rows)} = {100*agree/len(rows):.1f}%")
    print(f"Ambiguous cases:              {ambiguous}/{len(rows)} = {100*ambiguous/len(rows):.1f}%")
    print()

    # Per-category precision/recall
    print(f"{'Category':<20} {'TP':>4} {'FP':>4} {'FN':>4} {'Precision':>10} {'Recall':>8} {'F1':>6}")
    print("-" * 70)

    for cat in categories:
        tp = sum(1 for cls, gt in rows if cls == cat and gt == cat)
        fp = sum(1 for cls, gt in rows if cls == cat and gt != cat and gt != "ambiguous")
        fn = sum(1 for cls, gt in rows if cls != cat and gt == cat)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        print(
            f"{cat:<20} {tp:>4} {fp:>4} {fn:>4} "
            f"{prec:>9.2%} {rec:>7.2%} {f1:>6.3f}"
        )

    print()
    # Notable disagreements to inspect
    disagreements = conn.execute(
        """SELECT h.attempt_id, h.classifier_label, h.ground_truth, h.notes
           FROM hand_labels h
           WHERE h.ground_truth IS NOT NULL
             AND h.classifier_label != h.ground_truth
             AND h.ground_truth != 'ambiguous'
           ORDER BY h.classifier_label, h.ground_truth"""
    ).fetchall()

    if disagreements:
        print(f"Classifier disagreements ({len(disagreements)} total):")
        for aid, cls, gt, notes in disagreements[:20]:
            note_str = f" — {notes}" if notes else ""
            print(f"  attempt {aid}: classifier={cls}, truth={gt}{note_str}")
        if len(disagreements) > 20:
            print(f"  ... and {len(disagreements) - 20} more")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp_sample = sub.add_parser("sample", help="Build the 100-sample set")
    sp_sample.add_argument("--force", action="store_true",
                           help="Rebuild even if samples exist (destroys labels!)")

    sp_label = sub.add_parser("label", help="Label unlabeled samples interactively")
    sp_label.add_argument("--batch", type=int, default=25,
                          help="Max samples to label this session (default: 25)")

    sub.add_parser("score", help="Compute precision/recall")

    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        if args.cmd == "sample":
            cmd_sample(conn, force=args.force)
        elif args.cmd == "label":
            cmd_label(conn, batch=args.batch)
        elif args.cmd == "score":
            cmd_score(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()