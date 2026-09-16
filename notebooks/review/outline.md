# Paper #1 — 8-page plan (main text ≤ 8 pp, target 7.25)

## One-sentence thesis
Under prompt-enforced Pydantic schemas, *what* fails is more model-specific than *how often*; that
composition is a joint property of model and constraint surface; and the most common failure
(markdown fencing) conceals a content violation in about half of cases, so fence-stripping is not a fix.

## Three contributions (the only three)
1. An observed failure taxonomy (7 of 11 defined categories), with a classifier validated at
   `\pn{validation.blind_rate}` blind agreement (development-set, stated as such).
2. Dominant-category profiles across 9 models / 2 vendors that shift with the constraint surface
   (Sonnet 4.6 flip under medium_v2, fully mechanical by counterfactual revalidation).
3. Formatting failures conceal content failures: fence-strip revalidation + prompt-ablation precedence effect.

## Page budget
| § | Section | pp | Contents | Assets |
|---|---|---|---|---|
| 1 | Introduction | 0.75 | Motivating identifier example **from a reported cell** (Sol/Terra leading digit), thesis, 3 contributions | — |
| 2 | Related work | 0.5 | Constrained decoding / tool forcing stated as out of scope **once, only here**; JSON benchmarks; ParaConsist | — |
| 3 | Setup | 1.25 | Paradigm + 3-node harness; models, tiers, domains (manifest → App A); taxonomy; classifier validation in one paragraph | Fig 1 (harness, small) |
| 4.1 | Rates and composition | 1.0 | Per-model table; pooled rate reported **with** ex-Haiku and macro rate | Tab 1 `tab_models`, Tab 2 `tab_categories` |
| 4.2 | Dominant-category profiles | 0.75 | Four observed profiles; vendor/generation observations phrased as "not observed in configurations tested" | Fig 2 `fig_profiles` |
| 4.3 | Constraint surface | 0.75 | medium_v2: length_bound eliminated, counterfactual revalidation; field audit via `error_details.loc` | inline numbers |
| 4.4 | Formatting conceals content | 1.0 | Fence-strip pure vs compound; prompt ablation in one paragraph incl. precedence caveat and concealed-inclusive rates | Tab 3 (small) |
| 5 | Discussion & limitations | 1.0 | Two-vendor scope decision; moving target in both directions; temperature + max_tokens asymmetry; dev-set validation; no correctness evaluation | — |
| 6 | Conclusion | 0.25 | | — |
|   | **Total** | **7.25** | references and appendix not counted | |

## Appendix (unlimited, move-only)
- A. Cell manifest, resolved model versions (with pre-capture counts), sampling procedure
- B. Full schemas (medium, medium_v2, medium_v3) and three prompt texts
- C. Classifier: detection-order provenance, per-category P/R vs blind labels, corpus screens — **labelled full-corpus basis**
- D. Experiment G (identifier sub-causes, counts only, no rates)
- E. Per-domain distributions; first-attempt validity by node with reachability denominators
- F. Cross-field constraints (per-node constraint counts, never "tested N times")
- G. Divergence metric (both maxima, 0.4 pp tie noted, unrestricted max footnoted)
- H. Haiku robustness check (one run per question); zero-length completion (attempt 2451)
- I. Prompt ablation full table

## Removed entirely (not moved)
- Residual invalidity / "remediation profile" table (unit mismatch; not needed for thesis)
- Training-mechanism speculation, "substantively correct", "clusters", rebuttal-voice phrasing
- 3M impossibility claim (gone with the new §1 example)
- Any power / significance-from-overlap language

## Stated-once rule
Decoder distinction → §2 only. Perturbation rationale → App D only. Generation-durability → §5 only.

## Work order
1. `sqlite3 <DB> ".schema"` → fix `COL`, `LABELS_SQL`, `VALIDATOR_MESSAGES`, `node_model()` in `make_paper_numbers.py`
2. `make numbers` until golden checks pass (fix code, never golden values)
3. Start a **fresh** `paper/main.tex` + `paper/sections/*.tex`; do not edit the 23-page draft, pull prose from it selectively
4. Write in order §4 → §3 → §1 → §5 → §2 → §6, running `make lint` after each
5. Appendix last (mostly moves)
6. Read-through against the review 2 checklist; delete items that no longer apply