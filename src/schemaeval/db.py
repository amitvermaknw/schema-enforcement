"""SQLite logging.

Three tables:
    runs           — one row per graph execution
    node_runs      — one row per node execution
    node_attempts  — one row per LLM call, with raw output + error classification

Schema evolves via idempotent ALTER TABLE migrations in _migrate() — safe to
call init_db() on existing databases; new columns are added without touching
existing rows.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    paradigm TEXT NOT NULL,
    topology TEXT NOT NULL,
    schema_tier TEXT NOT NULL,
    model TEXT NOT NULL,
    max_retries INTEGER NOT NULL,
    question TEXT NOT NULL,
    final_answer TEXT,
    graph_success INTEGER NOT NULL,
    total_input_tokens INTEGER NOT NULL,
    total_output_tokens INTEGER NOT NULL,
    total_repairs INTEGER NOT NULL,
    total_latency_sec REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS node_runs (
    run_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    num_repairs INTEGER NOT NULL,
    latency_sec REAL NOT NULL,
    success INTEGER NOT NULL,
    final_error TEXT,
    PRIMARY KEY (run_id, node_name),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS node_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    attempt_num INTEGER NOT NULL,
    raw_output TEXT,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    validation_ok INTEGER NOT NULL,
    primary_category TEXT,
    all_categories TEXT,
    error_details TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
CREATE INDEX IF NOT EXISTS idx_attempts_run ON node_attempts(run_id);
CREATE INDEX IF NOT EXISTS idx_attempts_category ON node_attempts(primary_category);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent column additions for older DBs."""
    # node_attempts.resolved_model_version
    cols_attempts = {
        row[1]
        for row in conn.execute("PRAGMA table_info(node_attempts)").fetchall()
    }
    if "resolved_model_version" not in cols_attempts:
        conn.execute(
            "ALTER TABLE node_attempts ADD COLUMN resolved_model_version TEXT"
        )
        conn.commit()

    # runs.dataset — added when introducing FinanceBench alongside HotpotQA.
    # Existing rows get 'hotpotqa' as a safe default since all prior runs used it.
    cols_runs = {
        row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
    }
    if "dataset" not in cols_runs:
        conn.execute("ALTER TABLE runs ADD COLUMN dataset TEXT DEFAULT 'hotpotqa'")
        conn.execute("UPDATE runs SET dataset = 'hotpotqa' WHERE dataset IS NULL")
        conn.commit()

    # Post-migration indexes (must follow ALTER TABLE)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_attempts_version "
        "ON node_attempts(resolved_model_version)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_dataset ON runs(dataset)"
    )
    conn.commit()


def init_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    _migrate(conn)
    return conn


def log_run(
    conn: sqlite3.Connection,
    run_result: dict,
    paradigm: str,
    topology: str,
    schema_tier: str,
    model: str,
    max_retries: int,
    dataset: str = "hotpotqa",
) -> None:
    """Log a graph run and all its node attempts."""
    conn.execute(
        """INSERT INTO runs
           (run_id, timestamp, paradigm, topology, schema_tier, model,
            max_retries, question, final_answer, graph_success,
            total_input_tokens, total_output_tokens, total_repairs,
            total_latency_sec, dataset)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_result["run_id"],
            datetime.now(timezone.utc).isoformat(),
            paradigm, topology, schema_tier, model, max_retries,
            run_result["question"],
            run_result["final_answer"],
            int(run_result["graph_success"]),
            run_result["total_input_tokens"],
            run_result["total_output_tokens"],
            run_result["total_repairs"],
            run_result["total_latency_sec"],
            dataset,
        ),
    )
    for node_name, m in run_result["per_node"].items():
        conn.execute(
            "INSERT INTO node_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_result["run_id"], node_name,
                m["total_input_tokens"], m["total_output_tokens"],
                m["num_repairs"], m["latency_sec"],
                int(m["success"]), m["final_error"],
            ),
        )
        for att in m.get("attempts", []):
            err_summary = att.get("error_summary") or {}
            conn.execute(
                """INSERT INTO node_attempts
                   (run_id, node_name, attempt_num, raw_output,
                    input_tokens, output_tokens, validation_ok,
                    primary_category, all_categories, error_details,
                    resolved_model_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_result["run_id"], node_name, att["attempt_num"],
                    att.get("raw_output"),
                    att["input_tokens"], att["output_tokens"],
                    int(att["validation_ok"]),
                    err_summary.get("primary_category"),
                    json.dumps(err_summary.get("categories", [])) if err_summary else None,
                    json.dumps(err_summary.get("errors", [])) if err_summary else None,
                    att.get("resolved_model_version"),
                ),
            )
    conn.commit()