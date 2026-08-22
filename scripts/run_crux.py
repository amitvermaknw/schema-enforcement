#!/usr/bin/env python3
"""Crux experiment runner: does failure-mode distribution differ across models?

Usage examples:
    python3 scripts/run_crux.py --model gpt-5.6-luna --n 2 --dataset hotpotqa --schema-tier medium
    python3 scripts/run_crux.py --model gpt-5.6-terra --n 2 --dataset hotpotqa --schema-tier medium
    python3 scripts/run_crux.py --model gpt-5.6-sol --n 2 --dataset hotpotqa --schema-tier medium
    python3 scripts/run_crux.py --model claude-haiku-4-5-20251001 --n 2 --dataset hotpotqa --schema-tier medium
    python3 scripts/run_crux.py --model claude-sonnet-5 --n 2 --dataset hotpotqa --schema-tier medium
    python3 scripts/run_crux.py --model claude-opus-4-8 --n 2 --dataset hotpotqa --schema-tier medium

Each run appends to results/experiments.db. Then:
    python scripts/analyze_crux.py
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from schemaeval.data import PILOT_SAMPLES, load_financebench, load_hotpotqa
from schemaeval.db import init_db, log_run
from schemaeval.paradigms import call_llm_strict_repair
from schemaeval.schemas import available_tiers, get_schemas
from schemaeval.topologies import run_sequential_graph


DB_PATH = os.getenv("DB_PATH", "results/experiments.db")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True,
                   help="Model name, e.g. gpt-4o-mini, gpt-4o, "
                        "claude-haiku-4-5-20251001, claude-sonnet-4-6")
    p.add_argument("--n", type=int, default=30,
                   help="Number of inputs (default: 30)")
    p.add_argument("--dataset", choices=["hotpotqa", "financebench", "hardcoded"],
                   default="hotpotqa",
                   help="Task-input source (default: hotpotqa)")
    p.add_argument("--schema-tier", default="medium",
                   choices=available_tiers(),
                   help="Which schema tier to use (default: medium)")
    p.add_argument("--max-retries", type=int, default=3)
    return p.parse_args()


def _check_key(model: str) -> None:
    if model.startswith("gpt-") or model.startswith("o1-"):
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY not set in .env")
    elif model.startswith("claude-"):
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit(
                "ANTHROPIC_API_KEY not set in .env. "
                "Get one at console.anthropic.com."
            )


def _load_inputs(source: str, n: int) -> list[str]:
    if source == "hotpotqa":
        print(f"Loading {n} HotpotQA samples...")
        return load_hotpotqa(n=n)
    if source == "financebench":
        print(f"Loading {n} FinanceBench samples...")
        return load_financebench(n=n)
    if source == "hardcoded":
        return PILOT_SAMPLES[:n]
    raise ValueError(f"Unknown dataset: {source}")


def main():
    args = parse_args()
    _check_key(args.model)

    questions = _load_inputs(args.dataset, args.n)
    schemas = get_schemas(args.schema_tier)

    conn = init_db(DB_PATH)
    print(f"Model:       {args.model}")
    print(f"Dataset:     {args.dataset}")
    print(f"Schema tier: {args.schema_tier}")
    print(f"Max retries: {args.max_retries}")
    print(f"Inputs:      {len(questions)}")
    print(f"Logging to:  {DB_PATH}\n")

    n_success = 0
    n_repairs = 0
    total_tokens = 0

    for i, question in enumerate(questions, 1):
        # Truncate the display so long FinanceBench prompts stay readable
        preview = question.replace("\n", " ")[:70]
        print(f"[{i}/{len(questions)}] {preview}...")
        result = run_sequential_graph(
            question,
            paradigm_fn=call_llm_strict_repair,
            model=args.model,
            max_retries=args.max_retries,
            schemas=schemas,
        )
        log_run(
            conn, result,
            paradigm="strict_repair",
            topology="sequential_3node",
            schema_tier=args.schema_tier,
            model=args.model,
            max_retries=args.max_retries,
            dataset=args.dataset,
        )
        status = "OK" if result["graph_success"] else "FAIL"
        print(
            f"    [{status}] "
            f"tokens={result['total_input_tokens']}+{result['total_output_tokens']} "
            f"repairs={result['total_repairs']} "
            f"lat={result['total_latency_sec']}s"
        )
        n_success += int(result["graph_success"])
        n_repairs += result["total_repairs"]
        total_tokens += result["total_input_tokens"] + result["total_output_tokens"]

    print("-" * 60)
    print(
        f"Model={args.model} dataset={args.dataset} tier={args.schema_tier}: "
        f"{n_success}/{len(questions)} succeeded, "
        f"{n_repairs} total repairs, {total_tokens} total tokens"
    )
    print("\nNext: `python scripts/analyze_crux.py`")


if __name__ == "__main__":
    main()