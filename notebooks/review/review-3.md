**Yes—this is your strongest draft so far.** The reduction from 23 pages to 11 has helped substantially. The central argument is easier to follow, the scope is more defensible, and several major errors from the earlier drafts are now corrected.

**My honest assessment: promising, but I would still hold submission for one more focused revision.** The remaining problems are no longer primarily about the paper’s premise. They concern an unfinished reproducibility appendix, inconsistent run counts, insufficient validation of the classifier, and important new results in the appendices that are not yet reflected in the main analysis.

**Privacy:** I won’t intentionally publish your manuscript or disclose it to other users. However, I cannot provide an NDA or guarantee confidentiality beyond the platform’s data-handling policies. Before releasing the raw outputs, check them for sensitive information and redistribution restrictions.

I reviewed all 11 supplied pages and the figure image. Because there are no line numbers, I refer to sections, tables, and quoted sentences. I have not externally verified the references, model endpoints, or experimental artifacts.

---

# 1. Overall verdict and improvement

## What is now substantially better

1. **The constrained-decoding discussion is technically much better.** You no longer rely on the false claim that grammars cannot enforce your regex and length constraints.
2. **The experimental-cell count now reconciles.** Appendix A lists 20 cells, of which two are excluded, leaving 18.
3. **The impossible 214-character “overlength” example is removed.** The new 251–315 range is compatible with the stated cap.
4. **The prompt-ablation interpretation is appropriately narrower.** You no longer claim that underlying behavior is proven unchanged.
5. **The classifier’s validation-first precondition is clear.**
6. **Cross-node referential integrity is correctly described as unimplemented, not inexpressible.**
7. **The per-domain and first-attempt tables are valuable additions.**
8. **The manuscript is considerably less repetitive and defensive.**
9. **The headline idea is now coherent:** primary labels can obscure co-occurring violations and distort interpretation of interventions.

## Would it survive TMLR review?

**In its current form, I would still lean against acceptance.** My likely main concerns would be:

- The submitted artifact is visibly unfinished.
- A key table contains inconsistent run counts.
- The taxonomy is only checked on its own development examples by its author.
- Statistical uncertainty still ignores the experimental dependence structure.
- The paper underinterprets its new domain and first-attempt results.
- The contribution beyond familiar syntax/schema validation and JSON recovery needs sharper demonstration.

However, unlike the first draft, **I can now see a plausible route to a defensible submission without rebuilding the study entirely**.

You do not necessarily need more models. You need a more auditable analysis and stronger evidence that the diagnostic framework generalizes beyond the examples used to develop it.

---

# 2. Issues that should block submission

## Issue 1 — Appendix B is unfinished

Page 9 contains:

> “[Copy src/schemaeval/schemas/medium.py to paper/code/medium.py.]”

and:

> “[Copy src/schemaeval/prompts.py to paper/code/prompts.py.]”

These are editing instructions, not supplementary material.

For this paper, the schemas and prompts are central experimental objects. Reviewers cannot assess whether the failures result from prompt construction, schema presentation, or implementation choices without seeing them.

### Proposed solutions

- Replace both placeholders with actual content or working anonymized artifact links.
- Include:
  - Full baseline schemas.
  - Exact schema changes for both perturbations.
  - Baseline, aggressive, and few-shot prompts.
  - Exact retry messages.
  - Whether previous failed outputs remain in the conversation.
  - Error serialization and truncation rules.
  - Dependency versions, especially Pydantic.
- Include an executable command that reproduces the reported tables from stored outputs.
- Verify that the supplementary files are actually included in the submission archive.

**This is a straightforward submission blocker.**

---

## Issue 2 — The Haiku run count is still inconsistent

Table 6 reports:

> Haiku, medium, HotpotQA: **194 runs**, 1,066 attempts.

But Appendix A says:

> “The … baseline cell contains **134 runs**…”

And Table 9 reports:

> 1,066 attempts, **7.96 attempts/run**.

The arithmetic supports 134:

\[
1066/134 = 7.96,
\]

whereas:

\[
1066/194 = 5.49.
\]

Table 10 also supports the smaller baseline count: Haiku has 166 identify-stage runs, consistent with 134 HotpotQA plus 32 FinanceBench.

The most plausible explanation is that **194 includes prompt-variant runs while 1,066 includes baseline attempts only**, but this must be verified.

### Proposed solutions

- If 134 is correct, change Table 6 to 134.
- Add separate rows for the aggressive and few-shot conditions.
- Generate run counts and attempt counts using the same filtering function.
- Add automated assertions that every table’s denominator matches its reporting basis.

For example:

```text
baseline_runs =
    count_distinct(run_id where prompt_variant == "baseline")

baseline_attempts =
    count(attempt_id where prompt_variant == "baseline")
```

Also explain how the 365 variant attempts—189 plus 176—relate to the 4,396-attempt full corpus.

---

## Issue 3 — Model and endpoint provenance remains insufficient

The manuscript still lists identifiers such as:

```text
gpt-5.6-luna
gpt-5.6-sol
gpt-5.6-terra
claude-sonnet-5
claude-opus-4-8
```

I cannot authenticate these from the supplied manuscript.

A reproducibility appendix needs more than saying that an endpoint returned the requested alias unchanged. That establishes the returned identifier, not a pinned underlying model version.

### Proposed solutions

Add a model-provenance table:

| Requested ID | Returned ID | Provider/API route | Collection dates | Pinned snapshot? | Sampling settings |
|---|---|---|---|---|---|

If these are proxy aliases, internal mappings, or special-access endpoints, disclose that explicitly.

Also:

- State the full requested Haiku identifier rather than only the shortened display name.
- Provide documentation for endpoint-specific parameter behavior.
- Distinguish “returned alias” from “resolved immutable version.”
- Include actual collection dates.

**If reviewers cannot identify the evaluated models, the cross-family and cross-generation interpretation becomes difficult to assess.**

---

## Issue 4 — The classifier has not received independent validation

You are transparent about this, which is good:

> “development-set agreement, not held-out validation”

But the contribution still says:

> “validated against blind hand labels”

That sounds stronger than the actual protocol.

The classifier was changed using these examples, and the same person designed the classifier and assigned the labels. The 97.2% figure is therefore **corrected-classifier agreement with development labels**, not independent validation.

### Proposed solutions

At minimum:

1. Freeze the classifier and category definitions.
2. Sample a new held-out set.
3. Have a second person label it without seeing classifier outputs.
4. Report initial agreement before adjudication.
5. Preserve disagreements and adjudication rationales.

Include deliberately challenging cases, such as:

- A failed ordinary instance containing `title` and `description`.
- A short prose prefix.
- A schema object inside a fence.
- A malformed fence.
- Multiple validator-error categories in one attempt.
- A present field with the wrong type.

If new annotation is impossible, soften Contribution 1 to:

> “A failure taxonomy with deterministic detectors, an explicit precedence rule, and development-set checks against human labels.”

That is honest, but it leaves a weaker taxonomy contribution.

---

## Issue 5 — The uncertainty estimates still do not match the design

The manuscript repeatedly calls attempt-level Wilson intervals “indicative.”

That acknowledges the problem, but does not solve it.

Attempts are dependent because:

- Retries follow failures.
- Retry prompts include feedback.
- Some questions are repeated.
- Later-node exposure depends on upstream success.

### Proposed solutions

- Use a question-clustered bootstrap for the main descriptive rates.
- Carry all runs and retries associated with a selected question together.
- Preserve dataset strata where appropriate.
- Explain that this quantifies variability over the observed question set and does not make fixed-prefix sampling representative of the full benchmarks.
- Consider removing naive Wilson intervals from the main model table if appropriate clustered estimates are not available.

You can retain simple binomial intervals as explicitly labeled reference calculations, but they should not be your principal uncertainty analysis.

---

# 3. Important findings in your new appendices need to change the main paper

## A. Dominant profiles also depend on the task domain

Table 9 contains an important result:

| Model | Domain | Failure rate | Dominant category |
|---|---|---:|---|
| Sonnet 5 | FinanceBench | 21.1% | `length_bound` |
| Sonnet 5 | HotpotQA | 21.6% | `markdown_wrap` |

This is particularly useful because **the same model has almost identical failure rates but different dominant categories across domains**.

That may be a cleaner example of your thesis than comparing different models.

Opus also changes dominant category across domains, although its HotpotQA result rests on only two failures and needs strong qualification.

### Proposed solutions

Add a paragraph to Section 4.2:

> “Profiles also vary with task distribution. Sonnet 5 has similar failure rates on FinanceBench and HotpotQA, but its dominant category changes from length violations to markdown wrapping. Thus, the observed profile depends on the model, constraints, and task distribution.”

Do not describe the profile only as a joint property of model and constraint surface. Prompting, node exposure, and domain also matter.

Also consider reporting fence-strip results by domain. The pooled Haiku–Sonnet contrast may partly reflect differences in task composition.

---

## B. Haiku’s 0% first-attempt validity is too important to leave unexplained

Table 10 reports:

- Identify: 166 reached, **0.0% valid initially**.
- Gather: 166 reached, **0.0% valid initially**.
- Answer: 143 reached, **0.0% valid initially**.

This is a striking result: all 475 observed first attempts fail strict validation.

It is not mathematically inconsistent with the aggregate results. But it is unusual enough that reviewers will want assurance that “first attempt” was extracted correctly.

### Proposed solutions

Audit the query and check:

1. Does every run-node pair have exactly one first attempt?
2. Is the first attempt selected before filtering to failures?
3. Are successful first attempts retained in the database?
4. Is retry numbering consistent across collection batches?
5. Are success flags taken from the validation result rather than the presence of an error record?

Then report:

- First-attempt failure composition.
- Whether those initial failures are mostly wrapping.
- First-attempt validity after fence removal.
- Retry success.

If correct, this is a meaningful operational finding: the repair loop is doing nearly all of the strict-conformance work for that model.

---

## C. Run-level success can probably be reported now

You already provide enough information to suggest run-level outcomes.

Under the stated sequential, retry-only-on-failure design, Haiku has:

- 451 valid attempts: \(1329-878\).
- 166 successful identify stages, because 166 runs reach gather.
- 143 successful gather stages, because 143 reach answer.

That leaves:

\[
451-166-143 = 142
\]

successful answer stages, suggesting **142 completed runs out of 166**, or approximately **85.5%**.

Please verify this from actual run records rather than reporting the inferred number directly.

### Proposed solutions

Add a compact operational table:

| Model | Runs | Completed runs | Completion rate | Attempts/completed run |
|---|---:|---:|---:|---:|

This would show why attempt failure and pipeline completion are different quantities. It would also give your study more practical value.

---

# 4. Section-by-section review with corrections

## Page 1 — Title, abstract, introduction

### Title

> “Prompt-Enforced Pydantic Schemas”

Prompting requests compliance; validation enforces acceptance. “Prompt-enforced” is understandable, but slightly imprecise.

**Possible replacement:**

> **Beyond JSON Validity: Diagnosing Schema-Conformance Failures in Prompt-and-Validate LLM Pipelines**

Your existing title is usable, but this alternative better matches the revised contribution.

### Abstract: “so fence-stripping alone is not a repair”

Fence stripping **is a complete repair for 48.0% of wrapped cases**.

The problem is that it is not sufficient for all of them.

**Replace with:**

> “so fence removal is a partial repair whose effectiveness varies substantially across configurations.”

### Abstract: “primary length-violation share”

Table 5 reports percentages of **attempts**, not shares of failures.

**Replace “share” with “rate”** when referring to that table.

### Abstract: “the change is mechanical”

Your revalidation establishes that the 18 stored length failures become valid under relaxed constraints. It does not establish that every difference in the fresh-generation distribution is mechanical.

**Use:**

> “revalidating the stored failures confirms that relaxing the caps is sufficient to eliminate those observed violations.”

### Introduction: regex description

> “meaning lowercase snake_case that starts with a letter”

The regex permits consecutive and trailing underscores and imposes a length range of 3–31 characters.

**Replace with:**

> “a 3–31-character lowercase identifier beginning with a letter and containing letters, digits, or underscores.”

### Introduction: normalization

The revised example is much better. Still:

> “reaching it requires a normalisation convention the task never states”

could suggest a valid identifier cannot be inferred from the pattern.

**More precise:**

> “the task does not specify which conforming normalization convention should be used.”

---

## Page 2 — Contributions and related work

### Contribution 1

Qualify “validated,” as discussed above.

### Contribution 3 and Section 4.4 title

You use “content violation” and “content failures.”

Because you explicitly do not assess semantic correctness, readers may interpret these terms incorrectly.

**Prefer:**

- “underlying schema violation”
- “payload-conformance failure”

For example:

> **Formatting failures conceal underlying schema violations**

### Related work

This section is now much more focused.

However, you should explicitly distinguish your method from the straightforward baseline:

> Parse or extract JSON, validate the payload, and report syntax versus schema errors.

A reviewer may ask whether the central finding is an expected consequence of classifying wrappers before payload validation.

### Proposed solution

Add a short positioning paragraph explaining that your contribution is not discovering that both errors can coexist, but:

- Quantifying their co-occurrence.
- Showing how primary-label precedence alters intervention interpretation.
- Providing reproducible configuration-level diagnostics.

Also add the original HotpotQA and FinanceBench citations.

---

## Page 3 — Design and taxonomy

### “Three schema tiers”

The variants are not a simple increasing strictness hierarchy.

**Prefer:**

> “one baseline schema and two targeted variants”

You can retain the internal code names.

### Exact detector definitions

The compressed taxonomy omits details required for mechanical reproducibility.

For example:

> “at least two JSON Schema meta-keywords such as properties and required”

“Such as” is insufficient for an exact predicate.

### Proposed solutions

In an appendix, provide:

- Complete keyword vocabulary.
- Exact preamble-span detector.
- Whitespace handling.
- Full Pydantic error-code mapping.
- Treatment of type mismatches.
- Custom-validator message mapping.
- Catch-all category name and behavior.
- Complete pseudocode.

The previous draft mapped numeric type errors to `range_bound` and other type errors to `missing_field`. This draft omits those mappings. Make clear whether the implementation changed or the description was merely shortened.

### “The Stage-1 predicates must precede Stage 2”

This is a design choice, not a mathematical requirement.

**Replace with:**

> “We give Stage-1 predicates precedence to preserve the behavioral distinctions that Pydantic error codes alone do not express.”

A multilabel classifier or parallel behavioral/validator representation is a legitimate alternative.

---

## Page 4 — Tables 1–2 and profiles

### Arithmetic

The displayed primary-category counts sum correctly to **1,126**.

The Table 2 rates are consistent with the displayed counts.

The caption correctly identifies the HotpotQA-only models. This is improved.

### Table 1 rounding

The rounded shares sum to 100.1%.

This is ordinary rounding, not a substantive error. Add:

> “Percentages may not sum to 100 due to rounding.”

### “They do not follow vendor tier”

The evidence supports a narrower statement: vendor or capability-tier labels do not uniquely determine these observed profiles.

**Prefer:**

> “The observed profiles are not determined solely by vendor, model tier, or failure rate.”

### “the other never produces”

Use:

> “the other did not produce in our observations.”

Keep all absence claims explicitly sample-bound.

---

## Page 5 — Figure 1 and length perturbation

### Figure 1

The figure is readable and useful. The colors and legend allow the main categories to be distinguished.

The main weakness is that a bar with four failures looks as evidentially substantial as one with 878.

### Proposed solutions

Add to each row:

- Failure count, \(n_{\text{fail}}\).
- Optionally the absolute failure rate.

For example:

```text
gpt-5.6-terra@loose  n_fail=4, rate=2.6%
```

That is more important than adding uncertainty bands to a crowded stacked chart.

### Length measurements

The revised 8 coverage-note, 9 answer, and 1 fact breakdown sums correctly to 18.

But:

> “1 fact value of at most 480 characters”

is still oddly imprecise.

If the raw completion is available, report the actual field length. If only a bounded or truncated representation survives, explain that limitation.

### Mechanical revalidation

This is valuable, but separate the two experiments explicitly:

| Analysis | Attempts | Failures | Rate |
|---|---:|---:|---:|
| Original medium outputs | 178 | 28 | 15.7% |
| Same outputs under relaxed schema* | 178 | 10 | 5.6% |
| Fresh generations under relaxed schema | 324 | 24 | 7.4% |

\*The second row follows if all 18 reported failures become valid and no other validation behavior changes; verify by revalidating the complete set.

That table would make the counterfactual distinction unmistakable.

---

## Page 6 — Compound failures, prompting, recommendations

### Table 4

The counts reconcile:

- 327 pure-formatting cases.
- 354 compound cases.
- 681 wrappers total.

The revised Wilson interval for 4/41, approximately **[3.9%, 22.5%]**, is consistent with the standard calculation.

### Table 5

The interpretation is now much better.

However, several reported values have changed across drafts:

- Baseline wrapping: 48.5% → 49.0%.
- Baseline primary length: 14.3% → 14.4%.
- Earliest-run deduplication: 257/401 → 260/404.

Those changes are not automatically errors. They may reflect corrected filtering or earliest-run selection. But they should come from one frozen analysis version, not manual edits.

### Proposed solutions

- Include exact counts alongside percentages.
- Record the classifier and analysis version used for each release.
- Regenerate every related figure and table from the same data snapshot.
- Add an internal reconciliation report before submission.

### “primary counts are lower bounds on prevalence”

For the detected violations you count, this is a useful description. But the method does not establish error-free measurement of “true prevalence.”

**Safer wording:**

> “Single-primary-label counts omit some detected co-occurring violations.”

### “Do not express length bounds inside a regular expression”

Still too absolute.

**Replace with:**

> “When diagnostic clarity matters, represent identifier length separately from character-class restrictions.”

There are valid reasons to encode both in a regex. Your result supports diagnostic separation, not a universal prohibition.

### “the measurement tells an author which side must move”

The measurement identifies the mismatch. It does not decide whether the schema, prompt, model, or application design should change.

**Replace with:**

> “The measurement identifies the mismatch that the application must resolve.”

---

## Page 7 — Limitations and conclusion

This section is significantly improved.

### Durability

The cross-generation observations are descriptive. They do not isolate a generation effect because sampling settings and exposure differ.

**Suggested wording:**

> “The configurations we tested show different profiles across model generations; these comparisons do not isolate generation from other configuration differences.”

### Repeated-question sensitivity

> “does not materially change the most affected cell”

Your check shows similarity in one aggregate failure rate. It does not establish that repetition leaves category composition, compound fractions, or uncertainty unchanged.

**Narrow it to:**

> “changes that cell’s pooled failure-rate estimate by approximately 0.5 percentage points.”

### Conclusion

> “hides most of what a practitioner needs”

This is rhetorically stronger than necessary.

**Replace with:**

> “does not identify the interventions needed to address the observed failures.”

The conclusion should also mention domain dependence, given Table 9.

---

# 5. Appendix-specific corrections

## Appendix A — Manifest and sampling

Beyond the 194/134 discrepancy, add:

- Unique question counts per cell.
- Exact question IDs.
- Dataset versions.
- Collection dates.
- Separate prompt-variant rows.

Run counts do not reveal unique prefix lengths when questions are repeated.

Also state whether the 30-run pilot threshold was fixed before examining results. The earlier drafts claimed this; the current draft omits that detail.

## Appendix C — Validation

The table’s “recall” values are **within the label-stratified development sample**, not corpus recall.

Put that directly in the caption.

The sentence:

> “predicates broader than the detectors”

is not correct for the `properties` screen: requiring `properties` is not a superset of accepting any two keywords from the vocabulary.

**Replace with:**

> “We used relaxed screens for wrapping and preambles, and a keyword-restricted screen for schema mirroring.”

Also, “bounds recall” is vague. Say:

> “checks for missed mirroring cases among failures containing this key.”

## Appendix D — Identifier perturbation

You again report 18 total failures across the four cells but discuss 19 identifiers. The previous draft explained that only 17 attempts were regex failures. That clarification has disappeared.

**Restore:**

> “Of 18 failing attempts, 17 were assigned `regex_pattern`; these contained 19 violating identifiers.”

Your mechanical sub-causes can overlap:

- Non-ASCII is also outside the ASCII character class.
- A leading digit may coexist with length overflow.

State whether annotations are multilabel or assigned by precedence. If single-valued, give the order.

Also:

> “too few to support rates or shares”

is statistically imprecise. You can report descriptive rates at any sample size; the problem is inferential uncertainty.

**Replace with:**

> “too few failures for precise comparative inference.”

## Appendix E — Domain and first-attempt results

These additions are useful enough to affect the main findings, not merely serve as supplementary reassurance.

Audit the Haiku zeros and discuss the Sonnet domain-profile change.

Add first-attempt counts, not only percentages:

```text
valid first attempts / runs reaching node
```

## Appendix F — Model-level constraints

The totals reconcile:

\[
3997-1126 = 2871
\]

valid attempts, plus four validator-stage identifier failures gives 2,875 attempts reaching those checks.

This is much clearer than the previous full-corpus/reporting-basis mixture.

Keep the claim scoped to the relevant node-level validators; do not imply that no nested validator can ever run before another field fails.

## Appendix G — Divergence

This is now appropriately supplementary and uses the main reporting basis.

Still, the 97.5-point unrestricted maximum should identify the exact groups and category. That makes the number auditable.

The maximum-gap statistic should remain secondary. It is selected to be extreme and does not summarize the full distributions.

---

# 6. A practical analysis that would strengthen the paper cheaply

Your stored outputs already support an offline repair comparison.

From Table 2 and Table 4:

| Model | Strict failure | Residual invalidity after fence removal |
|---|---:|---:|
| Sonnet 5 | \(67/313 = 21.4\%\) | \((67-37)/313 = 9.6\%\) |
| Haiku 4.5 | \(878/1329 = 66.1\%\) | \((878-290)/1329 = 44.2\%\) |

Across the reporting corpus:

\[
(1126-327)/3997 = 20.0\%
\]

remain invalid after recovering pure-wrapper failures, compared with 28.2% initially.

### Why this helps

It connects the taxonomy to an interpretable intervention:

> How much invalidity remains after a simple deterministic repair?

### Necessary qualification

These are **offline rates on the stored attempts**. They are not the outcome of rerunning the pipeline with repair enabled, because repair would change retries and downstream exposure.

This distinction can be stated in one sentence and gives the paper more practical substance without new inference calls.

---

# 7. What would make this more convincing as a TMLR paper?

The remaining scientific challenge is **contribution strength**.

A skeptical reviewer may say:

> “Wrapping can coexist with schema errors, and relaxing constraints removes corresponding failures. What is new beyond that?”

Your answer should be empirical and operational, not rhetorical:

1. **Quantification:** how often wrappers conceal additional violations.
2. **Heterogeneity:** how that fraction varies across configurations and domains.
3. **Measurement consequences:** how primary-label precedence changes conclusions drawn from interventions.
4. **Operational consequences:** residual invalidity and run-level outcomes under repair.
5. **Transfer:** whether the taxonomy remains useful for schemas not used to construct it.

The most valuable additional experiment would likely be **a small held-out-schema evaluation**, not adding another vendor merely for breadth.

Similarly, independent annotation and a matched prompt ablation would strengthen the study more than another descriptive maximum-gap statistic.

---

# 8. Prioritized action list

## Must fix

1. Replace Appendix B’s placeholders with actual artifacts.
2. Reconcile 194 versus 134 Haiku runs.
3. Document endpoint provenance and collection dates.
4. Publish exact classifier predicates and mappings.
5. Audit Table 10’s Haiku first-attempt zeros.
6. Generate every table from one frozen reporting basis.

## Strongly recommended before submission

7. Add independent held-out annotation.
8. Use question-clustered uncertainty.
9. Discuss Sonnet’s domain-dependent profile.
10. Report run-level completion.
11. Add offline residual invalidity after fence removal.
12. Include exact counts in the prompt table.

## Final wording cleanup

13. “Content failures” → “underlying schema violations.”
14. “Share” → “rate” where the denominator is attempts.
15. “Fence stripping is not a repair” → “fence stripping is only a partial repair.”
16. “Never produces” → “was not observed to produce.”
17. Replace the universal prohibition on regex length bounds with a diagnostic recommendation.
18. Add original dataset citations and verify all reference metadata.

---

# Bottom line

**This draft is genuinely better—not merely shorter.** The main argument is now scientifically recognizable and substantially more defensible.

**I would still not submit the exact version supplied**, primarily because the artifacts are unfinished, the run manifest is inconsistent, and the validation and uncertainty analyses remain weaker than the paper’s framing suggests.

My recommendation is to stop expanding the narrative and perform a **final evidence-focused revision**:

- audit the numbers,
- finish the artifacts,
- validate the classifier independently,
- and elevate the useful domain/first-attempt results already present.

That would give this manuscript a materially stronger chance in review.