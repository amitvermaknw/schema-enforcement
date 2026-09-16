**Yes—this is a meaningful improvement over the first draft.** The main argument is clearer, several important technical corrections have been made, and the new analysis of violations hidden beneath markdown fences is substantially more useful than the original “failures migrate” story.

**However, I still would not submit this version to TMLR.** There are several concrete inconsistencies, including a potentially serious field-length error, contradictory statements carried over from the previous draft, and an experimental-cell count that does not reconcile with the newly stated design.

My assessment has moved from **“interesting idea with major technical problems”** to **“promising empirical paper whose analysis and reporting still need consolidation.”** That is real progress—but not yet submission readiness.

I reviewed the supplied 23 pages. As before, this is a manuscript-level review; I cannot authenticate the model endpoints, references, code, or newly reported revalidation results from the PDF text alone.

# 1. What improved—and deserves to stay

| Issue in the first draft | Assessment of the revision |
|---|---|
| Compound failures were secondary | **Much improved.** They now provide the central motivation. |
| Prompting supposedly moved failures into length errors | **Important new analysis.** Checking hidden length violations was the right response. However, the new “unchanged” conclusion is too strong. |
| Grammars supposedly cannot enforce regex/length constraints | **Corrected well in Sections 1–2**, but the old argument survives elsewhere. |
| Pydantic parsing exception was incorrect | **Corrected in the algorithm and mapping**, but one contradictory sentence remains. |
| Classifier could label valid objects as failures | **Substantially addressed** by explicitly classifying only already-invalid attempts. |
| Haiku deduplication used incompatible denominators | **Corrected.** The HotpotQA-only comparison is now consistent. |
| “Four clusters” were not statistical clusters | **Improved in Section 5.2**, but the conclusion still calls them clusters. |
| Length-ablation counts were compared despite unequal exposure | **Improved.** Table 7 now includes rates. |
| Regeneration was confused with mechanical revalidation | **Improved in principle.** You now report both—but the field-length inconsistency needs resolution. |
| Perfect annotation agreement obscured classifier development | **Much more transparent.** Development-set limitations are now explicit. |
| Haiku dominated pooled statistics | **Acknowledged and partially addressed** with macro-averaging. |

The strongest substantive improvement is this:

> **A rise in a primary error category need not represent an increase in its underlying violation prevalence when an earlier-precedence category becomes less frequent.**

That is a defensible and useful methodological point. I would preserve it, but avoid claiming more than the data establish.

---

# 2. Critical issue: some “overlength” fields are shorter than the cap

This is the first issue I would resolve, before editing anything else.

On page 5:

> “coverage_notes … field lengths of 214–315 characters against a 250-character cap”

On page 17:

> “nine coverage_notes violations at 214–315 characters against the 250-character cap”

A **214-character field cannot violate a maximum length of 250 characters**. With the stated minimum of 20, it also does not violate the lower bound.

This is repeated in Sections 3.2, 5.5, 6.1, and 6.2. It is not a harmless wording problem because the corrected length measurements support your new counterfactual argument.

Possible explanations include:

- You measured the wrong field.
- The range includes conforming fields from attempts that failed elsewhere.
- The applied cap differs from the reported cap.
- A custom validator uses a different measure.
- The range was transcribed incorrectly.
- The attempt was classified by a different error than the one being described.

**Do not guess which explanation applies. Audit the 18 attempts.**

Produce a small supplementary table:

| Attempt ID | Node | Error location | Error type | Measured field length | Applied bound | Valid under original schema? | Valid under relaxed schema? |
|---|---|---|---|---:|---:|---|---|

Then regenerate every related claim.

Also verify:

> “The model exceeds the summary cap by about 15% on average…”

Does this average use only actual violating fields? Does it include the allegedly 214-character example?

**Until this is reconciled, I would not trust the length-ablation interpretation.** That does not mean the result is wrong; it means the manuscript currently does not establish it consistently.

---

# 3. The number of experimental cells does not reconcile

The new design statement on page 5 says:

> “All nine models are run at the medium tier on both task domains…”

That implies **18 medium-tier cells** in the full corpus.

You also report:

- Sonnet 4.6 at `medium_v2`: at least **1 additional cell**.
- Sol at `medium_v3_loose_regex`: **1**.
- Terra at `medium_v3_loose_regex`: **1**.
- Luna at `medium_v3_loose_regex`, excluded pilot: **1**.

That gives **at least 22 full-corpus cells**, not 20.

After excluding the two pilots, there would be **at least 20 reported configurations**, not 18. If Sonnet’s relaxed tier covers both domains, the discrepancy grows.

Therefore, at least one of these statements must be incorrect:

1. Every model was run on both domains at the medium tier.
2. The full corpus contains 20 cells.
3. The reporting basis contains 18 configurations.
4. The stated cell definition.

This is exactly why a complete cell manifest is necessary. Add it to the paper or appendix:

```text
model
schema variant
dataset
prompt variant
unique questions
runs
attempts
failures
collection batch
included in main results?
```

The manuscript currently makes the design sound more complete than the cell counts permit. Fixing this is more important than adding further interpretation.

---

# 4. The new prompt-ablation conclusion overcorrects

The new table reports:

| Condition | Underlying length-violation rate |
|---|---:|
| Baseline | 37.8% |
| Aggressive | 30.2% |
| Few-shot | 36.9% |

You repeatedly conclude:

> “The underlying behaviour is unchanged.”

and:

> “a length-violation rate it did not touch.”

That is **not established**.

The aggressive condition is **7.6 percentage points lower** than baseline. The few-shot condition is close to baseline, but descriptive similarity is not evidence of equivalence.

Moreover, the conditions:

- Were collected in different batches.
- Have unequal numbers of runs and attempts.
- May differ in question exposure.
- Include model-dependent retry mixtures.
- Are not paired observations of the same completions.

Your analysis establishes something narrower and valuable:

> **The monotonic rise in primary `length_bound` rates does not correspond to a monotonic rise in detected underlying length violations.**

It does **not** establish:

- That prompting has no effect on underlying length.
- That all changes are caused exclusively by classifier precedence.
- That the same individual violations were simply uncovered.
- That the conditions are equivalent.

### Suggested replacement paragraph

> Primary `length_bound` rates increase from 14.3% to 22.7% across the prompt conditions, but rates including violations beneath wrappers are 37.8%, 30.2%, and 36.9%. Thus, the increase in the primary category does not support an interpretation that underlying length violations increased. The baseline and few-shot point estimates are similar, while the aggressive condition is lower. Because the conditions have unequal exposure and were collected in different batches, we do not establish equivalence or isolate the causal effect of prompting on underlying length.

Use that qualification in the abstract, introduction, discussion, and conclusion—not only in limitations.

### Another important measurement question

Table 8 labels the row:

> “Length violations (all)”

But its definition is **primary length errors plus length errors found beneath fences**.

Does it include length errors that co-occur with an unwrapped, regex-primary failure? What about length errors under prose preambles?

If not, “all” is inaccurate. Use:

> **Detected length violations: primary or beneath fences**

Or inspect the complete error lists and actually count every detected length violation.

---

# 5. A new count inconsistency in the prompt experiment

On page 18:

> “primary length failures run 154/1,066, 31/189 and 40/176”

But:

\[
154/1066 \approx 14.45\%,
\]

which rounds to **14.4%**, not the **14.3%** in Table 8.

Your previous draft reported **152** baseline length failures:

\[
152/1066 \approx 14.26\%,
\]

which does round to 14.3%.

Reconcile whether the count is 152 or 154, then regenerate the table and downstream totals.

This illustrates a broader problem: numerical claims appear to have been updated manually in some places but not others. Ideally, counts and percentages should be inserted from one generated results file.

---

# 6. Several corrected arguments still coexist with the old incorrect ones

This is now one of the manuscript’s biggest presentation problems. The revision reads partly like a corrected paper and partly like the old paper with rebuttal paragraphs inserted.

## A. The 3M impossibility claim remains

The opening correctly acknowledges `company_3m`.

But page 10 still says:

> “every lowercase snake_case rendering a model might reasonably choose … violates the anchor … and no amount of instruction-following competence recovers it.”

That directly contradicts page 1.

Also, the new opening says:

> “had no way to infer that the schema wanted a different one.”

That is still too strong. The model is given the schema, which signals that `3m` is invalid. What is missing is a **preferred normalization policy**, not all information needed to produce a conforming identifier.

Use:

> “The prompt does not specify which conforming normalization convention to use.”

Similarly, on page 19:

> “the model cannot infer that convention from the pattern”

should become:

> “the pattern does not uniquely specify a normalization convention.”

## B. The constrained-decoding error remains in Section 6.4

Page 20 says:

> “we have softened the claim to length and pattern constraints accordingly.”

But length and pattern constraints are precisely the constraints you correctly explain as enforceable in Section 2.

Delete or rewrite this paragraph. The discussion should not reintroduce the argument the related-work section explicitly rejects.

## C. Tool-forcing is still equated with constrained decoding

Page 6:

> “OpenAI’s response_format … or Anthropic tool-forcing. These implement constrained decoding…”

This remains insufficiently qualified. Tool selection, tool-argument generation, and strict schema enforcement are distinct facilities.

A safer statement is:

> “We exclude vendor-native structured-output and tool-use configurations, whose enforcement mechanisms and guarantees depend on the endpoint and settings.”

## D. The wrong exception remains in Section 4.2

Page 8:

> “a fenced output raises JSONDecodeError.”

Your updated Section 3.4 and Algorithm 1 correctly describe `ValidationError` with `json_invalid`.

Fix the remaining sentence.

## E. “Clusters” survives after being explicitly rejected

Page 14 says the groups are not statistical clusters.

Page 22 says:

> “models cluster into four signatures”

Page 6 also refers to:

> “our signature clusters”

Use **observed dominant-category profiles** consistently.

## F. D3 contradicts Section 4.4

D3 says categories are separated where remedies differ, with same-remedy sub-causes kept together.

Section 4.4 now correctly says:

> “single categories because that is the granularity the validator reports at, not because one intervention addresses each”

These are different design principles.

Rewrite D3 to match the implemented taxonomy:

> **Diagnostic usefulness.** Primary categories summarize surface behavior or validator error families; sub-cause annotations refine the interventions relevant to each family.

---

# 7. Cross-node consistency is not inexpressible in this paradigm

On page 5:

> “Cross-node referential integrity is the constraint class this paradigm most clearly cannot express…”

Page 22 repeats:

> “testing it would require validation machinery outside the schema.”

This is incorrect for a prompt-and-validate pipeline.

Pydantic validation can receive context, and custom validators can inspect previously validated identifiers supplied through that context. For example, the application can call:

```python
GatherOutput.model_validate_json(
    completion,
    context={"allowed_entity_ids": previous_entity_ids},
)
```

A validator can then check membership using that contextual information.

Alternatively, an application-level validation step can perform the check. Either approach remains within the broader prompt-and-validate paradigm.

The correct limitation is:

> **Our implementation does not validate cross-node referential integrity.**

Not:

> **This paradigm cannot express cross-node referential integrity.**

That distinction matters. Avoid converting an unimplemented feature into a fundamental limitation.

---

# 8. Statistical limitations are acknowledged, but not resolved

The new limitations section is candid. However, statements such as:

> “A first-attempt-only analysis … [is] the most important extension of this work”

will likely prompt a reviewer to ask:

> Why is an analysis necessary for interpreting the existing comparisons deferred when the required attempt records already exist?

Likewise:

> “the per-dataset replication … is not reported here”

is not a strong final position for a paper that uses two-domain coverage as supporting evidence.

## What should be added before submission

### First-attempt results

At minimum, report first-attempt validity and composition by node.

Remember that downstream first attempts are still conditioned on reaching the node. The identify node provides the cleanest initial comparison; other nodes need their reachability denominator.

### Run-level outcomes

You have run IDs, retry logic, and attempt records. If possible, report:

- Fraction of runs completing all three nodes.
- Attempts per completed run.
- Retry success rates.
- Abandonment stage.

### Per-domain distributions

Do not rely on pooled tables to claim replication across datasets.

### Question-clustered uncertainty

Calling attempt-level Wilson intervals “indicative” does not repair their independence assumption.

For your descriptive pipeline estimands, resample whole question clusters, carrying their runs and retries together. Clearly explain what uncertainty this estimates and what fixed-prefix sampling still prevents you from claiming.

### Do not infer significance from interval overlap

Page 13 says:

> “have overlapping intervals and are not distinguishable…”

Overlap of individual confidence intervals is not itself a test of a pairwise difference. And the intervals already ignore dependence.

Prefer:

> “We do not establish an ordering within these groups.”

Also remove:

> “both sides … are well powered”

unless you supply an actual power argument.

---

# 9. The model-selection discussion contains a misleading tradeoff

On page 20:

> “a team comparing them trades a higher volume of cheaply repaired failures against a lower volume of expensive ones.”

The reported numbers do not show a compensating tradeoff between Haiku and Sonnet. On these stored outputs, Sonnet has both lower strict failure and lower residual invalidity after fence removal.

Using your tables:

| Model | Original failures | Recovered by fence removal | Residual invalidity on stored attempts |
|---|---:|---:|---:|
| Sonnet 5 | 67 | 37 | \(30/313 = 9.6\%\) |
| Haiku 4.5 | 878 | 290 | \(588/1329 = 44.2\%\) |

These are **offline revalidation rates on the observed attempt sets**, not forecasts of rerunning the pipeline with fence repair: adding repair would change which retries and downstream attempts occur.

Still, this is a clearer operational result than the current prose.

For the full reporting corpus:

\[
(1126-327)/3997 = 20.0\%
\]

remain invalid after repairing the pure markdown-wrapper cases, compared with 28.2% initially.

Consider adding this analysis explicitly, with the offline qualification.

Also, a dominant category is not inherently “more actionable than a failure rate.” **Absolute residual rates and category composition are complementary.** Your new central argument already demonstrates why neither should replace the other.

---

# 10. Further numerical and wording corrections

These are smaller individually, but together they affect credibility.

### “More than half” is incorrect

Conclusion:

> “Prompt variants reduced markdown wrapping by more than half…”

From 48.5% to 25.0% is approximately a **48.5% relative reduction**, not more than half.

Use:

> “reduced markdown wrapping by 23.5 percentage points, or nearly half.”

### “Over half the corpus” uses the wrong denominator

Page 19:

> “590 instances … which is over half the corpus.”

590 is:

- **52.4% of the 1,126 failing attempts**;
- **14.8% of the 3,997 total attempts**.

Write “over half of failing attempts.”

### “All six groupings” is inconsistent

Page 14:

> “All six groupings are drawn from the medium tier…”

Table 5 contains **four** profiles. The six qualifying divergence groups are a different object, and one of those is `medium_v2`.

### “Two of the four” small groups is also inconsistent

The profile sizes are:

- Markdown: 2 models.
- Regex: 4.
- Length: 2.
- Mirroring: 1.

Thus **three** profiles contain one or two models, not two.

### The macro-average has a different basis

The 16.7% macro-average appears to use the nine **medium-tier** model rates in Table 4, while 28.2% includes the reported schema variants.

State that explicitly:

> “At the baseline medium tier, the unweighted mean of the nine model-level rates is 16.7%.”

Do not present them as two weightings of an otherwise identical configuration set.

### Token-budget causality is overstated

You appropriately write:

> “reasoning appears to have consumed the entire output budget…”

because stop reason and content-block types were not logged.

But later call it:

> “a concrete consequence of the token-ceiling asymmetry”

That is stronger than the evidence. Use:

> “consistent with exhaustion of the configured output budget.”

### “No validity rate distinguishes them” is too absolute

The abstract says:

> “No validity rate distinguishes them…”

Their strict failure rates already differ substantially, and a post-repair validity rate also distinguishes them.

What you mean is:

> “Strict validity alone does not reveal this difference in repairability.”

### Field-level rejection remains incorrect

Section 4.5 still says all 1,322 non-validator-reaching failures:

> “were rejected at field level.”

Many are rejected during JSON parsing. Use:

> “did not reach the relevant model-level consistency checks.”

---

# 11. Claims that still go beyond your evidence

## Semantic correctness

You still describe overlong financial responses as:

> “substantively correct”

But you explicitly do not evaluate extraction or answer correctness.

Either audit those cases and report the procedure, or describe them as:

> “containing a calculation or explanatory derivation.”

Adding a citation about format restrictions does not validate the correctness of your outputs.

## Training mechanisms

Statements such as:

> “reflects a format that conflicts with how the model was trained”

and:

> “Only the first is likely to yield to prompt engineering”

remain speculative.

Your experiment measures output behavior, not training mechanisms. Mark these as hypotheses or remove them.

## Disappearance across generations

You still write:

> “schema mirroring is gone”

and:

> “Modes do disappear.”

Use:

> “Schema mirroring was not observed in the newer configurations we tested.”

The generation comparisons also remain confounded by different sampling settings and potentially different exposure.

## “Miscalibrated”

Section 5.5 now gives a reasonable caveat: a cap may reflect a genuine downstream requirement.

But the limitations section returns to:

> “demonstrably miscalibrated”

The experiment demonstrates a constraint–output mismatch, not that the application requirement was wrong.

Use **binding**, **restrictive**, or **below observed output lengths**, unless you independently justify the chosen calibration target.

## “Repair budget”

The heading remains:

> “A repair budget rather than a failure rate”

But you do not measure repair latency, tokens, monetary cost, or engineering effort.

Rename it:

> **A remediation profile beyond the strict failure rate**

---

# 12. Classifier validation: improved transparency, still limited evidence

This section is much better than before. In particular, admitting that the labeled examples were used to correct the classifier is scientifically appropriate.

However, distinguish three quantities clearly:

1. **Original classifier versus original labels:**  
   131/144 agreement, approximately **91.0%**.

2. **Corrected classifier versus original labels:**  
   140/144, or **97.2%**.

3. **Corrected classifier versus adjudicated labels:**  
   144/144.

The second is not independent validation of a frozen classifier. Your limitations acknowledge this, but the headline phrase “blind agreement” can still obscure that the classifier was revised using those examples.

I would use a provenance table rather than several paragraphs explaining the sequence.

Also:

> “the adjudicated figure … measures whether the classifier is right”

is too strong. It measures agreement with the adjudicated operational reference, produced within the same development process.

### Remaining classifier concerns

- Numeric type errors are still mapped to `range_bound`.
- Nonnumeric type errors are still mapped to `missing_field`.
- Arbitrary non-regex custom validator messages still become `cross_field_ref`.

Those mappings remain semantically weak for a taxonomy presented as broadly applicable.

The validation-first precondition resolves false labeling of **valid** objects with `title` and `description`, but an **invalid ordinary instance** containing those keys can still be mislabeled as schema mirroring. Add adversarial unit tests for this boundary.

A held-out annotation set with an independent annotator would materially strengthen the submission.

---

# 13. Reproducibility still needs concrete artifacts, not just promises

The following remain missing from the supplied text:

- A complete cell manifest.
- Exact prompt texts and retry messages.
- Full Pydantic schema definitions.
- Pydantic and dependency versions.
- Question IDs and dataset revisions.
- Dataset citations for HotpotQA and FinanceBench.
- Collection dates.
- Clear endpoint provenance.
- An anonymized artifact link.

The unusual model identifiers still need documentation. I cannot verify them from the manuscript. If they are aliases supplied by a proxy or internal service, state that explicitly.

Also:

> “We record the version the provider resolved each alias to, rather than relying on the alias”

is inaccurate when the provider simply returns the same alias. That records a response identifier, not necessarily a pinned model version.

A useful table would distinguish:

```text
requested identifier
returned identifier
pinned snapshot available?
provider/API route
collection dates
sampling settings
```

---

# 14. The paper is longer, but not yet more efficient

The increase from 19 to 23 pages is not itself a problem. The issue is that much of the additional text explains why claims must be limited, while the original strong claims remain elsewhere.

Examples:

- The decoder distinction is explained repeatedly.
- The same Haiku/Sonnet percentages appear throughout.
- The generation-durability argument is repeated.
- The perturbation rationale is restated in results, discussion, and limitations.
- Several paragraphs sound like responses to a reviewer rather than a clean final presentation.

Phrases I would reduce include:

> “We want to be precise…”  
> “the obvious argument is wrong”  
> “unsurprising rather than suspicious”  
> “earns its place”  
> “we do not minimise it”

Replace these with direct methodological statements.

You do not need to narrate every revision in the final paper. State the corrected method once, report the evidence, and keep the limitations proportional.

---

# 15. My recommended next revision

## Must fix before submission

1. **Audit the 214–315-character “violations.”**
2. **Reconcile the experimental-cell counts.**
3. **Fix 152 versus 154 primary length failures.**
4. **Remove the remaining impossibility, decoder, and Pydantic contradictions.**
5. **Replace “underlying behavior unchanged” with the narrower supported claim.**
6. **Provide first-attempt and per-domain analyses.**
7. **Document model provenance and experimental artifacts.**

## Strongly recommended

8. Add question-clustered uncertainty.
9. Report offline residual invalidity after deterministic repair.
10. Add independent, held-out classifier validation.
11. Test sensitivity to primary-label precedence and aggregation.
12. Consolidate repeated discussion and limitations.

## A safer central claim

I would frame the paper around:

> **Primary failure labels can distort comparisons when violations co-occur. Revalidating recoverable surface-format failures reveals residual schema violations and prevents an apparent increase in a primary category from being mistaken for increased underlying violation prevalence.**

That is stronger scientifically than claiming the model behavior was unchanged, and it fits your most useful evidence.

# Final assessment

**Does it improve? Yes, substantially in framing, transparency, and diagnostic analysis.**

**Do important issues remain? Yes.** Some are simple remnants of the previous draft, but the field-length inconsistency, cell-count mismatch, and unsupported equivalence claim are substantive.

**Would I now recommend acceptance at TMLR? Not yet.** My main concern would no longer be that the paper lacks an interesting idea. It would be whether the numerical reporting and experimental interpretation are reliable enough to support that idea.

The next revision should focus less on adding explanations and more on **auditing the data, producing the missing analyses, and making every section agree with the corrected results**.