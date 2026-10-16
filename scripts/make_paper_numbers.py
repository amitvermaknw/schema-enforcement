#!/usr/bin/env python3
"""
Single source of truth for every number in Paper #1.

Reads ONLY the locked DB (read-only URI). Writes paper/generated/paper_numbers.json.
Every value carries a basis tag so no number can be quoted on the wrong denominator.

    python scripts/make_paper_numbers.py      (run from repo root; needs src/ importable)

Bases
  reported : cells with >=30 runs, prompt_variant='baseline'   -> all main-text numbers
  full     : every attempt in the DB                           -> classifier-validation frame only
  ablation : haiku x medium x hotpotqa, all prompt variants    -> prompt ablation only
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")

DB = Path("results/archive/paper1_FINAL_DATA_locked_v4_20260913.db")
OUT = Path("paper/generated/paper_numbers.json")

ATTEMPTS_SQL = """
SELECT a.id, a.run_id AS run, r.model, r.schema_tier AS tier, r.dataset AS domain,
       a.node_name AS node, a.attempt_num, r.prompt_variant AS variant, r.question,
       r.timestamp, a.validation_ok AS valid, a.primary_category AS cat,
       a.raw_output AS raw, a.error_details AS err, a.output_tokens,
       a.resolved_model_version AS resolved
FROM node_attempts a JOIN runs r USING (run_id)
"""
RUNS_SQL = "SELECT run_id AS run, model, schema_tier AS tier, dataset AS domain FROM runs"
LABELS_SQL = "SELECT attempt_id, classifier_label, ground_truth, notes FROM hand_labels"
REVAL_SQL = "SELECT attempt_id, outcome, compound_category FROM markdown_wrap_revalidation"

# ---- set from diagnostics (2026-09-14) ------------------------------------
# hand_labels.ground_truth holds the ADJUDICATED label; blind labels are recovered
# from the CORRECTED notes and must equal this dict (asserted).
HUMAN_ERRORS = {
    987: ("enum_violation", "regex_pattern"),
    2817: ("enum_violation", "regex_pattern"),
    2833: ("enum_violation", "regex_pattern"),
    1208: ("markdown_wrap", "prose_preamble"),
}
PURE_OUTCOMES = {"pure_formatting"}
VALIDATOR_MESSAGES = [                   # cross-field checks (constant f-string fragments)
    "' not in entities canonical_ids",  # identify: primary_entity_id membership
    "!= len(entities)=",                # identify: entity_count
    "!= len(facts)=",                   # gather: fact_count
    " implies bucket='",                # answer: confidence_bucket
]
MODEL_LEVEL_MESSAGES = ["' fails canonical_id pattern '"]  # answer: supporting IDs (not cross-field)
# ---------------------------------------------------------------------------

MIN_RUNS = 30
HAIKU = "claude-haiku-4-5"
SONNET46 = "claude-sonnet-4-6"
G_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra")
EXPECTED_PILOTS = {
    ("gpt-4o-mini", "medium", "financebench"),
    ("gpt-5.6-luna", "medium_v3_loose_regex", "hotpotqa"),
}
ID_CLASSES = {  # tier -> (first-char class, body class)
    "medium": ("a-z", "a-z0-9_"),
    "medium_v3_loose_regex": ("a-zA-Z0-9", "a-zA-Z0-9_\\-"),
}

# Verified in prior rounds. Mismatch => fix the code, never the golden value.
GOLDEN = {
    "full.cells": 20, "reported.cells": 18, "full.failures": 1326,
    "reported.attempts": 3997, "reported.failures": 1126,
    "reported.cat.markdown_wrap": 681, "reported.cat.length_bound": 263,
    "reported.cat.regex_pattern": 126, "reported.cat.schema_mirroring": 38,
    "reported.cat.prose_preamble": 9, "reported.cat.enum_violation": 8,
    "reported.cat.parse_error": 1,
    "ablation.baseline.attempts": 1066, "ablation.aggressive.attempts": 189,
    "ablation.few_shot.attempts": 176,
    "fence.table.rows": 789, "fence.table.missing_rows": 0,
    "fence.reported.pure": 327, "fence.reported.compound": 354,
    "reported.length_bound_incl_concealed": 590,
    "validation.n": 144, "validation.blind_agree": 140,
    "crossfield.violations": 0, "modellevel.violations": 4,
    "crossfield.value_errors_unmatched": 0,
    "calib.field.unparsed": 0,
    "calib.medium.length_bound": 18, "calib.medium_v2.length_bound": 0,
    "calib.counterfactual_pass": 18,
    "pert.medium.identifiers": 8, "pert.medium_v3_loose_regex.identifiers": 11,
    "pert.medium.leading_digit": 4, "pert.medium.length_overflow": 4,
    "pert.medium_v3_loose_regex.length_overflow": 10,
    "pert.medium_v3_loose_regex.unicode": 1,
    "divergence.groups_qualifying": 6, "divergence.pairs": 15,
    "zero_length.n": 1,
    "screen.fence_any.matches": 790, "screen.fence_any.markdown_wrap": 789,
    "screen.properties.matches": 42, "screen.properties.schema_mirroring": 42,
}

N: dict[str, dict] = {}


def put(key, value, basis, note=""):
    if isinstance(value, float):
        value = round(value, 6)
    N[key] = {"value": value, "basis": basis, "note": note}


def wilson(k, n, z=1.959964):
    if n == 0:
        return [float("nan")] * 2
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


CAP_RE = re.compile(r"at most (\d+) character")
NOTE_BLIND_RE = re.compile(r"labeled (?:as )?([a-z_]+)")
SUPPORT_ID_RE = re.compile(r"supporting_entity_id '(.*?)' fails canonical_id pattern")


def walk(doc, loc: str):
    """Follow a dotted Pydantic loc ('facts.2.fact') into parsed JSON."""
    cur = doc
    for part in str(loc).split("."):
        if isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def jloads(s):
    try:
        return json.loads(s) if s else None
    except (TypeError, json.JSONDecodeError):
        return None


def node_model(tier: str, node: str):
    from schemaeval.schemas import medium, medium_v2, medium_v3_loose_regex
    mod = {"medium": medium, "medium_v2": medium_v2,
           "medium_v3_loose_regex": medium_v3_loose_regex}[tier]
    return {"identify": mod.IdentifyOutput, "gather": mod.GatherOutput,
            "answer": mod.AnswerOutput}[node]


def load():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    df = pd.read_sql(ATTEMPTS_SQL, con)
    runs = pd.read_sql(RUNS_SQL, con)
    labels = pd.read_sql(LABELS_SQL, con)
    reval = pd.read_sql(REVAL_SQL, con)
    con.close()
    for d in (df, runs):
        d["model"] = d["model"].str.replace(r"-\d{8}$", "", regex=True)
    df["failed"] = df["valid"] == 0
    df["is_first"] = df["attempt_num"] == df.groupby(["run", "node"])["attempt_num"].transform("min")
    return df, runs, labels, reval


def split(df, runs):
    per_cell = runs.groupby(["model", "tier", "domain"])["run"].nunique()
    pilots = set(per_cell[per_cell < MIN_RUNS].index)
    assert pilots == EXPECTED_PILOTS, f"pilot set changed: {pilots}"
    cell = pd.MultiIndex.from_frame(df[["model", "tier", "domain"]])
    in_pilot = pd.Series(cell.isin(list(pilots)), index=df.index)
    rep = df[(df.variant == "baseline") & ~in_pilot]
    ab = df[(df.model == HAIKU) & (df.tier == "medium") & (df.domain == "hotpotqa")]
    return rep, ab, per_cell, pilots


def summarize(frame, keys):
    rows = []
    for k, g in frame.groupby(keys):
        k = k if isinstance(k, tuple) else (k,)
        a, f, r = len(g), int(g.failed.sum()), g.run.nunique()
        comp = g.loc[g.failed, "cat"].value_counts()
        rows.append({**dict(zip(keys, k)), "attempts": a, "failures": f, "rate": f / a,
                     "ci": wilson(f, a), "runs": int(r), "attempts_per_run": a / r,
                     "dominant": comp.index[0] if f else None,
                     "dominant_share": float(comp.iloc[0] / f) if f else None,
                     "dominant_ci": wilson(int(comp.iloc[0]), f) if f else None,
                     "composition": {c: int(v) for c, v in comp.items()}})
    return rows


# ---------------------------------------------------------------------------
def s_corpus(df, rep, per_cell, pilots):
    for name, d in (("reported", rep), ("full", df)):
        a, f = len(d), int(d.failed.sum())
        put(f"{name}.attempts", a, name)
        put(f"{name}.failures", f, name)
        put(f"{name}.rate", f / a, name)
        put(f"{name}.cells", d.groupby(["model", "tier", "domain"]).ngroups, name)
    put("reported.models", int(rep.model.nunique()), "reported")
    put("reported.categories_observed", int(rep.loc[rep.failed, "cat"].nunique()), "reported")
    for c, n in rep.loc[rep.failed, "cat"].value_counts().items():
        put(f"reported.cat.{c}", int(n), "reported")
    manifest = []
    for (m, t, d), r in per_cell.items():
        g = df[(df.model == m) & (df.tier == t) & (df.domain == d) & (df.variant == "baseline")]
        manifest.append(dict(model=m, tier=t, domain=d, runs=int(r), attempts=len(g),
                             failures=int(g.failed.sum()), excluded=(m, t, d) in pilots))
    put("manifest", manifest, "full", "baseline prompt; excluded = pilot")
    nh = rep[rep.model != HAIKU]
    put("reported.exhaiku.attempts", len(nh), "reported")
    put("reported.exhaiku.failures", int(nh.failed.sum()), "reported")
    put("reported.exhaiku.rate", float(nh.failed.mean()), "reported")
    put("reported.haiku.failures", int(rep[rep.model == HAIKU].failed.sum()), "reported")


def s_groups(rep):
    groups = summarize(rep, ["model", "tier"])
    put("groups", groups, "reported", "model@tier, pooled over domains")
    med = sorted(g["rate"] for g in groups if g["tier"] == "medium")
    put("reported.medium.macro_rate", sum(med) / len(med), "reported", "unweighted mean over models")
    put("reported.medium.median_rate", med[len(med) // 2], "reported")
    put("cells", summarize(rep, ["model", "tier", "domain"]), "reported", "per-domain")
    put("models", summarize(rep, ["model"]), "reported", "all tiers pooled")
    return groups


def s_first_attempt(rep):
    rows = []
    for (m, t, n), g in rep[rep.is_first].groupby(["model", "tier", "node"]):
        rows.append(dict(model=m, tier=t, node=n, reached=len(g),
                         first_attempt_valid=float((~g.failed).mean()),
                         composition={c: int(v) for c, v in g.loc[g.failed, "cat"].value_counts().items()}))
    put("first_attempt_by_node", rows, "reported", "denominator = runs that reached the node")


def s_ablation(ab):
    for v, g in ab.groupby("variant"):
        put(f"ablation.{v}.attempts", len(g), "ablation")
        put(f"ablation.{v}.failures", int(g.failed.sum()), "ablation")
        put(f"ablation.{v}.failure_rate", float(g.failed.mean()), "ablation")
        for c in ("markdown_wrap", "length_bound", "regex_pattern"):
            put(f"ablation.{v}.{c}", float((g.failed & (g.cat == c)).mean()), "ablation")
            put(f"ablation.{v}.{c}_n", int((g.failed & (g.cat == c)).sum()), "ablation")
    b, f = N["ablation.baseline.markdown_wrap"]["value"], N["ablation.few_shot.markdown_wrap"]["value"]
    put("ablation.delta.markdown_wrap_pp", 100 * (b - f), "ablation")
    put("ablation.delta.markdown_wrap_rel", (b - f) / b, "ablation")
    b, f = N["ablation.baseline.failure_rate"]["value"], N["ablation.few_shot.failure_rate"]["value"]
    put("ablation.delta.failure_rate_pp", 100 * (b - f), "ablation")


def s_fence(df, rep, ab, reval):
    put("fence.table.rows", len(reval), "full")
    put("fence.table.outcomes", {str(k): int(v) for k, v in reval.outcome.value_counts(dropna=False).items()}, "full")
    rv = reval.set_index("attempt_id")
    mw_full = df[df.failed & (df.cat == "markdown_wrap")]
    put("fence.table.missing_rows", len(set(mw_full.id) - set(rv.index)), "full")

    def pure(i):
        return rv.at[i, "outcome"] in PURE_OUTCOMES

    def concealed(i):
        return set() if i not in rv.index or pure(i) else {str(rv.at[i, "compound_category"])}

    mw = rep[rep.failed & (rep.cat == "markdown_wrap")]
    for model, g in list(mw.groupby("model")) + [("reported", mw)]:
        ids = list(g.id)
        n_c = sum(not pure(i) for i in ids)
        put(f"fence.{model}.n", len(ids), "reported")
        put(f"fence.{model}.pure", len(ids) - n_c, "reported")
        put(f"fence.{model}.compound", n_c, "reported")
        put(f"fence.{model}.pure_share", (len(ids) - n_c) / len(ids), "reported")
        put(f"fence.{model}.compound_share", n_c / len(ids), "reported")
        put(f"fence.{model}.compound_ci", wilson(n_c, len(ids)), "reported")
        for c, n in Counter(x for i in ids for x in concealed(i)).items():
            put(f"fence.{model}.concealed.{c}", n, "reported")
        put(f"fence.{model}.concealed_length_share",
            sum("length_bound" in concealed(i) for i in ids) / len(ids), "reported")
    put("reported.length_bound_incl_concealed",
        N["reported.cat.length_bound"]["value"] + N.get("fence.reported.concealed.length_bound", {"value": 0})["value"],
        "reported")
    for v, g in ab.groupby("variant"):
        lb = int((g.failed & (g.cat == "length_bound")).sum())
        conc = sum("length_bound" in concealed(i) for i in g.id)
        put(f"ablation.{v}.length_bound_incl_concealed", (lb + conc) / len(g), "ablation")


def s_calibration(rep):
    s = rep[rep.model == SONNET46]
    for t in ("medium", "medium_v2"):
        g = s[s.tier == t]
        put(f"calib.{t}.attempts", len(g), "reported")
        put(f"calib.{t}.failures", int(g.failed.sum()), "reported")
        put(f"calib.{t}.rate", float(g.failed.mean()), "reported")
        for c in ("length_bound", "regex_pattern", "prose_preamble", "enum_violation"):
            put(f"calib.{t}.{c}", int((g.failed & (g.cat == c)).sum()), "reported")

    lb = s[(s.tier == "medium") & s.failed & (s.cat == "length_bound")]
    fields: dict[str, list] = {}
    unparsed = 0
    for r in lb.itertuples():
        errs, doc = jloads(r.err), jloads(r.raw)
        if not isinstance(errs, list) or doc is None:
            unparsed += 1
            continue
        for e in errs:
            if e.get("type") != "string_too_long":
                continue
            m, val = CAP_RE.search(e.get("msg", "")), walk(doc, e.get("loc", ""))
            if not (m and isinstance(val, str)):
                unparsed += 1
                continue
            parts = [p for p in str(e["loc"]).split(".") if not p.isdigit()]
            fields.setdefault(parts[-1], []).append((len(val), int(m.group(1))))
    put("calib.field.unparsed", unparsed, "reported", "must be 0")
    for f, xs in fields.items():
        over = [(n - c) / c for n, c in xs]
        put(f"calib.field.{f}", dict(n=len(xs), min=min(n for n, _ in xs), max=max(n for n, _ in xs),
                                     cap=xs[0][1], mean_overrun=sum(over) / len(over),
                                     max_overrun=max(over)), "reported", "sonnet-4-6 @ medium")

    from pydantic import ValidationError
    passes = 0
    for r in lb.itertuples():
        try:
            node_model("medium_v2", r.node).model_validate_json(r.raw or "")
            passes += 1
        except ValidationError:
            pass
    put("calib.counterfactual_pass", passes, "reported", f"of {len(lb)} stored medium length_bound failures")


def subcauses(ident: str, tier: str) -> list[str]:
    first, body = ID_CLASSES[tier]
    out = []
    if any(ord(ch) > 127 for ch in ident):
        out.append("unicode")
    if ident[:1].isdigit() and not re.match(f"[{first}]", ident[:1]):
        out.append("leading_digit")
    if re.search(f"[^{body}]", ident.encode("ascii", "ignore").decode()):
        out.append("invalid_char")
    if not 3 <= len(ident) <= 31:
        out.append("length_overflow")
    return out or ["other"]


def s_perturbation(rep):
    for tier in ("medium", "medium_v3_loose_regex"):
        g = rep[rep.model.isin(G_MODELS) & (rep.tier == tier) & (rep.domain == "hotpotqa")]
        rp = g[g.failed & (g.cat == "regex_pattern")]
        causes, multi, examples, unparsed = Counter(), 0, [], 0
        for r in rp.itertuples():
            errs, doc = jloads(r.err), jloads(r.raw)
            idents = []
            for e in errs if isinstance(errs, list) else []:
                if e.get("type") == "string_pattern_mismatch":
                    v = walk(doc, e.get("loc", "")) if doc is not None else None
                    if isinstance(v, str):
                        idents.append(v)
                    else:
                        unparsed += 1
                elif e.get("type") == "value_error" and (m := SUPPORT_ID_RE.search(e.get("msg", ""))):
                    idents.append(m.group(1))
            for ident in idents:
                sc = subcauses(ident, tier)
                multi += len(sc) > 1
                causes.update(sc)
                examples.append(dict(attempt=int(r.id), model=r.model, identifier=ident,
                                     length=len(ident), subcauses=sc))
        put(f"pert.{tier}.failures", int(g.failed.sum()), "reported")
        put(f"pert.{tier}.regex_failures", len(rp), "reported")
        put(f"pert.{tier}.identifiers", len(examples), "reported")
        put(f"pert.{tier}.multi_subcause", multi, "reported")
        put(f"pert.{tier}.unparsed", unparsed, "reported")
        for c in ("leading_digit", "length_overflow", "unicode", "invalid_char", "other"):
            put(f"pert.{tier}.{c}", causes.get(c, 0), "reported")
        put(f"pert.{tier}.examples", examples, "reported")
        for m in G_MODELS:
            gm = g[g.model == m]
            put(f"pert.{tier}.{m}.attempts", len(gm), "reported")
            put(f"pert.{tier}.{m}.failures", int(gm.failed.sum()), "reported")


def s_robustness(rep):
    h = rep[(rep.model == HAIKU) & (rep.tier == "medium") & (rep.domain == "hotpotqa")]
    rq = h.groupby("run").agg(question=("question", "first"), ts=("timestamp", "min")).reset_index()
    first_runs = rq.sort_values("ts").groupby("question")["run"].first()
    one = h[h.run.isin(first_runs)]
    put("robust.cell.attempts", len(h), "reported")
    put("robust.cell.failures", int(h.failed.sum()), "reported")
    put("robust.cell.rate", float(h.failed.mean()), "reported")
    put("robust.cell.runs", int(h.run.nunique()), "reported")
    put("robust.cell.questions", int(h.question.nunique()), "reported")
    put("robust.cell.runs_per_question", {str(k): int(v) for k, v in rq.question.value_counts().value_counts().items()}, "reported")
    put("robust.one_run.attempts", len(one), "reported")
    put("robust.one_run.failures", int(one.failed.sum()), "reported")
    put("robust.one_run.rate", float(one.failed.mean()), "reported")


def s_matched(rep):
    """Matched cross-model basis: HotpotQA medium-tier cells share one question set."""
    m = rep[(rep.tier == "medium") & (rep.domain == "hotpotqa")]
    qsets = m.groupby("model")["question"].agg(frozenset)
    shared = frozenset.intersection(*qsets)
    union = frozenset.union(*qsets)
    assert shared == union, (
        f"HotpotQA medium cells do not share one question set: "
        f"shared={len(shared)} union={len(union)} per-model={qsets.map(len).to_dict()}")
    put("matched.hotpotqa_medium.models", int(len(qsets)), "reported")
    put("matched.hotpotqa_medium.shared_questions", int(len(shared)), "reported")
    put("matched.hotpotqa_medium.union_questions", int(len(union)), "reported")


def s_validation(df, labels):
    lab = labels.merge(df[["id", "cat"]], left_on="attempt_id", right_on="id")
    recovered = {}
    for r in lab[lab.notes.fillna("").str.contains("CORRECTED")].itertuples():
        m = NOTE_BLIND_RE.search(r.notes)
        recovered[int(r.attempt_id)] = (m.group(1) if m else None, r.ground_truth)
    assert recovered == HUMAN_ERRORS, f"notes disagree with HUMAN_ERRORS: {recovered}"
    lab["blind"] = [recovered.get(i, (g, g))[0] for i, g in zip(lab.attempt_id, lab.ground_truth)]
    note = "frame = all failures in DB (incl. pilot cells and prompt variants)"
    n, k = len(lab), int((lab.cat == lab.blind).sum())
    put("validation.n", n, "full", note)
    put("validation.blind_agree", k, "full", note)
    put("validation.blind_rate", k / n, "full", note)
    put("validation.blind_ci", wilson(k, n), "full", note)
    put("validation.adjudicated_agree", int((lab.cat == lab.ground_truth).sum()), "full", note)
    put("validation.classifier_label_stale", int((lab.classifier_label != lab.cat).sum()), "full", "expect 0")
    for c in sorted(set(lab.cat) | set(lab.blind.dropna())):
        put(f"validation.cat.{c}", dict(tp=int(((lab.cat == c) & (lab.blind == c)).sum()),
                                        predicted=int((lab.cat == c).sum()),
                                        human=int((lab.blind == c).sum())),
            "full", "against blind human labels (pre-adjudication)")


def s_cross_field(rep):
    err = rep.err.fillna("")
    cross = err.apply(lambda s: any(m in s for m in VALIDATOR_MESSAGES))
    model_level = err.apply(lambda s: any(m in s for m in MODEL_LEVEL_MESSAGES))
    value_err = err.str.contains('"type": "value_error"', regex=False)
    put("crossfield.validated", int((~rep.failed).sum()), "reported")
    put("crossfield.violations", int((rep.failed & cross).sum()), "reported")
    put("modellevel.violations", int((rep.failed & model_level).sum()), "reported")
    put("crossfield.reached", int((~rep.failed).sum() + (rep.failed & model_level).sum()), "reported")
    put("crossfield.not_reached", int((rep.failed & ~model_level & ~cross).sum()), "reported")
    put("crossfield.value_errors_unmatched", int((rep.failed & value_err & ~cross & ~model_level).sum()), "reported")


def s_tier2(rep):
    # Tier 2. F1: Haiku 4.5 run-nodes with no valid attempt -- does the fence-stripped first
    # attempt carry the same length violation as the final one, and what did the returned
    # error of each fenced attempt say? F2: sensitivity to the supporting-identifier check,
    # the one enforced constraint absent from the prompt (Table 14).
    from pydantic import ValidationError
    from schemaeval.errors import _strip_code_fences
    FENCE = "`" * 3
    LEN = ("string_too_long", "too_long")
    b = "reported"

    def len_locs(node, raw):
        try:
            node_model("medium", node).model_validate_json(_strip_code_fences(raw or ""))
            return set()
        except ValidationError as e:
            return {(".".join(map(str, d["loc"])), d["type"]) for d in e.errors() if d["type"] in LEN}

    h = rep[(rep.model == HAIKU) & (rep.tier == "medium")]
    ex = h[h.groupby(["run", "node"])["valid"].transform("max") == 0]
    ex = ex.sort_values(["run", "node", "attempt_num"])
    by_node, fb = Counter(), Counter()
    n_same = n_persist = n_fenced = n_jinv = n_flen = 0
    for (run, node), g in ex.groupby(["run", "node"], sort=False):
        lens = [len_locs(node, r) for r in g.raw]
        by_node[node] += 1
        n_same += bool(lens[0] & lens[-1])
        n_persist += bool(set.intersection(*lens))
        raws, errs = g.raw.fillna("").tolist(), g.err.fillna("").tolist()
        k = 0
        for i, (raw, err) in enumerate(zip(raws, errs)):
            if raw.lstrip().startswith(FENCE):
                n_fenced += 1
                n_jinv += "json_invalid" in err
                n_flen += any(t in err for t in LEN)
            if i < len(errs) - 1 and any(t in err for t in LEN):
                k += 1
        fb[k] += 1
    put("conceal.exh.n", sum(by_node.values()), b, "Haiku 4.5 medium run-nodes with no valid attempt")
    put("conceal.exh.gather", by_node["gather"], b)
    put("conceal.exh.answer", by_node["answer"], b)
    put("conceal.exh.same_field", n_same, b, "fence-stripped attempt 0 and final attempt share a length loc")
    put("conceal.exh.persist", n_persist, b, "same length loc violated on every attempt")
    put("conceal.exh.fenced", n_fenced, b)
    put("conceal.exh.fenced_json_invalid", n_jinv, b, "returned error of a fenced attempt is json_invalid")
    put("conceal.exh.fenced_len_in_error", n_flen, b)
    put("conceal.exh.len_feedback", {str(k): v for k, v in sorted(fb.items())}, b,
        "run-nodes by number of returned retry errors naming a length violation")
    put("conceal.exh.len_feedback_once", fb[1], b)
    put("conceal.exh.len_feedback_twice", fb[2], b)

    fails = rep[rep.failed]
    hid = fails.err.fillna("").str.contains("fails canonical_id pattern", regex=False)
    kept = fails[~hid]
    put("hidden.n", int(hid.sum()), b, "failures from the supporting-identifier check")
    top = lambda s: Counter(s).most_common(1)[0][0] if len(s) else None
    for label, keys in (("cells", ["model", "tier", "domain"]), ("groups", ["model", "tier"])):
        full = fails.groupby(keys)["cat"].agg(top)
        red = kept.groupby(keys)["cat"].agg(top).reindex(full.index)
        put(f"hidden.flips.{label}", int((full != red).sum()), b,
            "dominant-category changes when hidden-constraint failures are excluded")
    g = kept[(kept.model == "gpt-4o-mini") & (kept.tier == "medium")]
    put("hidden.gpt4omini.n_without", len(g), b)
    put("hidden.gpt4omini.regex_without", int((g.cat == "regex_pattern").sum()), b)
    put("hidden.gpt4omini.share_without", float((g.cat == "regex_pattern").mean()), b)
    put("hidden.regex_pattern_without", int((kept.cat == "regex_pattern").sum()), b)
    hid_ids = set(fails[hid].id)
    exr = rep[rep.groupby(["run", "node"])["valid"].transform("max") == 0]
    hrn = [g2 for _, g2 in exr.groupby(["run", "node"]) if g2.id.isin(hid_ids).any()]
    put("hidden.exhausted_runnodes", len(hrn), b)
    put("hidden.exhausted_attempts", int(sum(g2.id.isin(hid_ids).sum() for g2 in hrn)), b)


def s_screens(df):
    """Over-broad corpus recall screens on the full basis (Appendix C)."""
    f = df[df.failed].copy()
    raw = f.raw.fillna("")
    fence_any = raw.str.contains("```", regex=False)
    put("screen.fence_any.matches", int(fence_any.sum()), "full")
    put("screen.fence_any.markdown_wrap", int((fence_any & (f.cat == "markdown_wrap")).sum()), "full")
    put("screen.fence_any.prose_preamble", int((fence_any & (f.cat == "prose_preamble")).sum()), "full")
    props = raw.str.contains('"properties"', regex=False)
    put("screen.properties.matches", int(props.sum()), "full")
    put("screen.properties.schema_mirroring", int((props & (f.cat == "schema_mirroring")).sum()), "full")
    head = raw.str.lstrip()
    opener = (head.str.len() > 0) & ~head.str[:1].isin(["{", "["]) & ~head.str.startswith("```")
    put("screen.nonjson_opener.matches", int(opener.sum()), "full")
    put("screen.nonjson_opener.prose_preamble", int((opener & (f.cat == "prose_preamble")).sum()), "full")
    put("screen.empty.matches", int((head.str.len() == 0).sum()), "full")


def s_zero_length(rep):
    z = rep[rep.failed & (rep.raw.fillna("").str.len() == 0)]
    put("zero_length.n", len(z), "reported")
    if len(z):
        r = z.iloc[0]
        put("zero_length.output_tokens", int(r.output_tokens), "reported")
        put("zero_length.model", r.model, "reported")
        put("zero_length.node", r.node, "reported")
        put("zero_length.attempt", int(r.id), "reported")


def s_versions(rep):
    for m in ("gpt-4o", "gpt-4o-mini"):
        g = rep[rep.model == m]
        put(f"versions.{m}.precapture", int(g.resolved.isna().sum()), "reported")
        put(f"versions.{m}.attempts", len(g), "reported")
        put(f"versions.{m}.resolved", g.resolved.dropna().value_counts().to_dict(), "reported")


def divergence(groups, min_fail):
    q = [g for g in groups if g["failures"] >= min_fail]
    pairs = []
    for i, a in enumerate(q):
        for b in q[i + 1:]:
            for c in set(a["composition"]) | set(b["composition"]):
                d = abs(a["composition"].get(c, 0) / a["failures"] - b["composition"].get(c, 0) / b["failures"])
                pairs.append(dict(pp=100 * d, category=c,
                                  a=f'{a["model"]}@{a["tier"]}', b=f'{b["model"]}@{b["tier"]}'))
    pairs.sort(key=lambda p: -p["pp"])
    return q, pairs


def s_divergence(groups):
    q, pairs = divergence(groups, 20)
    put("divergence.groups_total", sum(g["failures"] > 0 for g in groups), "reported")
    put("divergence.groups_qualifying", len(q), "reported", ">= 20 failures")
    put("divergence.pairs", len(q) * (len(q) - 1) // 2, "reported")
    put("divergence.top", pairs[:12], "reported")
    other = next((p for p in pairs if p["category"] != pairs[0]["category"]), None)
    if other:
        put("divergence.runner_up_category_pp", other["pp"], "reported")
        put("divergence.gap_pp", pairs[0]["pp"] - other["pp"], "reported")
    _, allp = divergence(groups, 1)
    put("divergence.unrestricted.top", allp[:3], "reported")


def main() -> int:
    df, runs, labels, reval = load()
    rep, ab, per_cell, pilots = split(df, runs)
    s_corpus(df, rep, per_cell, pilots)
    groups = s_groups(rep)
    s_first_attempt(rep)
    s_ablation(ab)
    s_fence(df, rep, ab, reval)
    s_calibration(rep)
    s_perturbation(rep)
    s_robustness(rep)
    s_matched(rep)
    s_validation(df, labels)
    s_cross_field(rep)
    s_tier2(rep)
    s_zero_length(rep)
    s_screens(df)
    s_versions(rep)
    s_divergence(groups)

    meta = {"db": str(DB), "sha256": hashlib.sha256(DB.read_bytes()).hexdigest(),
            "generated_utc": datetime.now(timezone.utc).isoformat()}

    for _name in ("review3_numbers.json", "cf_numbers.json", "review3_derived.json"):
        _p = OUT.parent / _name
        if not _p.exists():
            print(f"merge: {_name} missing, skipped", file=sys.stderr)
            continue
        _extra = json.loads(_p.read_text())["numbers"]
        N.update(_extra)
        print(f"merge: {_name} -> {len(_extra)} records", file=sys.stderr)
        
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"meta": meta, "numbers": N}, indent=2, default=float, ensure_ascii=False))

    bad = [(k, v, N.get(k, {}).get("value")) for k, v in GOLDEN.items() if N.get(k, {}).get("value") != v]
    for k, want, got in bad:
        print(f"GOLDEN MISMATCH {k}: expected {want}, got {got}", file=sys.stderr)
    print(f"wrote {len(N)} numbers -> {OUT}  ({'FAIL' if bad else 'golden OK'})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
