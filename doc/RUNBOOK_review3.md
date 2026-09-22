# Review 3 — Section A + B runbook

`scripts/review3.py` is standalone (stdlib + numpy; pydantic only for `counterfactual`).
It opens the locked DB read-only and never writes to it. Tested end-to-end on a synthetic
DB built by `tests/make_fixture.py` with the documented schema. It has not yet been run on the real DB.

```bash
DB=results/archive/paper1_FINAL_DATA_locked_v4_20260913.db
```

## Step 1: Audit (B). Run first and paste `audit_review3.md` back
```bash
python scripts/review3.py audit --db $DB --out audit_review3.md
```
Covers the reviewer's five questions plus the manifest bug:
| Check | Answers |
|---|---|
| B0 | Full schema dump. It pins the column names that `review3.py` resolves from candidate lists (attempt PK, raw-completion column, revalidation key/outcome). |
| B1/B1b | Exactly one `attempt_num=0` per run-node |
| B2 | Your handoff query verbatim (validity × attempt_num × category, Haiku baseline) |
| B3 | attempt_num contiguous from 0 (retry numbering consistent across batches) |
| B4 | No attempt logged after a valid one (retry-only-on-failure holds) |
| B5 | Success flag agrees with category and error_details (flag is from validation, not error presence) |
| B6 | First-attempt validity for every model (Haiku is not a query artifact if others are non-zero) |
| B7 | Haiku first-attempt validity by collection date × dataset (0% uniform across batches?) |
| B8 | Haiku attempts per run-node distribution |
| B9 | `graph_success` vs answer-node validity mismatches |
| B10 | Runs per cell **by prompt_variant** (confirms 194 = 134 + 60 variant runs) |
| B11 | `resolved_model_version` per requested model (provenance input) |
| B12 | Haiku first-attempt raw opener (fence/brace), independent of the classifier; fence rate by attempt_num |

If B0 shows a column name not in the candidate lists, add it to `*_CANDS` at the top.

## Step 2: Numbers (A1–A5, A7, A8, A13, A14)
```bash
python scripts/review3.py numbers --db $DB --out paper/generated --repo .
```
Exit 2 if any hard golden check fails:
`manifest.claude-haiku-4-5@medium@hotpotqa@baseline.runs=134`, `reported.attempts=3997`,
`reported.failures=1126`, `full.attempts=4396`, `full.failures=1326`, `fence.reported.pure=327`.
The Haiku completed-run count (reviewer inferred 142) is a soft check; the DB value is reported either way.

Outputs in `paper/generated/`:
| File | Item |
|---|---|
| `review3_numbers.json` | flat keys `{value, basis, note, fmt}` |
| `tab_manifest.tex` | A1: one row per variant, unique questions, date range, exclusion reason |
| `question_manifest.csv` | A1: exact questions + sha1. **Check FinanceBench licence before releasing text.** |
| `tab_provenance.tex` | A2 |
| `tab_models.tex` | A3: bootstrap CIs replace Wilson (Wilson kept as `*.ci_wilson_ref` key only) |
| `tab_operational.tex` | A4 completion + A5 offline residual invalidity, per group + pooled |
| `tab_first_attempt.tex` | A7: valid/reached counts, after-fence counts, composition, retry success |
| `tab_domain.tex` | A8: rate, dominant, pure/wrapped by model × domain |

**Integration** (make_paper_numbers.py, before emitting numbers.tex/keys.txt):
```python
r3 = json.loads((GEN / "review3_numbers.json").read_text())["numbers"]
numbers.update({k: v for k, v in r3.items() if v["fmt"] not in ("list", "dict")})
numbers["manifest"] = r3["manifest"]   # same field names as before + questions/dates/variant
```
Key namespaces: `g.<model>@<tier>.*`, `c.<model>@<tier>@<domain>.*`, `pooled.reported.*`,
`manifest.*`, `prov.*`, `robust.*`, `meta.*`. **`g.*.ci` and `g.*.dominant_ci` are now bootstrap**,
so the "(Wilson …)" wording in §3.3 and §4.2 must change to "(question-clustered bootstrap …)".
`fmt` hints: `int`, `pct`, `ci_pct`, `pp`, `f2`, `str`. Map them in your existing formatter.

**A2 caveat:** route, temperature, and max_tokens come from `CLIENT_CONFIG` (top of file, transcribed from §3.2).
Confirm them against the two client branches. Everything else is from the DB.

## Step 3: Derived (A9, A10). Already run on the uploaded JSON
```bash
python scripts/review3.py derive --numbers paper/generated/paper_numbers.json
```
Results (`review3_derived.json`):
- `pert.pooled`: **18 failures / 17 regex / 19 identifiers**, multilabel, 0 multi-subcause.
- `divergence.unrestricted.max`: 97.49 pp, `regex_pattern`, **tied across 2 pairs**: Haiku@medium vs sol@v3 and Haiku@medium vs terra@v3.
- `divergence.top.n_tied = 4`: the 72.89 pp restricted max is a 4-way tie, all Haiku vs a zero-wrap group. §4.2 currently says "the largest difference between two groups." That wording should acknowledge the tie.

## Step 4: Counterfactual (A6)
```bash
python scripts/review3.py counterfactual --db $DB --pythonpath . \
  --medium-module <schemas.medium> --v2-module <schemas.medium_v2> \
  --node-map identify=<Cls>,gather=<Cls>,answer=<Cls> \
  --fresh-attempts 324 --fresh-failures 24
```
- Revalidates all 178 stored outputs (valid and failed) under **both** medium and v2.
- **Drift guard:** exit 3 if medium revalidation doesn't reproduce stored `validation_ok`. This catches schema edits made since collection, or validators that need context.
- Emits a transition matrix (valid→invalid must be 0) and `tab_counterfactual.tex` (3 rows).

## Step 5: Appendix code (A12)
```bash
python scripts/review3.py appcode --repo . \
  --item "Medium schemas=schemas/medium.py" \
  --diff "medium_v2 changes=schemas/medium.py..schemas/medium_v2.py" \
  --diff "medium_v3 changes=schemas/medium.py..schemas/medium_v3.py" \
  --item "Prompts=prompts.py" --item "Retry message=<file>::<SYMBOL>" \
  --item "Stage-1 predicates=errors.py::<fn>,<fn>"
```
`path::A,B` extracts top-level classes, functions, or assignments via `ast`, so tiers defined in one module still diff cleanly.
Non-ASCII in sources is reported so you can extend `\lstset{literate=…}`.

## A11 figure (render_paper_assets.py not uploaded). Patch
```python
for bar, g in zip(bars, groups):   # bars = outermost stacked segment per group
    ax.annotate(f"n_fail={g['failures']}, {100*g['rate']:.1f}%",
                (bar.get_x() + bar.get_width(), bar.get_y() + bar.get_height()/2),
                xytext=(3, 0), textcoords="offset points", va="center", fontsize=6)
```

## A13 / A14
- `meta.git_head`, `meta.git_tag`, `meta.tracked` (per-file last commit + dirty flag), and `meta.db_sha256` are all recorded. Tag the commit before the final run.
- Earliest-run rule is recorded as `robust.one_run.rule`: minimum `runs.timestamp`, ties broken by `run_id`, per cell × question.
- `robust.dedup_all.delta_pp` is the pooled-rate change for the "repeated questions" sentence.

## Already reconciled from the uploaded JSON (no DB needed)
- Full corpus: 4,396 = 3,997 reported + 34 pilot (gpt-4o-mini FB 28, luna v3 6) + 365 variant (189 + 176).
- Failures: 1,326 = 1,126 + 13 + 0 + 99 + 88.
- 194 − 134 = 60 variant runs in the Haiku HotpotQA cell.
- Reviewer's residual figures, to be confirmed by `tab_operational`: pooled 20.0%, Haiku 44.2%, Sonnet 5 9.6%.