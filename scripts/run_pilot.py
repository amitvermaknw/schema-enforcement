#!/usr/bin/env python3
"""Run the pilot experiment: 5 samples, strict+repair, sequential, medium schema."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from schemaeval.data import PILOT_SAMPLES
from schemaeval.db import init_db, log_run
from schemaeval.paradigms import call_llm_strict_repair
from schemaeval.schemas import get_schemas
from schemaeval.topologies import run_sequential_graph


MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
DB_PATH = os.getenv("DB_PATH", "results/experiments.db")
MAX_RETRIES = 3
SCHEMA_TIER = "medium"


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY not set. Copy .env.example to .env and fill it in."
        )

    schemas = get_schemas(SCHEMA_TIER)
    conn = init_db(DB_PATH)
    print(f"Running {len(PILOT_SAMPLES)} samples on {MODEL} "
          f"(schema={SCHEMA_TIER}, max_retries={MAX_RETRIES})")
    print(f"Logging to: {DB_PATH}\n")

    for i, question in enumerate(PILOT_SAMPLES, 1):
        print(f"[{i}/{len(PILOT_SAMPLES)}] {question[:70]}...")
        result = run_sequential_graph(
            question,
            paradigm_fn=call_llm_strict_repair,
            model=MODEL,
            max_retries=MAX_RETRIES,
            schemas=schemas,
        )
        log_run(
            conn, result,
            paradigm="strict_repair",
            topology="sequential_3node",
            schema_tier=SCHEMA_TIER,
            model=MODEL,
            max_retries=MAX_RETRIES,
        )
        status = "OK" if result["graph_success"] else "FAIL"
        print(
            f"    [{status}] "
            f"tokens={result['total_input_tokens']}+{result['total_output_tokens']} "
            f"repairs={result['total_repairs']} "
            f"latency={result['total_latency_sec']}s"
        )
        if result["final_answer"]:
            print(f"    answer: {result['final_answer'][:100]}")
        for node_name, m in result["per_node"].items():
            marker = " " if m["success"] else "!"
            print(
                f"     {marker} {node_name:10s} "
                f"tok={m['total_input_tokens']:>4}+{m['total_output_tokens']:>4} "
                f"repairs={m['num_repairs']} "
                f"lat={m['latency_sec']}s"
            )
        print()

    row = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(graph_success), 0),
               COALESCE(AVG(total_repairs), 0.0),
               COALESCE(AVG(total_latency_sec), 0.0),
               COALESCE(SUM(total_input_tokens + total_output_tokens), 0)
        FROM runs
        WHERE timestamp >= datetime('now', '-1 hour')
        """
    ).fetchone()
    print("-" * 60)
    print(
        f"Runs: {row[0]} | Success: {row[1]}/{row[0]} | "
        f"Avg repairs: {row[2]:.2f} | Avg latency: {row[3]:.2f}s | "
        f"Total tokens: {row[4]}"
    )


if __name__ == "__main__":
    main()