Thank you for trusting me with this. There is a worthwhile paper here, and the effort you put into preserving outputs, diagnosing classifier bugs, and reporting limitations is evident.

**On privacy:** I won’t intentionally share your manuscript with other users or publish it. However, I cannot provide an NDA or guarantee confidentiality beyond the platform’s data-handling policies. If the raw completions contain sensitive information, redact them before sharing more or releasing an artifact.

I reviewed all 19 pages you supplied. Because this is parsed text without line numbers, I’ll refer to **pages, sections, and quoted passages**. I can evaluate the manuscript’s reasoning, internal consistency, and technical claims; I cannot verify the experiments, model endpoints, references, or implementation without the corresponding artifacts.

# 1. Honest verdict: would this survive TMLR review?

**I would not submit this version yet.**

My likely recommendation, if reviewing this manuscript as written, would be **rejection in its present form**, although I think a substantially revised version could become publishable.

The problem is **not principally writing quality**. The manuscript is generally readable and has a strong organizing idea. The problem is that several central interpretations exceed the evidence, and a few technical claims are incorrect.

The most consequential issues are:

1. **The opening “unsatisfiable identifier” argument is false as written.**
2. **The contrast with constrained decoding incorrectly treats regex and length constraints as inherently outside grammar enforcement.**
3. **The published classifier algorithm does not correctly describe Pydantic v2’s JSON-parsing exception behavior.**
4. **Model comparisons combine dependent retries, unequal question exposure, different sampling settings, and uneven experimental coverage.**
5. **The perturbations support narrower conclusions than the causal language claims.**
6. **The “four clusters” are groups defined by their dominant category—not independently established clusters.**
7. **Several denominators and reporting conventions need reconciliation.**
8. **Independent validation and reproducibility details are insufficient for the strength of the claims.**

These are fixable, but some require reanalysis or new experiments—not copyediting.

## What is genuinely strong

- **The compound-failure result is your strongest finding.** Distinguishing “valid after fence removal” from “still invalid after fence removal” is operationally useful.
- Preserving raw completions and permitting relabeling is good experimental practice.
- Separating conformance from extraction correctness is appropriate.
- Explicitly describing precedence is better than silently imposing it.
- You acknowledge important limitations rather than hiding them.
- The question—*what does a validity rate conceal about remediation?*—is meaningful.

I would rebuild the paper around those strengths.

---

# 2. Submission-blocking technical and methodological issues

## A. The 3M example does not establish unsatisfiability

You write on page 1:

> “The pair is unsatisfiable…”

And later:

> “no amount of instruction-following competence recovers it.”

This is incorrect unless your task imposes an additional naming rule that you have not stated.

These identifiers all satisfy your pattern:

```text
company_3m
entity_3m
id_3m
```

Your schema requires a valid canonical identifier; it does not, as described, require the identifier to preserve the entity name’s initial character.

The correct conclusion is:

> Direct lowercasing of some entity names conflicts with the identifier pattern unless an explicit normalization convention is provided.

That is an **underspecified normalization policy**, not an unsatisfiable schema–entity pair.

This error propagates through the introduction, taxonomy, discussion, and practitioner recommendations. A reviewer who spots it on page 1 may distrust the later reasoning.

**Suggested replacement opening:**

> A practitioner requires canonical identifiers matching `^[a-z][a-z0-9_]{2,30}$`, but does not specify how to normalize names beginning with digits. For the entity “3M,” a model may produce `3m`, which violates both the initial-letter requirement and the minimum length. A valid identifier such as `company_3m` exists, but choosing it requires a normalization convention absent from the task specification. This illustrates a mismatch between schema constraints and the instructions needed to satisfy them.

Also, your regex does not strictly enforce snake_case: it permits consecutive and trailing underscores. Call it a **lowercase identifier pattern** unless you intend that broader definition.

## B. The constrained-decoding distinction needs correction

You repeatedly write that grammars constrain surface form while character patterns and field-length caps are predicates over values that grammars admit.

That is too broad and technically wrong.

For the constraints used here:

- Character-class restrictions are regular-language constraints.
- Bounded string lengths can be represented in a grammar or automaton.
- Enumerations can be enforced during decoding.
- Implementations differ in which JSON Schema keywords they support.

The defensible distinction is:

> Constrained-decoding systems can enforce supported structural and value constraints, but may not enforce arbitrary Pydantic validators or unsupported schema features.

Whether a particular framework supports your exact pattern or character-count semantics is an **implementation question**, not a fundamental limitation of grammars.

Similarly:

> “Anthropic tool-forcing … implement[s] constrained decoding”

is not established simply by selecting a tool-forcing API option. Tool selection, argument generation, and strict schema enforcement are different facilities. Document the exact API and guarantee rather than treating them as interchangeable.

**Required fix:** rewrite Sections 1, 2, 3.4, and 6.4 consistently.

You can justify studying prompt-only generation without claiming decoder enforcement cannot address your dominant failures.

## C. Algorithm 1 mishandles Pydantic’s parsing errors

Your algorithm says:

```text
attempt S.model_validate_json(y)
if JSONDecodeError then return parse_error
```

In Pydantic v2, malformed JSON passed to `model_validate_json()` normally raises a **Pydantic `ValidationError` containing a `json_invalid` error**, not a standard-library `JSONDecodeError`.

Unless the implementation performs a separate `json.loads()` step, the algorithm’s parse-error branch will not behave as described.

This is especially important because the manuscript reports a previous parse-error classification bug.

**Required fix:**

- Map Pydantic’s `json_invalid` explicitly; or
- Show the separate parsing stage actually used in the code.
- Add regression tests for empty output, malformed JSON, truncated JSON, and valid JSON of the wrong root type.

I cannot tell whether this is a pseudocode error or an implementation error. Either is submission-blocking until resolved.

## D. The classifier can mark valid instances as failures

Your `schema_mirroring` heuristic flags an object whose root keys include at least two schema keywords.

But a legitimate application schema could contain:

```json
{"title": "Example", "description": "A valid record"}
```

The heuristic would label this `schema_mirroring` before validation—even if it is a valid instance of the target schema.

That contradicts the combination of:

- “arbitrary Pydantic model,”
- schema-tier invariance,
- and a total classifier that returns `clean` for conforming outputs.

**Better design:**

1. Establish strict conformance first.
2. Preserve that result as the validity ground truth.
3. Apply behavioral classification to failures.
4. Record surface and underlying violations separately.

You can still give surface categories precedence **within already established failures**.

If classification is only ever called on known-invalid attempts, state that precondition explicitly and correct Algorithm 1.

## E. Your unit of analysis makes model comparisons difficult

Attempts are not independent samples:

- Retries depend on earlier failures.
- Retry prompts contain validation feedback.
- Questions are repeated.
- Later nodes are observed only when earlier nodes succeed.
- Poorer-performing models generate more attempts per run.
- Some models use temperature zero and others provider defaults.

The pooled attempt-level rate is a legitimate descriptive measurement of the observed pipeline workload. It is **not a clean estimate of a model’s initial schema-following ability**.

Moreover:

> “An aggregate rate of 28.2% tells a practitioner how often the pipeline breaks”

is wrong. It tells them the proportion of observed attempts that fail, not the proportion of end-to-end runs that fail.

**At minimum, report:**

| Measurement | What it answers |
|---|---|
| First-attempt validity by node | How reliably does the initial prompt work? |
| Retry success conditional on prior failure | How useful is repair feedback? |
| End-to-end run success | How often does the pipeline finish? |
| Attempts and tokens per successful run | What is the operational burden? |
| Failure composition by node | Are signatures driven by task-stage exposure? |

Use question-clustered uncertainty estimates, preserving the dependence among retries and repeated runs.

Also, Haiku contributes approximately **33% of attempts but 78% of failures** on the reporting basis. Therefore, the aggregate failure composition is heavily Haiku-weighted. Report a sensitivity analysis or equal-weighted summaries alongside the pooled result.

## F. The perturbations do not establish the claimed causes

### Length-cap perturbation

You report `coverage_notes` values of 1,017–1,977 characters and raise the cap to 1,000.

If those numbers are **field lengths**, the original outputs would still violate the new cap. If they are **whole-completion lengths**, they do not directly quantify the field-level mismatch.

Rerunning with a modified schema can also change generation behavior.

Therefore, separate:

1. **Counterfactual revalidation:** validate the same stored output against both schemas.
2. **Regeneration:** prompt the model under the modified schema and examine its new outputs.

These answer different questions.

Furthermore, observing zero length errors does not prove the original cap was “miscalibrated.” A 250-character cap may be a genuine downstream requirement. To establish miscalibration, explain the application requirement and whether longer outputs preserve the intended utility/cost tradeoff.

### Regex perturbation

The experiment confirms that removing a leading-digit restriction removes that rejection cause while retaining a length ceiling leaves length rejections possible.

That is useful operationally, but largely follows from the constraint definitions. It does not establish that the remaining signature is a stable model property rather than an artifact of the remaining constraint.

Also:

- Sol: 3 + 5 failures.
- Terra: 6 + 4 failures.
- Total: **18 failures**.

You then discuss **17 failing attempts** with violating identifiers.

This may simply mean one failure belongs to another category. If so, say so explicitly.

## G. “Four clusters” currently means “four argmax groups”

You write:

> “Grouping configurations by their dominant failure category yields four clusters, each internally consistent across every member.”

If groups are defined by the dominant category, agreement on the dominant category is true by construction.

It does not show that:

- Their full distributions are similar.
- The groups are stable across datasets.
- The groups persist across tiers.
- The groups outperform vendor/tier partitions under a quantitative criterion.

You have two reasonable options:

**Option 1: narrow the language.**

> “At the baseline tier, the pooled model-level distributions exhibit four observed dominant-category profiles.”

**Option 2: perform a real stability analysis.**

Compare full category distributions, quantify within-/between-group distances, and assess stability under question-level resampling.

Also, Sonnet 4.6 changes from length-dominant to regex-dominant under `medium_v2`. That directly limits claims that dominant category is an invariant model property.

## H. The prompt-ablation interpretation is partly confounded by precedence

You observe:

- Less `markdown_wrap`.
- More primary `length_bound`.

But a wrapped, overlong output is counted as `markdown_wrap`, not `length_bound`. Therefore, suppressing wrapping can increase the primary length category **without increasing the underlying prevalence of overlong content**.

You recognize this possibility in prose, but the abstract and section title still encourage a “failures migrate” interpretation.

The necessary analysis is:

> Strip wrappers and measure underlying length violations in every prompt condition.

Also, reducing failure from 64.9% to 50.0% is:

- **14.9 percentage points absolute**;
- approximately **23% relative**.

That is not “not the rate,” and calling it merely “modest” is unnecessarily dismissive of your own result.

Change the heading to:

> **Prompt variants reduce strict-format failures but leave substantial residual violations**

---

# 3. Page-by-page review

The points below cover the remaining substantive issues and presentation problems throughout the manuscript.

## Page 1 — Title, abstract, opening

### Title

> “Across LLM Families”

This promises fairly broad generalization. Your evidence is narrower: nine hosted configurations from two vendors, one custom pipeline, and fixed question prefixes.

The title is not unacceptable, but a more defensible version is:

> **Beyond JSON Validity: Diagnosing Schema-Conformance Failures in Prompt-and-Validate LLM Pipelines**

“Prompt-enforced” is also slightly misleading: prompting requests conformance; it does not enforce it in the strict sense.

### Abstract

The abstract is readable but overpacked. It introduces taxonomy, clustering, divergence, compound failures, two perturbations, prompting, and release artifacts.

Specific fixes:

- “decidable by a deterministic function” → **“assigned by a deterministic classifier.”** Your behavioral detectors are operational heuristics, not proofs of latent intent.
- “configurations cluster” → qualify or replace as discussed above.
- “locate the causes” → **“probe sensitivity to selected constraints.”**
- “difference in repair cost” → **“difference in residual invalidity after fence removal.”** Actual repair cost is not measured.
- “We release…” → provide an anonymized artifact link and release contents.

The 52.0% compound-failure result deserves greater prominence than the maximum-divergence statistic.

### Opening example

Replace the unsatisfiability argument. This is the highest-priority prose correction in the paper.

## Page 2 — Introduction and contributions

> “behaves identically across vendors”

The architecture is portable; behavior is not identical. Your own experiment uses different token limits and sampling settings.

Use:

> “can be implemented across vendors without access to their decoding internals.”

> “what application frameworks default to”

This requires evidence or narrower wording. Frameworks have different defaults and may select provider-native structured output.

> “A practitioner told only the category would have predicted neither outcome.”

Too strong. Someone seeing a length-bound failure could reasonably predict that increasing the cap might reduce it.

Better:

> “Sub-cause annotations distinguish which violations a particular relaxation can and cannot address.”

### Contributions

Contribution 3 says:

> “establishing … repair cost”

You measure the fraction recoverable by one deterministic repair, not cost.

Contribution 4 says:

> “separate schema-driven from model-driven failure”

The intervention does not cleanly identify that distinction. Both prompt behavior and constraints participate in the outcome.

## Page 3 — Related work

The related-work discussion is thoughtful but repeatedly overstates alignment with other studies.

> “We observe the same redistribution…”

Changes in semantic wrong-value incidence and changes in schema-error categories are not necessarily the same phenomenon. Present this as an analogy or hypothesis.

> “mode collapse is not a prompting defect to be engineered away”

Three prompt variants on one model cannot establish that. Also, “mode collapse” is overloaded and may be inappropriate for occasional conversational formatting.

> “We apply the same method one layer down.”

Your methodology differs materially from MAST:

- Behavioral/error-code classification versus broader trace interpretation.
- One nonindependent annotator versus independent annotators.
- Much smaller annotation support.

Use “inspired by” rather than “the same method.”

### Missing related work

The paper needs a more direct comparison with:

- Existing structured-output error analyses.
- Parser/validator-based evaluations.
- JSON recovery and repair systems.
- Schema-compliance evaluations distinguishing syntax, structure, and values.

I cannot verify your reference metadata from the manuscript alone. Independently check every title, author list, identifier, and claimed result.

## Page 4 — Study design, schemas, models

### Pipeline description

You motivate the sequential design using downstream references to upstream identifiers.

However, the listed validators appear largely **within-object**:

- Primary ID belongs to current entities.
- Counts match current lists.
- Confidence matches bucket.

Where is actual membership of `Fact.entity_id` in the **previous node’s** identifier set enforced?

A regex check does not enforce referential integrity.

Either:

- Document the cross-node validator and its contextual inputs; or
- Narrow the claim about what the sequential design tests.

### Three schema tiers

These are better described as:

- Baseline schema.
- Relaxed-length variant.
- Relaxed-character-class variant.

They are not three straightforward levels of one strictness hierarchy.

### Model identifiers

Names such as:

```text
gpt-5.6-sol
gpt-5.6-luna
gpt-5.6-terra
claude-sonnet-5
claude-opus-4-8
```

need clear provenance. I cannot authenticate them from this text.

If they are public endpoints, provide collection dates and provider documentation. If they are internal aliases or proxy mappings, disclose that and avoid treating them as self-evident public model generations.

An alias returned unchanged is **not evidence that a pinned underlying model version was captured**.

This issue could independently undermine reproducibility if left unresolved.

## Page 5 — Enforcement, runs, reporting basis

### Retry protocol

“Validation error appended” is insufficient for reproduction. Include:

- Exact initial system and user messages.
- Whether the prior assistant output is retained.
- Error formatting and truncation.
- Whether failures reset conversation state.
- Exact abandonment behavior.
- Handling of refusals, API errors, and incomplete responses.

### Apparent Haiku denominator mismatch

You identify:

> 134 HotpotQA baseline runs, 1,066 attempts.

Then the repeated-question check compares:

> 257/401 = 64.1%

against:

> 878/1,329 = 66.1%.

But 1,329 is the **both-domain pooled Haiku total** in Table 4.

That appears to compare a deduplicated HotpotQA subset with a pooled HotpotQA-plus-FinanceBench quantity.

If so, the relevant full HotpotQA comparator is the 64.9% in Table 8—not 66.1%.

Please reconcile this explicitly.

### Reporting basis

The paper changes basis for:

- Main results.
- Validation.
- Divergence.
- Prompt variants.
- Cross-field analysis.

These changes are disclosed, which is good, but the bookkeeping is too hard to audit.

Add one complete cell table with:

```text
model | schema | dataset | prompt | unique questions |
runs | attempts | failures | collection batch | included?
```

Generate every headline table from that table programmatically.

## Page 6 — Datasets, determinism, taxonomy rationale

### Datasets

Add the original dataset citations and specify:

- Dataset package/repository.
- Version or revision.
- Exact question IDs.
- Exact per-cell prefix lengths.
- Context assembly.
- How FinanceBench truncation is performed.

“First n” is not reproducible unless `n` is reported for every cell.

### Determinism

Temperature zero does not guarantee deterministic hosted inference.

Use:

> “We requested greedy or temperature-zero sampling where supported; exact repeatability is not guaranteed.”

### Token ceiling

The asymmetric ceiling is a potential confound, not merely a completeness note. It could affect truncation or responses with no visible text even if field caps are much smaller.

Report finish/stop reasons and output token distributions.

### Taxonomy rationale

> “the first is repaired by three lines of string handling”

Your own analysis shows that only some wrapped cases are repaired that way.

Write:

> “A pure wrapper failure may be repaired deterministically; wrapped outputs with additional violations are not.”

## Page 7 — Detector definitions

### `prose_preamble`

Why 20 characters?

A short preamble still violates JSON-only instructions. If the threshold is operationally motivated, justify it and show sensitivity at other thresholds.

Also specify the brace-span detector. Does it recognize balanced braces and quoted braces, or merely a substring matching heuristic?

### `schema_mirroring`

Beyond false positives, it can miss genuine schema-like responses lacking your keyword combination. Report its boundary as operational, not as a definitive inference about model intent.

### Pydantic mapping

Several mappings are semantically awkward:

- Numeric type errors → `range_bound`.
- Nonnumeric type errors → `missing_field`.
- All remaining custom `value_error`s → `cross_field_ref`.

A present field of the wrong type is not missing. A string where a number is required is not necessarily out of range. Arbitrary custom validators need not be cross-field.

Consider separating:

- Missing required field.
- Type mismatch.
- Numeric bound.
- Custom validator failure.

### Incorrect Pydantic capability claim

> “item-level pattern constraints on list elements that Pydantic cannot express declaratively”

Pydantic v2 supports constrained item types, for example:

```python
from typing import Annotated
from pydantic import StringConstraints

CanonicalId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,30}$")
]

supporting_entity_ids: list[CanonicalId]
```

Correct this statement.

### Plurality rule

A repeated error across many list elements can dominate a single important violation elsewhere. Include sensitivity to:

- First error.
- Plurality.
- Distinct error categories.
- Multilabel reporting.

## Page 8 — Table 1, Algorithm 1, precedence

**Table 1’s counts sum correctly to 1,126.**

However, “Primary remedy” sometimes reads as empirically established when it is merely proposed. Rename it **“Candidate intervention.”**

Algorithm 1 requires the Pydantic parsing correction discussed earlier.

> “pure function of (y, S)”

For your schemas this may be true. It is not true for arbitrary Pydantic models: custom validators can depend on external state or contextual inputs.

Scope the statement to your implementation and fixed environment.

> “we report the stripped revalidation alongside every rate”

You do not actually provide stripped revalidation beside every rate, particularly for the prompt conditions. Either add it or narrow the sentence.

The unreachable fallback branch should be removed from the release, unless retained explicitly for independent use with tests.

## Page 9 — Sub-taxonomy

> “heterogeneous in cause while homogeneous in remedy”

This contradicts the paper’s main example: character-class relaxation and length relaxation are different remedies.

More accurate:

> “The primary categories reflect validator reporting; sub-causes refine the intervention needed.”

### Leading-digit discussion

Replace the impossibility claims throughout.

### Type-prefixed identifiers

These can violate multiple conditions: colon/slash, capitalization, and length. Your sub-taxonomy should permit multiple annotations when appropriate.

### Length interpretation

Claims such as:

> “overrun deterministically as the fact count grows”

and:

> “reflects a format that conflicts with how the model was trained”

are not established by the experiment.

Use behavioral descriptions rather than unobserved training mechanisms.

### Semantic correctness

You say overlong financial answers are “substantively correct,” but the study explicitly does not evaluate answer correctness.

Either manually validate these cases and report the protocol, or say:

> “contain a calculation or explanatory derivation.”

## Page 10 — Sub-causes, cross-field analysis, validation

### Table 2

The listed counts sum correctly to 19. Clearly distinguish:

- Sub-causes observed in the perturbation subset.
- Sub-causes observed elsewhere.
- Hypothetical examples included for explanation.

### Cross-field denominator

You write:

> “The remaining 1,322 failures were rejected at field level.”

That cannot be accurate for all of them because the full corpus includes markdown wrappers and malformed JSON rejected before field validation.

Use:

> “did not reach the relevant model-level consistency checks.”

Also, if there are nested Pydantic models, some nested validators may execute even when a parent later fails. “Reached validator execution” needs a precise definition.

A cleaner denominator would count exposure to each individual consistency check.

### Human validation

You corrected four hand labels after inspecting error types or raw outputs and then report 144/144 agreement.

That is adjudicated agreement, not necessarily the original blind agreement.

Report separately:

1. Initial labels.
2. Initial disagreements.
3. Adjudication procedure.
4. Whether the code or definitions changed.
5. Final agreement.

For a taxonomy paper, an independent second annotator would materially strengthen the work.

## Page 11 — Precision and recall

### Census confidence intervals

You say census categories have no sampling uncertainty, then report Wilson intervals.

Both can be meaningful under different estimands:

- A census gives exact agreement on the fixed corpus.
- A binomial interval refers to an assumed broader population.

State which interpretation you intend. Wilson intervals do not measure uncertainty caused by annotator bias.

### Recall claims

The `schema_mirroring` screen using `"properties"` is not a superset of a detector that can fire on any two of fourteen keywords. You acknowledge this later, but the preceding unconditional language should be corrected.

Also, the short-preamble screen shows none were found **in this corpus**; it does not establish that the threshold is generally safe.

### “Every count is a lower bound”

This is true only if labels have no false positives and categories are defined compatibly with multilabel counting.

Safer:

> “Single-primary-label counts omit some co-occurring violations.”

### Pydantic ordering

Plurality depends on ordering only in ties; otherwise it depends on error multiplicity. Distinguish those sensitivities.

## Page 12 — Overall results and signatures

**Table 4’s individual rates are arithmetically consistent with the displayed counts.**

But the caption says:

> “both task domains pooled”

while GPT-4o-mini includes only HotpotQA. Add an explicit footnote in the table, rather than relying on later prose.

### Empty completion

Do not automatically interpret this as an ordinary model JSON-generation failure. Report:

- Stop/finish reason.
- Content-block types.
- Whether generation exhausted a limit.
- Whether visible text was absent in the provider response or lost during extraction.

It may be a model output issue, endpoint behavior, or extraction-layer issue.

### Four signatures

Restrict the claim to the basis actually shown: pooled models at the baseline tier. Show dataset-specific distributions before claiming replication across domains.

## Page 13 — Divergence and generational claims

### Divergence metric

The maximum category-share gap is an understandable descriptive statistic, but:

- It selects the most extreme contrast.
- It ignores most of the distribution.
- It lacks uncertainty.
- It uses another reporting basis.
- The two-vendor comparison is affected by configuration differences.

Consider using it as a secondary statistic rather than the abstract’s leading numerical claim.

> “both sides … are well powered”

You have not presented a power analysis. Twenty-four to forty-six failures are not automatically “well powered.”

Use “meet the reporting threshold.”

### Pilot inclusion

There is no compelling scientific reason for the headline divergence analysis to reintroduce excluded pilots. Use one primary reporting basis and place the alternative in sensitivity analysis.

### Generation claims

“Disappears” and “appears” should become:

> “was not observed” and “was observed.”

Zero instances in a finite sample do not establish disappearance.

Also, a comparison involving temperature-zero versus default sampling is not a clean generation-only comparison.

## Page 14 — Compound failures and perturbations

**Table 6’s arithmetic is correct.**

This is the paper’s best section, but the distinction should remain:

> otherwise schema-conformant

not:

> “otherwise correct.”

You did not evaluate semantic correctness.

Report uncertainty around the model-specific compound fractions. Sonnet’s 9.8% rests on four compound cases out of 41 wrappers.

### Perturbation design

You write:

> “which questions each model drew”

but earlier specify deterministic prefixes, not random draws. Explain whether different cells used different prefix lengths or whether “drew” refers to stochastic identifier choices.

Do not omit attempt-level rates simply because category shares are near 100%. Counts **and rates with uncertainty** are appropriate.

## Page 15 — Calibration and prompting

### Table 7

The counts sum correctly, but add attempt denominators directly:

- Baseline: 178 attempts.
- Relaxed tier: apparently 324, given the other reported totals.

Raw doubling of regex failures from 7 to 14 is not equivalent to a doubling of regex-failure incidence when attempt counts also increase substantially.

This substantially weakens the “redistribution” wording.

### Table 8

Add:

- Unique questions.
- Run counts.
- Common-question overlap.
- First-attempt results.
- Question-clustered intervals.
- Underlying post-strip violation rates.

The sixfold difference in denominators is not the only issue. Their construction differs: baseline combines main-sweep and debugging runs, whereas the variants may represent distinct batches.

## Page 16 — Repair budget and recommendations

### “Repair budget”

You have not measured:

- Repair latency.
- Additional tokens.
- Monetary repair cost.
- Engineering effort.
- End-to-end recovery under deployed repair policies.

Frame this as a **remediation profile**, or add operational measurements.

### Unsupported remedies

> “38 are schema mirroring and 8 are enumeration violations, both of which respond to prompt-level intervention”

You have not shown those interventions working for those categories. Say they **suggest candidate prompt-level interventions**.

### Extrapolation from Sonnet

Eighteen eliminated Sonnet length failures do not establish that a substantial fraction of all 590 observed length violations are schema-author errors.

### Recommendations

“Do not express length bounds inside a regular expression” is too absolute.

Better:

> “When diagnostic clarity matters, represent identifier length and character restrictions separately.”

The advice that patterns “must admit whatever names can begin with” is also wrong. A documented prefix or normalization scheme is a legitimate alternative.

## Page 17 — Model selection, cross-field findings, durability

### Stable model property

> “Dominant failure category is a stable property of a model in our data”

This needs qualification. You demonstrate changes under schema perturbation and have limited per-condition failure support.

Prefer:

> “Some models exhibit consistent dominant categories across the baseline conditions studied.”

### Model selection

A team should not choose solely by dominant-category share. A model with a low absolute rate of hard failures may be preferable to one dominated by formatting but with many more failures overall.

Show **residual invalidity after deterministic repair** on the same fixed completions, and clearly distinguish that from the performance of a rerun pipeline using the repair policy.

### Durability

This discussion repeats Section 5.3 almost verbatim. Cut it or condense substantially.

### Limitations

> “categories themselves … do not depend on our particular choices”

The generic error vocabulary may transfer; the adequacy of the chosen category boundaries has not been established across unrelated schemas.

Acknowledge that distinction.

## Page 18 — Limitations and conclusion

The limitations are unusually candid, which is a strength. But acknowledging a limitation does not neutralize an overclaim elsewhere.

For example:

- Fixed prefixes limit population inference.
- Unequal/default sampling limits generation comparisons.
- Nonindependent annotation limits validation.
- Custom schemas limit claims of model-intrinsic signatures.

Those restrictions need to appear in the **results language**, not only here.

### Conclusion

> “differ by a factor of five in what that category costs to repair”

You measured a roughly 5.6-fold ratio in compound-failure fractions, not a fivefold cost ratio.

Replace it with the observed quantities.

> “A practitioner told only the category could not have predicted the difference.”

Again, too strong. The narrower, useful claim is that sub-causes identify which part of a category a relaxation addresses.

## Page 19 — References and release

Before submission:

- Verify all references and their descriptions.
- Cite HotpotQA and FinanceBench.
- Cite relevant implementation documentation where claims depend on Pydantic or provider guarantees.
- Make preprint labeling consistent.
- Include an anonymized repository or supplementary archive.

A release should contain:

- Exact schemas and prompts.
- Cell manifest and question IDs.
- Dependency lockfile.
- Model request settings and timestamps.
- Raw provider-response metadata where safe and permitted.
- Attempt/run/retry linkage.
- Classifier tests.
- Analysis scripts that reproduce every table.
- Original and adjudicated annotation labels.

Check dataset and provider terms before redistributing prompts, evidence passages, or raw outputs. Anonymize anything that could reveal authorship during double-blind review.

---

# 4. What I would change before submission

## Priority 1 — Correct the manuscript’s factual foundation

These do not require new inference calls:

1. Replace the unsatisfiability argument.
2. Correct constrained-decoding claims.
3. Correct Pydantic parsing and list-item validation claims.
4. Reconcile the Haiku denominator.
5. Explain 18 perturbation failures versus 17 identifier-failing attempts.
6. Clarify whole-output versus field lengths.
7. Replace “repair cost,” “clusters,” “stable model property,” and causal language where unsupported.
8. Verify model identifiers and references.

## Priority 2 — Reanalyze the existing corpus

This may recover much of the paper’s credibility without large additional cost:

1. Create one auditable cell manifest.
2. Separate initial attempts from retries.
3. Report per-node and end-to-end results.
4. Use one main inclusion basis.
5. Report per-domain profiles.
6. Revalidate all applicable stored outputs under:
   - strict parsing;
   - deterministic wrapper removal;
   - alternative schemas.
7. Measure underlying length violations across every prompt variant.
8. Add question-clustered uncertainty and dominant-profile stability analysis.
9. Test sensitivity to classification precedence and plurality.

## Priority 3 — Add focused new evidence

If budget permits, I would prioritize these over adding more model names:

### 1. Matched prompt ablation

Run the same questions under all prompt variants, with matching settings and a balanced number of runs.

### 2. Independent annotation

Use at least two annotators for a held-out set. Include ambiguous examples and valid outputs, not only predicted failures.

### 3. A small held-out schema evaluation

Apply the taxonomy to schemas not used in its development. This directly tests the claim that it is more than a classification layer tailored to three custom node models.

### 4. An actual repair-policy comparison

On matched runs, compare:

- Strict parser.
- Fence stripping plus validation.
- Fence stripping plus targeted repair.
- Current generic error-feedback retry.

Measure final validity, attempts, tokens, and latency. That would turn the “repair budget” framing into demonstrated practical value.

A native structured-output baseline could also be helpful, but it is not logically required if you keep the prompt-only scope narrow and accurately motivated.

---

# 5. Recommended reframing

The current manuscript’s broad claim is approximately:

> Models have stable failure signatures; our taxonomy identifies causes and predicts repair cost.

Your evidence more convincingly supports:

> **In a prompt-and-validate pipeline, strict validity conflates surface-format defects with underlying schema violations. A deterministic, layered analysis reveals substantial compound failure and distinguishes which violations selected repairs or schema changes address.**

That is narrower, but scientifically stronger.

I would organize the paper around three contributions:

1. **A layered conformance-analysis method**, separating strict validity, recoverable formatting, and underlying validator failures.
2. **An empirical study of compound failures**, including how wrapper removal changes residual invalidity across configurations.
3. **Matched intervention analyses**, distinguishing mechanical revalidation effects from generation changes.

The maximum 72.9-point divergence and four dominant-category groups can remain descriptive secondary findings.

# Bottom line

**There is a publishable idea here, but I do not think the current draft is ready for TMLR.** A skeptical reviewer can presently challenge the opening example, the decoder comparison, the classifier specification, and the experimental interpretation before reaching your strongest result.

My strongest advice is: **do not spend the next revision mainly polishing sentences.** Fix the technical claims, reconcile the experimental bookkeeping, and center the paper on compound failures and measured remediation. Those changes would make a much larger difference to its review prospects than more expansive claims or additional model coverage.