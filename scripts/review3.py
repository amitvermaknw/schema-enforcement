#!/usr/bin/env python3
"""
review3.py — Review-3 analyses for Paper #1 (schema-enforcement paper).

Subcommands
  audit           B:  first-attempt audit + schema introspection -> markdown report
  numbers         A1-A5, A7, A8, A13, A14: manifest, provenance, clustered bootstrap,
                  completion, residual invalidity, first-attempt, fence-by-domain, meta
  derive          A9, A10: pooled perturbation + divergence max, from an existing numbers JSON
  counterfactual  A6: revalidate all Sonnet-4.6 medium outputs under medium and medium_v2
  appcode         A12: generate generated/app_code.tex (listings + diffs) from repo sources

Design rules
  * DB opened read-only (sqlite URI mode=ro). Nothing is written to the DB.
  * Every emitted number is a flat key -> {"value","basis","note","fmt"}; merge with
    `numbers.update(json.load(...)["numbers"])` in make_paper_numbers.py before emitting.
  * Column names that the handoff does not pin down are resolved from candidate lists;
    failures print the actual table columns (run `audit` first — it dumps the schema).
  * Golden checks fail loudly (exit 2) on the invariants the reviewer reconciled by hand.
"""
from __future__ import annotations

import argparse
import ast
import csv
import difflib
import hashlib
import importlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SEED = 20260915
REPS = 2000
PILOT_MIN_RUNS = 30          # fixed before analysis (App. A); applied to baseline runs per cell
BASELINE = "baseline"
FENCE_PURE = "pure_formatting"

# Golden invariants (reconciled by reviewer / previous runs). Hard = exit 2 on mismatch.
GOLDEN_HARD = {
    "manifest.claude-haiku-4-5@medium@hotpotqa@baseline.runs": 134,
    "reported.attempts": 3997,
    "reported.failures": 1126,
    "full.attempts": 4396,
    "full.failures": 1326,
    "fence.reported.pure": 327,
}
GOLDEN_SOFT = {  # inferred by the reviewer; must be verified, not forced
    "g.claude-haiku-4-5@medium.completed": 142,
}

# A2 sampling configuration as sent by the client code. NOT derivable from the DB.
# Fill/confirm from the OpenAI and Anthropic client branches; values below are from §3.2 text.
CLIENT_CONFIG = {
    "claude-haiku-4-5":  {"route": "Anthropic Messages API (direct)", "temperature": "0", "max_tokens": "4096"},
    "claude-sonnet-4-6": {"route": "Anthropic Messages API (direct)", "temperature": "0", "max_tokens": "4096"},
    "claude-sonnet-5":   {"route": "Anthropic Messages API (direct)", "temperature": "omitted", "max_tokens": "4096"},
    "claude-opus-4-8":   {"route": "Anthropic Messages API (direct)", "temperature": "omitted", "max_tokens": "4096"},
    "gpt-4o":            {"route": "OpenAI API (direct)", "temperature": "0", "max_tokens": "not set"},
    "gpt-4o-mini":       {"route": "OpenAI API (direct)", "temperature": "0", "max_tokens": "not set"},
    "gpt-5.6-luna":      {"route": "OpenAI API (direct)", "temperature": "omitted", "max_tokens": "not set"},
    "gpt-5.6-sol":       {"route": "OpenAI API (direct)", "temperature": "omitted", "max_tokens": "not set"},
    "gpt-5.6-terra":     {"route": "OpenAI API (direct)", "temperature": "omitted", "max_tokens": "not set"},
}

ATTEMPT_PK_CANDS = ["attempt_id", "node_attempt_id", "id"]
RAW_CANDS = ["raw_output", "raw_completion", "completion", "raw_text", "raw_response",
             "response_text", "output_text", "output"]
NODE_CANDS = ["node_name", "node"]
REVAL_KEY_CANDS = ["attempt_id", "node_attempt_id", "attempt"]
REVAL_OUTCOME_CANDS = ["outcome", "result", "revalidation_outcome", "status", "classification"]


# ----------------------------------------------------------------------------- DB helpers
def connect_ro(db: Path) -> sqlite3.Connection:
    if not db.exists():
        sys.exit(f"DB not found: {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_cols(con, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def pick(con, table: str, cands: list[str], required: bool = True) -> str | None:
    cols = table_cols(con, table)
    for c in cands:
        if c in cols:
            return c
    if required:
        sys.exit(f"[{table}] none of {cands} found; columns are: {cols}")
    return None


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_model(m: str) -> str:
    """Display id: strip a trailing -YYYYMMDD snapshot suffix (requested id kept in provenance)."""
    return re.sub(r"-\d{8}$", "", m or "")


@dataclass
class Schema:
    attempt_pk: str
    node: str
    raw: str | None
    reval_key: str | None
    reval_outcome: str | None


def resolve_schema(con) -> Schema:
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    rk = ro = None
    if "markdown_wrap_revalidation" in tables:
        rk = pick(con, "markdown_wrap_revalidation", REVAL_KEY_CANDS)
        ro = pick(con, "markdown_wrap_revalidation", REVAL_OUTCOME_CANDS)
    return Schema(
        attempt_pk=pick(con, "node_attempts", ATTEMPT_PK_CANDS),
        node=pick(con, "node_attempts", NODE_CANDS),
        raw=pick(con, "node_attempts", RAW_CANDS, required=False),
        reval_key=rk, reval_outcome=ro,
    )


# ----------------------------------------------------------------------------- data model
@dataclass
class Run:
    run_id: object
    requested: str
    model: str
    tier: str
    dataset: str
    variant: str
    question: str
    ts: str
    success: int | None
    attempts: list = field(default_factory=list)

    @property
    def cell(self):  # (model, tier, dataset, variant)
        return (self.model, self.tier, self.dataset, self.variant)


@dataclass
class Attempt:
    aid: object
    run_id: object
    node: str
    num: int
    ok: int | None
    cat: str | None
    resolved: str | None
    reval: str | None = None


def load(con, sch: Schema):
    runs = {}
    for r in con.execute(
        "SELECT run_id, model, schema_tier, dataset, prompt_variant, question, timestamp, "
        "graph_success FROM runs"
    ):
        runs[r["run_id"]] = Run(r["run_id"], r["model"], norm_model(r["model"]), r["schema_tier"],
                                r["dataset"], r["prompt_variant"], r["question"], r["timestamp"] or "",
                                r["graph_success"])
    reval = {}
    if sch.reval_key:
        for r in con.execute(f"SELECT {sch.reval_key} k, {sch.reval_outcome} o FROM markdown_wrap_revalidation"):
            reval[r["k"]] = r["o"]
    n_orphan = 0
    for r in con.execute(
        f"SELECT {sch.attempt_pk} aid, run_id, {sch.node} node, attempt_num, validation_ok, "
        f"primary_category, resolved_model_version FROM node_attempts ORDER BY run_id, {sch.node}, attempt_num"
    ):
        run = runs.get(r["run_id"])
        if run is None:
            n_orphan += 1
            continue
        run.attempts.append(Attempt(r["aid"], r["run_id"], r["node"], r["attempt_num"], r["validation_ok"],
                                    r["primary_category"], r["resolved_model_version"], reval.get(r["aid"])))
    return runs, reval, n_orphan


# ----------------------------------------------------------------------------- statistics
def wilson(k: int, n: int, z: float = 1.959964) -> list[float]:
    if n == 0:
        return [float("nan")] * 2
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [c - h, c + h]


class ClusterBoot:
    """Question-clustered, dataset-stratified percentile bootstrap over ratio statistics.

    Clusters = (dataset, question). Each replicate resamples questions with replacement within
    each dataset stratum and carries every run and attempt of a selected question. Ratios are
    ratio-of-sums over the replicate. Uncertainty is over the observed fixed question prefix;
    it does not make that prefix representative of the benchmark.
    """

    def __init__(self, strata: list[str], name: str, reps: int = REPS):
        self.n = len(strata)
        rng = np.random.default_rng([SEED, zlib.crc32(name.encode())])
        s = np.asarray(strata)
        self.W = np.zeros((reps, self.n), dtype=np.int32)
        for u in np.unique(s):
            idx = np.flatnonzero(s == u)
            self.W[:, idx] = rng.multinomial(len(idx), np.full(len(idx), 1.0 / len(idx)), size=reps)

    def ratio(self, num, den) -> dict:
        num = np.asarray(num, float)
        den = np.asarray(den, float)
        D = self.W @ den
        N = self.W @ num
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.where(D > 0, N / D, np.nan)
        point = float(num.sum() / den.sum()) if den.sum() > 0 else float("nan")
        finite = r[np.isfinite(r)]
        lo, hi = (np.percentile(finite, [2.5, 97.5]).tolist() if finite.size else [float("nan")] * 2)
        if abs(hi - lo) < 1e-12:  # no bootstrap variation (point at 0/1): percentile CI is uninformative
            lo = hi = None
        return {"point": point, "ci": [lo, hi], "undefined_reps": int((~np.isfinite(r)).sum())}


# ----------------------------------------------------------------------------- aggregation
CATS = ["markdown_wrap", "prose_preamble", "schema_mirroring", "regex_pattern", "length_bound",
        "enum_violation", "missing_field", "range_bound", "parse_error", "cross_field_ref", "other"]


def question_table(runs: list[Run]) -> tuple[list[tuple], dict[str, np.ndarray]]:
    """Aggregate a set of runs to per-(dataset, question) cluster vectors."""
    keys: dict[tuple, int] = {}
    rows = defaultdict(lambda: defaultdict(float))
    for run in runs:
        k = (run.dataset, run.question)
        keys.setdefault(k, len(keys))
        q = rows[k]
        q["runs"] += 1
        q["completed"] += 1 if run.success == 1 else 0
        by_node = defaultdict(list)
        for a in run.attempts:
            by_node[a.node].append(a)
            q["attempts"] += 1
            if a.ok == 0:
                q["failures"] += 1
                q[f"cat.{a.cat}"] += 1
                if a.cat == "markdown_wrap" and a.reval == FENCE_PURE:
                    q["mw_pure"] += 1
        for node, atts in by_node.items():
            first = [a for a in atts if a.num == 0]
            if not first:
                continue
            f = first[0]
            q["fa.reached"] += 1
            q[f"fa.reached.{node}"] += 1
            if f.ok == 1:
                q["fa.valid"] += 1
                q[f"fa.valid.{node}"] += 1
            else:
                q["fa.failed"] += 1
                q[f"fa.failcat.{f.cat}"] += 1
                q[f"fa.failcat.{node}.{f.cat}"] += 1
                if f.cat == "markdown_wrap" and f.reval == FENCE_PURE:
                    q["fa.pure"] += 1
                    q[f"fa.pure.{node}"] += 1
                if any(a.ok == 1 for a in atts if a.num > 0):
                    q["fa.retry_success"] += 1
    order = sorted(keys, key=keys.get)
    all_cols = sorted({c for q in rows.values() for c in q})
    vec = {c: np.array([rows[k].get(c, 0.0) for k in order]) for c in all_cols}
    for c in ("runs", "completed", "attempts", "failures", "mw_pure", "fa.reached", "fa.valid",
              "fa.failed", "fa.pure", "fa.retry_success", "cat.markdown_wrap"):
        vec.setdefault(c, np.zeros(len(order)))
    return order, vec


class Numbers:
    def __init__(self):
        self.d: dict[str, dict] = {}

    def put(self, key, value, basis, fmt="", note=""):
        if isinstance(value, float) and not np.isfinite(value):
            value = None
        if fmt.startswith("ci") and isinstance(value, list) and None in value:
            return  # degenerate interval: emit no key so prose cannot cite it
        if isinstance(value, np.generic):
            value = value.item()
        self.d[key] = {"value": value, "basis": basis, "note": note, "fmt": fmt}

    def get(self, key):
        return self.d[key]["value"]


def group_stats(nums: Numbers, key: str, runs: list[Run], basis: str, with_nodes: bool = True):
    order, v = question_table(runs)
    if not order:
        return None
    bs = ClusterBoot([k[0] for k in order], key)
    att, fail = v["attempts"], v["failures"]
    comp = {c: int(v[f"cat.{c}"].sum()) for c in CATS if f"cat.{c}" in v and v[f"cat.{c}"].sum() > 0}
    out = {"key": key, "runs": int(v["runs"].sum()), "questions": len(order),
           "attempts": int(att.sum()), "failures": int(fail.sum()), "composition": comp}

    rate = bs.ratio(fail, att)
    nums.put(f"{key}.attempts", out["attempts"], basis, "int")
    nums.put(f"{key}.failures", out["failures"], basis, "int")
    nums.put(f"{key}.runs", out["runs"], basis, "int")
    nums.put(f"{key}.questions", out["questions"], basis, "int")
    nums.put(f"{key}.rate", rate["point"], basis, "pct")
    nums.put(f"{key}.ci", rate["ci"], basis, "ci_pct", "question-clustered bootstrap, 2,000 reps, percentile")
    nums.put(f"{key}.ci_wilson_ref", wilson(out["failures"], out["attempts"]), basis, "ci_pct",
             "reference only: Wilson over attempts, ignores clustering")
    out.update(rate=rate["point"], ci=rate["ci"])

    if comp:
        dom = max(comp, key=lambda c: (comp[c], -CATS.index(c)))
        sh = bs.ratio(v[f"cat.{dom}"], fail)
        nums.put(f"{key}.dominant", dom, basis, "str")
        nums.put(f"{key}.dominant_n", comp[dom], basis, "int")
        nums.put(f"{key}.dominant_share", sh["point"], basis, "pct")
        nums.put(f"{key}.dominant_ci", sh["ci"], basis, "ci_pct",
                 "bootstrap share of the full-sample dominant category (category held fixed)")
        out.update(dominant=dom, dominant_share=sh["point"], dominant_ci=sh["ci"])
        for c, n in comp.items():
            s = bs.ratio(v[f"cat.{c}"], fail)
            nums.put(f"{key}.share.{c}", s["point"], basis, "pct")
            nums.put(f"{key}.share.{c}.ci", s["ci"], basis, "ci_pct")
            r = bs.ratio(v[f"cat.{c}"], att)
            nums.put(f"{key}.attrate.{c}", r["point"], basis, "pct", "per attempt")

    # A4 completion
    c = bs.ratio(v["completed"], v["runs"])
    nums.put(f"{key}.completed", int(v["completed"].sum()), basis, "int")
    nums.put(f"{key}.completion_rate", c["point"], basis, "pct")
    nums.put(f"{key}.completion_ci", c["ci"], basis, "ci_pct")
    apc = bs.ratio(att, v["completed"])
    nums.put(f"{key}.attempts_per_completed_run", apc["point"], basis, "f2")
    nums.put(f"{key}.attempts_per_run", float(att.sum() / v["runs"].sum()), basis, "f2")
    out.update(completed=int(v["completed"].sum()), completion_rate=c["point"],
               completion_ci=c["ci"], attempts_per_completed_run=apc["point"])

    # A5 offline residual invalidity after fence removal
    res = bs.ratio(fail - v["mw_pure"], att)
    nums.put(f"{key}.residual_rate", res["point"], basis, "pct",
             "offline on stored attempts: (failures - pure fence failures)/attempts; not a re-run")
    nums.put(f"{key}.residual_ci", res["ci"], basis, "ci_pct")
    nums.put(f"{key}.fence_pure", int(v["mw_pure"].sum()), basis, "int")
    mw = v["cat.markdown_wrap"]
    if mw.sum() > 0:
        cs = bs.ratio(mw - v["mw_pure"], mw)
        nums.put(f"{key}.fence_n", int(mw.sum()), basis, "int")
        nums.put(f"{key}.fence_compound", int((mw - v["mw_pure"]).sum()), basis, "int")
        nums.put(f"{key}.fence_compound_share", cs["point"], basis, "pct")
        nums.put(f"{key}.fence_compound_ci", cs["ci"], basis, "ci_pct")
    out.update(residual_rate=res["point"], residual_ci=res["ci"], fence_pure=int(v["mw_pure"].sum()),
               fence_n=int(mw.sum()))

    # A7b retry trajectory: category by attempt_num; run-nodes that exhausted retries
    traj = defaultdict(Counter)
    exhausted = Counter()
    for run in runs:
        by_node = defaultdict(list)
        for x in run.attempts:
            by_node[x.node].append(x)
            traj[x.num]["n"] += 1
            traj[x.num]["valid" if x.ok == 1 else f"cat.{x.cat}"] += 1
        for node, atts in by_node.items():
            if not any(x.ok == 1 for x in atts):
                last = max(atts, key=lambda x: x.num)
                exhausted["n"] += 1
                exhausted[f"node.{node}"] += 1
                exhausted[f"cat.{last.cat}"] += 1
    for k, c in sorted(traj.items()):
        for f_, n in c.items():
            nums.put(f"{key}.att{k}.{f_}", n, basis, "int")
    nums.put(f"{key}.exhausted", exhausted["n"], basis, "int", "run-nodes with no valid attempt")
    for f_, n in exhausted.items():
        if f_ != "n":
            nums.put(f"{key}.exhausted.{f_}", n, basis, "int")

    # A7 first attempt (pooled over nodes)
    fr = v["fa.reached"]
    if fr.sum() > 0:
        fv = bs.ratio(v["fa.valid"], fr)
        ff = bs.ratio(v["fa.valid"] + v["fa.pure"], fr)
        rs = bs.ratio(v["fa.retry_success"], v["fa.failed"])
        nums.put(f"{key}.fa.reached", int(fr.sum()), basis, "int")
        nums.put(f"{key}.fa.valid", int(v["fa.valid"].sum()), basis, "int")
        nums.put(f"{key}.fa.valid_rate", fv["point"], basis, "pct")
        nums.put(f"{key}.fa.valid_ci", fv["ci"], basis, "ci_pct")
        nums.put(f"{key}.fa.valid_after_fence", int((v["fa.valid"] + v["fa.pure"]).sum()), basis, "int")
        nums.put(f"{key}.fa.valid_after_fence_rate", ff["point"], basis, "pct",
                 "offline: first attempt valid, or pure-formatting markdown_wrap")
        nums.put(f"{key}.fa.valid_after_fence_ci", ff["ci"], basis, "ci_pct")
        nums.put(f"{key}.fa.failed", int(v["fa.failed"].sum()), basis, "int")
        nums.put(f"{key}.fa.retry_success", int(v["fa.retry_success"].sum()), basis, "int")
        nums.put(f"{key}.fa.retry_success_rate", rs["point"], basis, "pct",
                 "node-invocations whose first attempt failed and a later attempt validated")
        facomp = {c.split(".", 2)[2]: int(v[c].sum()) for c in v
                  if c.startswith("fa.failcat.") and c.count(".") == 2 and v[c].sum() > 0}
        for c, n in facomp.items():
            nums.put(f"{key}.fa.failcat.{c}", n, basis, "int")
        out.update(fa_reached=int(fr.sum()), fa_valid=int(v["fa.valid"].sum()), fa_valid_rate=fv["point"],
                   fa_valid_after_fence=int((v["fa.valid"] + v["fa.pure"]).sum()),
                   fa_valid_after_fence_rate=ff["point"], fa_failed=int(v["fa.failed"].sum()),
                   fa_retry_success=int(v["fa.retry_success"].sum()), fa_retry_success_rate=rs["point"],
                   fa_composition=facomp, nodes={})
        if with_nodes:
            for node in ("identify", "gather", "answer"):
                rc = f"fa.reached.{node}"
                if rc not in v or v[rc].sum() == 0:
                    continue
                vc = v.get(f"fa.valid.{node}", np.zeros(len(order)))
                pc = v.get(f"fa.pure.{node}", np.zeros(len(order)))
                comp_n = {c.split(".", 3)[3]: int(v[c].sum()) for c in v
                          if c.startswith(f"fa.failcat.{node}.") and v[c].sum() > 0}
                nums.put(f"{key}.fa.{node}.reached", int(v[rc].sum()), basis, "int")
                nums.put(f"{key}.fa.{node}.valid", int(vc.sum()), basis, "int")
                nums.put(f"{key}.fa.{node}.valid_after_fence", int((vc + pc).sum()), basis, "int")
                out["nodes"][node] = {"reached": int(v[rc].sum()), "valid": int(vc.sum()),
                                      "valid_after_fence": int((vc + pc).sum()), "composition": comp_n}
    return out


# ----------------------------------------------------------------------------- git / meta
def git_info(repo: Path, paths: list[str]) -> dict:
    def g(*args):
        try:
            return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                                  check=True).stdout.strip()
        except Exception:
            return ""
    info = {"head": g("rev-parse", "HEAD"), "files": {}}
    resolved = []
    for p in paths:
        if not (repo / p).exists():
            hits = [h for h in g("ls-files", "--", f"*{Path(p).name}").splitlines() if h]
            p = hits[0] if len(hits) == 1 else p
        resolved.append(p)
    for p in resolved:
        info["files"][p] = {"commit": g("log", "-1", "--format=%H", "--", p),
                            "dirty": bool(g("status", "--porcelain", "--", p))}
    info["tag"] = g("describe", "--tags", "--exact-match") or ""
    return info


# ----------------------------------------------------------------------------- LaTeX
def tex_esc(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%")
            .replace("&", r"\&").replace("#", r"\#"))


def pct(x, d=1):
    return "--" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{100 * x:.{d}f}"


def ci_s(ci, d=1):
    if not ci or any(c is None or not np.isfinite(c) for c in ci) or abs(ci[1] - ci[0]) < 1e-12:
        return "--"
    return f"[{100 * ci[0]:.{d}f}, {100 * ci[1]:.{d}f}]"


def tabular(spec: str, header: list[str], rows: list[list[str]]) -> str:
    lines = [rf"\begin{{tabular}}{{{spec}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    lines += [" & ".join(r) + r" \\" for r in rows]
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- numbers
def cmd_numbers(a):
    db = Path(a.db)
    con = connect_ro(db)
    sch = resolve_schema(con)
    runs, reval, n_orphan = load(con, sch)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    N = Numbers()
    allruns = list(runs.values())

    # ---- A1 manifest (variant-consistent) --------------------------------------------------
    cells = defaultdict(list)
    for r in allruns:
        cells[r.cell].append(r)
    baseline_runs = {(m, t, d): len(rs) for (m, t, d, v), rs in cells.items() if v == BASELINE}
    manifest = []
    for (m, t, d, v), rs in sorted(cells.items()):
        atts = [x for r in rs for x in r.attempts]
        excluded_reason = ("prompt_variant" if v != BASELINE
                           else "pilot" if baseline_runs[(m, t, d)] < PILOT_MIN_RUNS else "")
        ts = sorted(r.ts for r in rs if r.ts)
        row = {"model": m, "tier": t, "domain": d, "variant": v, "runs": len(rs),
               "questions": len({r.question for r in rs}),
               "attempts": len(atts), "failures": sum(1 for x in atts if x.ok == 0),
               "completed": sum(1 for r in rs if r.success == 1),
               "date_min": ts[0][:10] if ts else "", "date_max": ts[-1][:10] if ts else "",
               "requested_ids": sorted({r.requested for r in rs}),
               "excluded": bool(excluded_reason), "excluded_reason": excluded_reason}
        manifest.append(row)
        k = f"manifest.{m}@{t}@{d}@{v}"
        for f_ in ("runs", "questions", "attempts", "failures"):
            N.put(f"{k}.{f_}", row[f_], "full", "int")
        N.put(f"{k}.dates", f"{row['date_min']}--{row['date_max']}", "full", "str")
    N.put("manifest", manifest, "full", "list",
          "runs, attempts, failures counted with the same prompt_variant filter; one row per variant")

    included = [r for r in allruns if r.variant == BASELINE and baseline_runs[(r.model, r.tier, r.dataset)] >= PILOT_MIN_RUNS]
    inc_ids = {id(r) for r in included}

    def tot(rs):
        at = [x for r in rs for x in r.attempts]
        return len(at), sum(1 for x in at if x.ok == 0)
    for name, rs in (("full", allruns), ("reported", included),
                     ("excluded_pilot", [r for r in allruns if r.variant == BASELINE and id(r) not in inc_ids]),
                     ("excluded_variant", [r for r in allruns if r.variant != BASELINE])):
        at, fl = tot(rs)
        N.put(f"{name}.attempts", at, name, "int")
        N.put(f"{name}.failures", fl, name, "int")
        N.put(f"{name}.runs", len(rs), name, "int")
    N.put("reconcile.ok", N.get("full.attempts") == N.get("reported.attempts") + N.get("excluded_pilot.attempts")
          + N.get("excluded_variant.attempts"), "full", "str")
    N.put("reported.cells", len({r.cell for r in included}), "reported", "int")
    all_ts = sorted(r.ts for r in allruns if r.ts)
    N.put("collection.date_min", all_ts[0][:10] if all_ts else "", "full", "str")
    N.put("collection.date_max", all_ts[-1][:10] if all_ts else "", "full", "str")
    N.put("pilot.min_runs", PILOT_MIN_RUNS, "full", "int", "fixed before analysis")
    N.put("data.orphan_attempts", n_orphan, "full", "int")

    # question manifest (exact question identities; check licence before release)
    with (out_dir / "question_manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "question_sha1_12", "cells", "runs", "question"])
        qs = defaultdict(lambda: [set(), 0])
        for r in allruns:
            qs[(r.dataset, r.question)][0].add(f"{r.model}@{r.tier}@{r.variant}")
            qs[(r.dataset, r.question)][1] += 1
        for (d, q), (cs, n) in sorted(qs.items()):
            w.writerow([d, hashlib.sha1(q.encode()).hexdigest()[:12], len(cs), n, q])

    # ---- A2 provenance ---------------------------------------------------------------------
    prov = []
    by_model = defaultdict(list)
    for r in allruns:
        by_model[r.model].append(r)
    for m, rs in sorted(by_model.items()):
        ret = Counter(x.resolved or "<not captured>" for r in rs for x in r.attempts)
        ts = sorted(r.ts for r in rs if r.ts)
        cfg = CLIENT_CONFIG.get(m, {"route": "UNKNOWN", "temperature": "UNKNOWN", "max_tokens": "UNKNOWN"})
        row = {"model": m, "requested": sorted({r.requested for r in rs}), "returned": dict(ret),
               "date_min": ts[0][:10] if ts else "", "date_max": ts[-1][:10] if ts else "", **cfg}
        prov.append(row)
        N.put(f"prov.{m}.dates", f"{row['date_min']}--{row['date_max']}", "full", "str")
        N.put(f"prov.{m}.not_captured", ret.get("<not captured>", 0), "full", "int")
    N.put("provenance", prov, "full", "list", "temperature/max_tokens/route from CLIENT_CONFIG, not the DB")

    # ---- A3/A4/A5/A7 per group and cell; pooled -------------------------------------------
    groups, cells_out = [], []
    by_group = defaultdict(list)
    by_cell = defaultdict(list)
    for r in included:
        by_group[(r.model, r.tier)].append(r)
        by_cell[(r.model, r.tier, r.dataset)].append(r)
    for (m, t), rs in sorted(by_group.items()):
        s = group_stats(N, f"g.{m}@{t}", rs, "reported")
        s.update(model=m, tier=t)
        groups.append(s)
    for (m, t, d), rs in sorted(by_cell.items()):
        s = group_stats(N, f"c.{m}@{t}@{d}", rs, "reported", with_nodes=False)
        s.update(model=m, tier=t, domain=d)
        cells_out.append(s)
    pooled = group_stats(N, "pooled.reported", included, "reported", with_nodes=False)

    # macro/median over medium groups (unchanged definitions)
    med = [g["rate"] for g in groups if g["tier"] == "medium"]
    N.put("reported.medium.macro_rate", float(np.mean(med)), "reported", "pct")
    N.put("reported.medium.median_rate", float(np.median(med)), "reported", "pct")

    # fence reported basis (golden)
    N.put("fence.reported.pure", pooled["fence_pure"], "reported", "int")
    N.put("fence.reported.n", pooled["fence_n"], "reported", "int")

    # ---- A8 fence + dominant by domain ----------------------------------------------------
    fdom = [{k: c.get(k) for k in ("model", "tier", "domain", "attempts", "failures", "rate", "dominant",
                                   "dominant_share", "fence_n", "fence_pure")} for c in cells_out]
    N.put("fence_by_domain", fdom, "reported", "list")
    for m in {c["model"] for c in cells_out}:
        doms = {c["domain"]: c.get("dominant") for c in cells_out if c["model"] == m and c["tier"] == "medium"}
        if len(set(doms.values())) > 1:
            N.put(f"domain_shift.{m}", ", ".join(f"{d}={v}" for d, v in sorted(doms.items())), "reported", "str",
                  "dominant category differs by domain")

    # ---- A14 earliest-run rule + repeated-question robustness -----------------------------
    def earliest(rs):
        best = {}
        for r in sorted(rs, key=lambda r: (r.ts, str(r.run_id))):
            best.setdefault((r.cell, r.question), r)
        return list(best.values())
    rule = "per (model, tier, dataset, variant, question): minimum runs.timestamp, ties by run_id"
    N.put("robust.one_run.rule", rule, "reported", "str")
    hh = by_cell.get(("claude-haiku-4-5", "medium", "hotpotqa"), [])
    if hh:
        er = earliest(hh)
        at, fl = tot(er)
        N.put("robust.one_run.runs", len(er), "reported", "int")
        N.put("robust.one_run.attempts", at, "reported", "int")
        N.put("robust.one_run.failures", fl, "reported", "int")
        N.put("robust.one_run.rate", fl / at if at else None, "reported", "pct")
        rpq = Counter(Counter(r.question for r in hh).values())
        N.put("robust.cell.runs_per_question", {str(k): v for k, v in sorted(rpq.items())}, "reported", "dict")
    worst = (0.0, "")
    for (m, t, d), rs in sorted(by_cell.items()):
        er = earliest(rs)
        a_full, f_full = tot(rs)
        a_er, f_er = tot(er)
        dpp = 100 * (f_er / a_er - f_full / a_full)
        k = f"robust.cell.{m}@{t}@{d}"
        N.put(f"{k}.dedup_runs", len(er), "reported", "int")
        N.put(f"{k}.dedup_rate", f_er / a_er, "reported", "pct")
        N.put(f"{k}.delta_pp", dpp, "reported", "pp")
        if abs(dpp) > abs(worst[0]):
            worst = (dpp, f"{m}@{t}@{d}")
    N.put("robust.within_cell.max_abs_delta_pp", abs(worst[0]), "reported", "pp",
          f"largest within-cell rate change from keeping earliest run per question: {worst[1]}")
    N.put("robust.within_cell.max_cell", worst[1], "reported", "str")
    er_all = earliest(included)
    at, fl = tot(er_all)
    N.put("robust.dedup_all.attempts", at, "reported", "int")
    N.put("robust.dedup_all.rate", fl / at, "reported", "pct")
    N.put("robust.dedup_all.delta_pp", 100 * (fl / at - pooled["rate"]), "reported", "pp",
          "pooled rate change; dominated by reweighting (dedup removes most Haiku runs), do not cite as robustness")

    # ---- A13 meta ---------------------------------------------------------------------------
    db_sha = sha256_file(db)
    N.put("meta.db_sha256", db_sha, "meta", "str")
    N.put("meta.db_sha256_short", db_sha[:12], "meta", "str")
    repo = Path(a.repo) if a.repo else None
    if repo:
        gi = git_info(repo, a.track)
        N.put("meta.git_head", gi["head"], "meta", "str")
        N.put("meta.git_head_short", gi["head"][:10], "meta", "str")
        N.put("meta.git_tag", gi["tag"], "meta", "str")
        N.put("meta.tracked", gi["files"], "meta", "dict")
        dirty = [p for p, v in gi["files"].items() if v["dirty"]]
        N.put("meta.dirty", bool(dirty), "meta", "str", ", ".join(dirty))
    N.put("meta.bootstrap", {"reps": REPS, "seed": SEED, "cluster": "dataset,question",
                             "strata": "dataset", "interval": "percentile 95%"}, "meta", "dict")
    N.put("meta.bootstrap_reps", REPS, "meta", "int")
    N.put("meta.versions", {"python": platform.python_version(), "numpy": np.__version__}, "meta", "dict")

    # ---- golden checks --------------------------------------------------------------------
    failures = []
    for k, exp in ({} if a.skip_golden else GOLDEN_HARD).items():
        got = N.d.get(k, {}).get("value")
        if got != exp:
            failures.append(f"HARD {k}: expected {exp}, got {got}")
    for k, exp in GOLDEN_SOFT.items():
        got = N.d.get(k, {}).get("value")
        if got != exp:
            print(f"[soft] {k}: reviewer inferred {exp}, DB gives {got} — report DB value", file=sys.stderr)

    # ---- tables -----------------------------------------------------------------------------
    write_tables(out_dir, N, manifest, prov, groups, cells_out, pooled)
    payload = {"meta": {"db": str(db), "sha256": db_sha, "generated_utc": datetime.now(timezone.utc).isoformat(),
                        "schema_resolution": sch.__dict__, "script": "review3.py numbers"},
               "numbers": N.d}
    (out_dir / "review3_numbers.json").write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {out_dir/'review3_numbers.json'} ({len(N.d)} keys)")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        sys.exit(2)


def write_tables(out: Path, N: Numbers, manifest, prov, groups, cells, pooled):
    code = lambda s: rf"\code{{{tex_esc(s)}}}"
    # A1 manifest
    rows = []
    for m in manifest:
        rows.append([code(m["model"]), tex_esc(m["tier"]), tex_esc(m["domain"]), tex_esc(m["variant"]),
                     str(m["runs"]), str(m["questions"]), str(m["attempts"]), str(m["failures"]),
                     f"{m['date_min']}--{m['date_max']}", tex_esc(m["excluded_reason"] or "--")])
    (out / "tab_manifest_r3.tex").write_text(tabular("lllrrrrrll",
        ["Model", "Tier", "Domain", "Prompt", "Runs", "Qs", "Att.", "Fail.", "Collected", "Excluded"], rows))
    # A2 provenance
    rows = []
    for p in prov:
        ret = "; ".join(f"{tex_esc(k)} ({v})" for k, v in sorted(p["returned"].items()))
        rows.append([", ".join(code(x) for x in p["requested"]), ret, tex_esc(p["route"]),
                     f"{p['date_min']}--{p['date_max']}", tex_esc(p["temperature"]), tex_esc(p["max_tokens"])])
    (out / "tab_provenance.tex").write_text(tabular("p{3.2cm}p{4.2cm}p{2.4cm}lll",
        ["Requested ID", "Returned ID (attempts)", "Route", "Collected", "Temp.", "max\\_tokens"], rows))
    # A3 models (replaces Wilson)
    rows = []
    for g in sorted([g for g in groups if g["tier"] == "medium"], key=lambda g: -g["rate"]):
        rows.append([code(g["model"]), str(g["runs"]), str(g["attempts"]), str(g["failures"]),
                     pct(g["rate"]), ci_s(g["ci"]), tex_esc(g.get("dominant", "--")),
                     pct(g.get("dominant_share")), ci_s(g.get("dominant_ci"))])
    (out / "tab_models_r3.tex").write_text(tabular("lrrrrlllr",
        ["Model", "Runs", "Att.", "Fail.", "Rate \\%", "95\\% CI", "Dominant", "Share \\%", "95\\% CI"], rows))
    # A4 completion + A5 residual
    rows = []
    for g in sorted(groups, key=lambda g: -g["rate"]):
        rows.append([code(g["model"]), tex_esc(g["tier"]), str(g["runs"]), str(g["completed"]),
                     pct(g["completion_rate"]), f"{g['attempts_per_completed_run']:.2f}",
                     pct(g["rate"]), pct(g["residual_rate"]), ci_s(g["residual_ci"])])
    rows.append([r"\emph{Pooled}", "", str(pooled["runs"]), str(pooled["completed"]), pct(pooled["completion_rate"]),
                 f"{pooled['attempts_per_completed_run']:.2f}", pct(pooled["rate"]), pct(pooled["residual_rate"]),
                 ci_s(pooled["residual_ci"])])
    (out / "tab_operational.tex").write_text(tabular("llrrrrrrl",
        ["Model", "Tier", "Runs", "Compl.", "Compl. \\%", "Att./compl.", "Strict fail \\%",
         "Residual \\%", "95\\% CI"], rows))
    # A7 first attempt
    rows = []
    for g in sorted(groups, key=lambda g: (g["model"], g["tier"])):
        for node in ("identify", "gather", "answer"):
            nd = g.get("nodes", {}).get(node)
            if not nd:
                continue
            compo = ", ".join(f"{tex_esc(c)} {n}" for c, n in sorted(nd["composition"].items(), key=lambda x: -x[1]))
            rows.append([code(g["model"]), tex_esc(g["tier"]), node, f"{nd['valid']}/{nd['reached']}",
                         f"{nd['valid_after_fence']}/{nd['reached']}", compo or "--"])
        rows.append([code(g["model"]), tex_esc(g["tier"]), r"\emph{retry}",
                     f"{g['fa_retry_success']}/{g['fa_failed']}", "", r"\emph{failed first attempts later valid}"])
    (out / "tab_first_attempt_r3.tex").write_text(tabular("lllrrp{5cm}",
        ["Model", "Tier", "Node", "Valid/reached", "After fence", "First-attempt failure composition"], rows))
    # A8 by domain
    rows = []
    for c in sorted(cells, key=lambda c: (c["model"], c["tier"], c["domain"])):
        comp = c["fence_n"] - c["fence_pure"]
        rows.append([code(c["model"]), tex_esc(c["tier"]), tex_esc(c["domain"]), pct(c["rate"]),
                     tex_esc(c.get("dominant", "--")), pct(c.get("dominant_share")),
                     f"{c['fence_pure']}/{c['fence_n']}" if c["fence_n"] else "--",
                     str(comp) if c["fence_n"] else "--"])
    (out / "tab_domain.tex").write_text(tabular("lllrlrrr",
        ["Model", "Tier", "Domain", "Rate \\%", "Dominant", "Share \\%", "Pure/wrapped", "Compound"], rows))


# ----------------------------------------------------------------------------- derive (A9, A10)
def cmd_derive(a):
    src = json.loads(Path(a.numbers).read_text())
    n = src["numbers"]
    v = lambda k: n[k]["value"]
    D = Numbers()
    tiers = ["medium", "medium_v3_loose_regex"]
    for f_ in ("failures", "regex_failures", "identifiers", "multi_subcause", "leading_digit",
               "length_overflow", "unicode", "invalid_char", "other"):
        D.put(f"pert.pooled.{f_}", sum(v(f"pert.{t}.{f_}") for t in tiers), "reported", "int")
    D.put("pert.subcause_labeling", "multilabel", "reported", "str",
          "sub-causes counted independently; non-ASCII characters excluded from invalid_char")
    top = v("divergence.unrestricted.top")
    mx = max(t["pp"] for t in top)
    tied = [t for t in top if abs(t["pp"] - mx) < 1e-9]
    D.put("divergence.unrestricted.max.pp", mx, "reported", "pp")
    D.put("divergence.unrestricted.max.category", tied[0]["category"], "reported", "str")
    D.put("divergence.unrestricted.max.n_tied", len(tied), "reported", "int")
    D.put("divergence.unrestricted.max.pairs",
          "; ".join(f"{t['a']} vs {t['b']}" for t in tied), "reported", "str")
    for i, t in enumerate(tied):
        D.put(f"divergence.unrestricted.max.{i}.a", t["a"], "reported", "str")
        D.put(f"divergence.unrestricted.max.{i}.b", t["b"], "reported", "str")
    rtop = v("divergence.top")
    rmx = max(t["pp"] for t in rtop)
    D.put("divergence.top.n_tied", sum(abs(t["pp"] - rmx) < 1e-9 for t in rtop), "reported", "int")
    out = Path(a.out)
    out.write_text(json.dumps({"meta": {"derived_from": a.numbers}, "numbers": D.d}, indent=2))
    for k, x in D.d.items():
        print(f"{k} = {x['value']}")


# ----------------------------------------------------------------------------- audit (B)
def q(con, sql, params=()):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return cols, [tuple(r) for r in cur.fetchall()]


def md_table(cols, rows, limit=60):
    s = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    s += ["| " + " | ".join("" if x is None else str(x) for x in r) + " |" for r in rows[:limit]]
    if len(rows) > limit:
        s.append(f"| … {len(rows) - limit} more rows |")
    return "\n".join(s)


def cmd_audit(a):
    con = connect_ro(Path(a.db))
    sch = resolve_schema(con)
    node, pk = sch.node, sch.attempt_pk
    rep = [f"# Review-3 audit\n\nDB: `{a.db}`  sha256 `{sha256_file(Path(a.db))}`  "
           f"generated {datetime.now(timezone.utc).isoformat()}\n"]

    rep.append("## 0. Schema\n")
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        rep.append(f"- `{t}` ({n} rows): " + ", ".join(table_cols(con, t)))
    rep.append(f"\nResolved: {sch.__dict__}\n")

    H = "r.model LIKE 'claude-haiku-4-5%' AND r.prompt_variant='baseline'"
    checks = [
        ("B1 run-node pairs without exactly one attempt_num=0 (all data)",
         f"SELECT COUNT(*) n_bad FROM (SELECT run_id,{node},SUM(attempt_num=0) k FROM node_attempts GROUP BY 1,2) WHERE k<>1"),
        ("B1b breakdown of k (first attempts per run-node)",
         f"SELECT k, COUNT(*) FROM (SELECT run_id,{node},SUM(attempt_num=0) k FROM node_attempts GROUP BY 1,2) GROUP BY k"),
        ("B2 validity by attempt_num × primary_category, Haiku baseline",
         f"SELECT a.attempt_num, COUNT(*) n, SUM(a.validation_ok) valid, a.primary_category "
         f"FROM node_attempts a JOIN runs r USING(run_id) WHERE {H} GROUP BY 1,4 ORDER BY 1,2 DESC"),
        ("B3 attempt_num contiguity: run-nodes where max(attempt_num)+1 != count or min != 0",
         f"SELECT COUNT(*) FROM (SELECT run_id,{node},MIN(attempt_num) mn,MAX(attempt_num) mx,COUNT(*) c "
         f"FROM node_attempts GROUP BY 1,2) WHERE mn<>0 OR mx+1<>c"),
        ("B4 attempts logged after a valid attempt in the same run-node (should be 0)",
         f"SELECT COUNT(*) FROM node_attempts a JOIN node_attempts b ON a.run_id=b.run_id AND a.{node}=b.{node} "
         f"AND b.attempt_num>a.attempt_num WHERE a.validation_ok=1"),
        ("B5 flag consistency: NULL validation_ok; valid with category; invalid without category",
         "SELECT SUM(validation_ok IS NULL) null_ok, SUM(validation_ok=1 AND primary_category IS NOT NULL) valid_with_cat, "
         "SUM(validation_ok=0 AND primary_category IS NULL) invalid_no_cat, "
         "SUM(validation_ok=1 AND error_details IS NOT NULL AND error_details NOT IN ('','[]','null')) valid_with_errors, "
         "SUM(validation_ok=0 AND (error_details IS NULL OR error_details IN ('','[]','null'))) invalid_no_errors FROM node_attempts"),
        ("B6 first-attempt validity by model (baseline), all nodes",
         "SELECT r.model, COUNT(*) reached, SUM(a.validation_ok) valid, ROUND(AVG(a.validation_ok),4) rate "
         "FROM node_attempts a JOIN runs r USING(run_id) WHERE a.attempt_num=0 AND r.prompt_variant='baseline' "
         "GROUP BY 1 ORDER BY 4"),
        ("B7 Haiku first attempts by collection date × dataset (batch uniformity)",
         f"SELECT substr(r.timestamp,1,10) day, r.dataset, COUNT(*) first_attempts, SUM(a.validation_ok) valid "
         f"FROM node_attempts a JOIN runs r USING(run_id) WHERE {H} AND a.attempt_num=0 GROUP BY 1,2 ORDER BY 1"),
        ("B8 Haiku (baseline) attempts per run-node: distribution of attempt counts and final validity",
         f"SELECT c attempts, SUM(ok) ended_valid, COUNT(*) run_nodes FROM (SELECT a.run_id,a.{node},COUNT(*) c,"
         f"MAX(a.validation_ok) ok FROM node_attempts a JOIN runs r USING(run_id) WHERE {H} GROUP BY 1,2) GROUP BY 1"),
        ("B9 run completion vs answer-node validity (baseline), mismatches by model",
         f"SELECT r.model, COUNT(*) runs, SUM(r.graph_success=1) completed, SUM(r.graph_success IS NULL) null_flag, "
         f"SUM((r.graph_success=1) <> COALESCE(x.ans_ok,0)) mismatch FROM runs r LEFT JOIN "
         f"(SELECT run_id, MAX(validation_ok) ans_ok FROM node_attempts WHERE {node}='answer' GROUP BY 1) x USING(run_id) "
         f"WHERE r.prompt_variant='baseline' GROUP BY 1"),
        ("B10 runs per cell by prompt_variant (manifest bug check)",
         "SELECT model, schema_tier, dataset, prompt_variant, COUNT(*) runs, COUNT(DISTINCT question) questions, "
         "MIN(timestamp) first, MAX(timestamp) last FROM runs GROUP BY 1,2,3,4 ORDER BY 1,2,3,4"),
        ("B11 resolved_model_version by requested model",
         "SELECT r.model, COALESCE(a.resolved_model_version,'<null>') returned, COUNT(*) FROM node_attempts a "
         "JOIN runs r USING(run_id) GROUP BY 1,2 ORDER BY 1,2"),
    ]
    for title, sql in checks:
        try:
            cols, rows = q(con, sql)
            rep.append(f"## {title}\n\n```sql\n{sql}\n```\n\n{md_table(cols, rows)}\n")
        except sqlite3.Error as e:
            rep.append(f"## {title}\n\nERROR: {e}\n\n```sql\n{sql}\n```\n")

    if sch.raw:
        cols, rows = q(con,
            f"SELECT a.{node} node, a.{sch.raw} raw FROM node_attempts a JOIN runs r USING(run_id) "
            f"WHERE {H} AND a.attempt_num=0")
        c = Counter()
        for n_, raw in rows:
            s = (raw or "").lstrip()
            c[(n_, "fence" if s.startswith("```") else "brace" if s[:1] in "{[" else "empty" if not s else "other")] += 1
        rep.append("## B12 Haiku first attempts: raw opener (classifier-independent)\n\n" +
                   md_table(["node", "opener", "n"], [(k[0], k[1], v) for k, v in sorted(c.items())]) + "\n")
        cols, rows = q(con,
            f"SELECT a.{pk}, a.{node}, substr(a.{sch.raw},1,160) FROM node_attempts a JOIN runs r USING(run_id) "
            f"WHERE {H} AND a.attempt_num=0 ORDER BY a.{pk} LIMIT 3")
        rep.append("### B12b three first-attempt samples (first 160 chars)\n\n" +
                   "\n".join(f"- {r[0]} {r[1]}: `{(r[2] or '').replace(chr(10), '⏎')}`" for r in rows) + "\n")
        cols, rows = q(con,
            f"SELECT a.attempt_num, COUNT(*), SUM(a.validation_ok), "
            f"SUM(ltrim(a.{sch.raw}) LIKE '```%') fenced FROM node_attempts a JOIN runs r USING(run_id) "
            f"WHERE {H} GROUP BY 1")
        rep.append("### B12c Haiku: fence rate by attempt_num (does retry feedback suppress fences?)\n\n"
                   + md_table(["attempt_num", "n", "valid", "fenced"], rows) + "\n")
    else:
        rep.append("## B12 skipped: no raw-completion column found among " + ", ".join(RAW_CANDS) + "\n")

    text = "\n".join(rep)
    Path(a.out).write_text(text)
    print(text)


# ----------------------------------------------------------------------------- counterfactual (A6)
def resolve_target(spec: str):
    """'pkg.mod:Name' or 'pkg.mod:REGISTRY.medium.identify' (getattr, then dict key, per segment)."""
    mod, _, path = spec.partition(":")
    obj = importlib.import_module(mod)
    for part in path.split("."):
        if hasattr(obj, part):
            obj = getattr(obj, part)
        elif isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            sys.exit(f"cannot resolve '{part}' in {spec}")
    if not hasattr(obj, "model_validate_json"):
        sys.exit(f"{spec} is not a pydantic v2 model")
    return obj


def parse_tier_map(spec: str) -> dict:
    return {k: resolve_target(v) for k, v in (kv.split("=", 1) for kv in spec.split(","))}


def cmd_counterfactual(a):
    sys.path.insert(0, a.pythonpath)
    con = connect_ro(Path(a.db))
    sch = resolve_schema(con)
    if not sch.raw:
        sys.exit("no raw completion column; cannot revalidate")
    tiers = {"medium": parse_tier_map(a.medium), "medium_v2": parse_tier_map(a.v2)}
    from pydantic import ValidationError

    rows = con.execute(
        f"SELECT a.{sch.attempt_pk} aid, a.{sch.node} node, a.attempt_num, a.validation_ok, a.primary_category, "
        f"a.{sch.raw} raw FROM node_attempts a JOIN runs r USING(run_id) "
        f"WHERE r.model LIKE ? AND r.schema_tier='medium' AND r.prompt_variant='baseline' AND r.dataset=?",
        (a.model + "%", a.dataset)).fetchall()

    def validate(tier, node, raw):
        cls = tiers[tier][node]
        try:
            cls.model_validate_json(raw or "")
            return True, []
        except ValidationError as e:
            return False, [(err["type"], ".".join(map(str, err["loc"]))) for err in e.errors()]

    drift, trans, v2_types, v2_cats = [], Counter(), Counter(), Counter()
    per = []
    for r in rows:
        ok_m, _ = validate("medium", r["node"], r["raw"])
        ok_v2, errs = validate("medium_v2", r["node"], r["raw"])
        if bool(ok_m) != bool(r["validation_ok"]):
            drift.append(r["aid"])
        trans[(bool(r["validation_ok"]), ok_v2)] += 1
        if not ok_v2:
            v2_cats[r["primary_category"]] += 1
            for t, loc in errs:
                v2_types[t] += 1
        per.append({"attempt": r["aid"], "node": r["node"], "orig_ok": bool(r["validation_ok"]),
                    "orig_cat": r["primary_category"], "v2_ok": ok_v2, "v2_errors": errs})

    n = len(rows)
    f_orig = sum(1 for p in per if not p["orig_ok"])
    f_v2 = sum(1 for p in per if not p["v2_ok"])
    N = Numbers()
    b = "reported"
    N.put("cf.n", n, b, "int")
    N.put("cf.orig.failures", f_orig, b, "int")
    N.put("cf.orig.rate", f_orig / n, b, "pct")
    N.put("cf.samev2.failures", f_v2, b, "int")
    N.put("cf.samev2.rate", f_v2 / n, b, "pct")
    N.put("cf.valid_to_invalid", trans[(True, False)], b, "int")
    N.put("cf.invalid_to_valid", trans[(False, True)], b, "int")
    N.put("cf.invalid_to_valid.length_bound",
          sum(1 for p in per if not p["orig_ok"] and p["v2_ok"] and p["orig_cat"] == "length_bound"), b, "int")
    N.put("cf.drift_medium", len(drift), b, "int", "stored outputs whose medium revalidation != stored validation_ok")
    N.put("cf.samev2.remaining_by_orig_cat", dict(v2_cats), b, "dict")
    N.put("cf.samev2.error_types", dict(v2_types), b, "dict")

    fresh = f"{a.fresh_failures}/{a.fresh_attempts}" if a.fresh_attempts else "see calib.medium_v2"
    rows_tex = [["Original medium outputs, medium schema", str(n), str(f_orig), pct(f_orig / n)],
                ["Same outputs, medium\\_v2 schema", str(n), str(f_v2), pct(f_v2 / n)]]
    if a.fresh_attempts:
        rows_tex.append(["Fresh medium\\_v2 generations", str(a.fresh_attempts), str(a.fresh_failures),
                         pct(a.fresh_failures / a.fresh_attempts)])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tab_counterfactual.tex").write_text(tabular("lrrr", ["Analysis", "Attempts", "Failures", "Rate \\%"], rows_tex))
    (out / "cf_numbers.json").write_text(json.dumps({"numbers": N.d, "per_attempt": per,
                                                     "drift_attempts": drift}, indent=2, default=str))
    print(json.dumps({k: v["value"] for k, v in N.d.items()}, indent=2), f"\nfresh: {fresh}")
    if drift:
        print(f"WARNING: {len(drift)} stored outputs do not reproduce their stored validation under the "
              f"current medium schema: {drift[:10]}", file=sys.stderr)
        sys.exit(3)


# ----------------------------------------------------------------------------- appcode (A12)
def extract(spec: str, root: Path) -> str:
    path, _, syms = spec.partition("::")
    src = (root / path).read_text()
    if not syms:
        return src
    tree = ast.parse(src)
    want = set(syms.split(","))
    parts = []
    for node in tree.body:
        names = set()
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names = {node.name}
        elif isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = {node.target.id}
        if names & want:
            seg = ast.get_source_segment(src, node, padded=True)
            deco = "".join(f"@{ast.get_source_segment(src, d)}\n" for d in getattr(node, "decorator_list", []))
            parts.append(deco + seg)
            want -= names
    if want:
        sys.exit(f"{path}: symbols not found: {sorted(want)}")
    return "\n\n".join(parts) + "\n"


def cmd_appcode(a):
    root = Path(a.repo)
    chunks = [f"% generated by review3.py appcode at {datetime.now(timezone.utc).isoformat()}; do not edit\n"]
    for item in a.item or []:
        label, spec = item.split("=", 1)
        body = extract(spec, root)
        chunks.append(f"\\paragraph{{{tex_esc(label)}}} (\\code{{{tex_esc(spec)}}})\n"
                      f"\\begin{{lstlisting}}[language=Python]\n{body}\\end{{lstlisting}}\n")
    for item in a.diff or []:
        label, spec = item.split("=", 1)
        left, right = spec.split("..", 1)
        diff = difflib.unified_diff(extract(left, root).splitlines(), extract(right, root).splitlines(),
                                    fromfile=left, tofile=right, lineterm="", n=2)
        chunks.append(f"\\paragraph{{{tex_esc(label)}}}\n\\begin{{lstlisting}}\n" + "\n".join(diff) + "\n\\end{lstlisting}\n")
    text = "\n".join(chunks)
    bad = sorted({ch for ch in text if ord(ch) > 127})
    if bad:
        print(f"note: non-ASCII characters in listings (add to lstset literate): {bad}", file=sys.stderr)
    Path(a.out).write_text(text)
    print(f"wrote {a.out}")


# ----------------------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("audit")
    s.add_argument("--db", required=True)
    s.add_argument("--out", default="audit_review3.md")
    s.set_defaults(fn=cmd_audit)

    s = sp.add_parser("numbers")
    s.add_argument("--db", required=True)
    s.add_argument("--out", default="paper/generated")
    s.add_argument("--repo", default=".")
    s.add_argument("--skip-golden", action="store_true", help="synthetic/test DBs only")
    s.add_argument("--track", nargs="*", default=["errors.py", "scripts/make_paper_numbers.py",
                                                  "scripts/render_paper_assets.py", "scripts/review3.py"])
    s.set_defaults(fn=cmd_numbers)

    s = sp.add_parser("derive")
    s.add_argument("--numbers", required=True)
    s.add_argument("--out", default="paper/generated/review3_derived.json")
    s.set_defaults(fn=cmd_derive)

    s = sp.add_parser("counterfactual")
    s.add_argument("--db", required=True)
    s.add_argument("--pythonpath", default=".")
    s.add_argument("--medium", required=True, help="identify=pkg.mod:Cls,gather=pkg.mod:Cls,answer=pkg.mod:Cls")
    s.add_argument("--v2", required=True, help="same form; attribute/dict paths allowed, e.g. pkg.mod:SCHEMAS.medium_v2.identify")
    s.add_argument("--model", default="claude-sonnet-4-6")
    s.add_argument("--dataset", default="hotpotqa")
    s.add_argument("--fresh-attempts", type=int)
    s.add_argument("--fresh-failures", type=int)
    s.add_argument("--out", default="paper/generated")
    s.set_defaults(fn=cmd_counterfactual)

    s = sp.add_parser("appcode")
    s.add_argument("--repo", default=".")
    s.add_argument("--item", action="append", help="Label=path[::Sym,Sym]")
    s.add_argument("--diff", action="append", help="Label=pathA[::Sym]..pathB[::Sym]")
    s.add_argument("--out", default="paper/generated/app_code.tex")
    s.set_defaults(fn=cmd_appcode)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()