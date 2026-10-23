# Artifact: Why Does Structured Output Fail?

Code, data and analysis for *Why Does Structured Output Fail? An Empirical
Study of Prompt-Enforced Pydantic Schemas Across Nine LLMs*.

Archived version (release `emse-submission`): https://doi.org/10.5281/zenodo.23586834

Every number in the paper is regenerated from one locked SQLite database by
the scripts in this repository; none is typed by hand. Reproducing them needs
no API keys and makes no model calls.

## Quick start

Requirements: Python 3.12 (`python3.12` on `PATH`), `make`, macOS or Linux.

```bash
make install   # creates .venv from requirements-lock.txt
make repro     # regenerates every number and runs every check below
```

`make repro` ends with:

```
repro OK: all numbers regenerated and all checks passed
```

It fails, with a non-zero exit, if any of the following does not hold:

| Check | Expected |
|---|---|
| Locked database SHA-256 | `d0f406f00882dadb4c0aa0b1bea3a4a77b562c80ec46f19fe7d6ad7d4ebfbeb4` |
| Golden invariants in `scripts/make_paper_numbers.py` | all agree with the database |
| `lint-numbers`: no hard-coded or unknown numbers in the paper source | `lint OK` |
| Classifier re-run over every failed attempt (on a copy of the database) | 1,326 examined, 0 to update |
| Validator re-run over every stored completion | 4,396 checked, 4,396 agree |
| Fence-strip outcomes recomputed for every wrapped failure (on a copy) | 379/789 pure formatting, 410/789 compound, 0 unstrippable |

Regenerated files land in `paper/generated/`. Against the committed copies, the
only expected differences are provenance fields (commit hash, timestamps).

Run `make help` to list the individual targets.

## What is here

The paper reports **3,997 generation attempts** across 18 configurations,
drawn from a full corpus of 4,396 attempts. Every attempt, including retries,
is stored with its raw completion, validation outcome, error details and
assigned category.

| Item | Location |
|---|---|
| Results database (authoritative record) | `results/archive/paper1_FINAL_DATA_locked_v4_20260913.db` |
| Failure classifier (Stage-1 predicates, Stage-2 mapping) | `src/schemaeval/errors.py` |
| Schemas: baseline and the two variants | `src/schemaeval/schemas/` |
| Prompt variants (baseline, aggressive, few-shot) | `src/schemaeval/prompts.py` |
| Pipeline (three-node sequential, strict-repair loop) | `src/schemaeval/topologies/`, `src/schemaeval/paradigms/` |
| Hand-label record (144 blind labels) | `hand_labels` table in the database |
| Analysis producing every `\pn{}` number | `scripts/make_paper_numbers.py`, `scripts/review3.py` |
| Paper source | `paper/` (`main_emse.tex`) |

**Release.** The release tag and archived DOI are given in the paper's data
availability statement.

## Environments

| File | Contents | Use |
|---|---|---|
| `requirements-lock.txt` | exact versions | reproducing the paper's numbers (`make install`) |
| `requirements.txt` | minimum versions | extending the harness or collecting new data (`make install-latest`) |

`requirements-lock.txt` is the **analysis** environment, verified by a
clean-clone reproduction. It is not the environment used for data collection;
the client SDK versions at collection time were not recorded, as the paper's
appendix on validator and client versions states.

## Running the steps by hand

`make repro` runs these commands; they can also be run directly from an
activated environment.

```bash
export DB=results/archive/paper1_FINAL_DATA_locked_v4_20260913.db

python scripts/review3.py numbers --db $DB --out paper/generated --repo .
python scripts/make_paper_numbers.py     # merges, checks golden invariants, writes paper_numbers.json
python scripts/render_paper_assets.py    # numbers.tex, keys.txt, tables, figure
python scripts/lint_numbers.py           # fails on hard-coded or unknown numbers

# first-attempt audit
python scripts/review3.py audit --db $DB --out audit_review3.md

# counterfactual revalidation of the relaxed-caps result
python scripts/review3.py counterfactual --db $DB --pythonpath src \
  --medium identify=schemaeval.schemas.medium:IdentifyOutput,gather=schemaeval.schemas.medium:GatherOutput,answer=schemaeval.schemas.medium:AnswerOutput \
  --v2 identify=schemaeval.schemas.medium_v2:IdentifyOutput,gather=schemaeval.schemas.medium_v2:GatherOutput,answer=schemaeval.schemas.medium_v2:AnswerOutput \
  --fresh-attempts 324 --fresh-failures 24
```

**Classifier reclassification check.** `scripts/reclassify_all.py` re-runs
the two-stage classifier over every failed attempt's stored output and error
details. `--apply` writes to the database, so run it on a copy only:

```bash
cp $DB /tmp/reclass_check.db
DB_PATH=/tmp/reclass_check.db python scripts/reclassify_all.py --dry-run
# expected: Total rows examined: 1326, Rows to update: 0
```

**Validator revalidation check.** `scripts/revalidate_all.py` revalidates
every stored completion against its node schema under the installed Pydantic
and compares the result with the stored `validation_ok`. It opens the
database read-only:

```bash
python scripts/revalidate_all.py --db $DB
# expected: checked: 4396, agree: 4396, exit 0
```

**Fence-strip revalidation.** Outcomes for every markdown-wrapped failure are
stored in the `markdown_wrap_revalidation` table. `scripts/fence_strip_revalidation.py`
recomputes them. It reads the database named by `DB_PATH` (default
`results/experiments.db`, which is not part of this artifact), and `--apply`
writes to it, so point it at a copy:

```bash
cp $DB /tmp/fence_check.db
DB_PATH=/tmp/fence_check.db python scripts/fence_strip_revalidation.py --dry-run
```

This covers all 789 wrapped failures in the full corpus; the paper reports the
subset on its reported basis (baseline prompt, pilot cells excluded).

## Building the PDF

Requires a LaTeX installation:

```bash
make paper     # latexmk -pdf main_emse.tex in paper/
```

`paper/main.tex` is an earlier version of the manuscript, kept for the record.

## Database schema

| Table | Contents |
|---|---|
| `runs` | one row per question run: model, schema tier, dataset, prompt variant, question, timestamp, `graph_success` |
| `node_attempts` | one row per generation attempt: node, `attempt_num`, `raw_output`, `validation_ok`, `primary_category`, `all_categories`, `error_details`, `resolved_model_version` |
| `node_runs` | per-node summary: tokens, repairs, latency |
| `hand_labels` | 144 blind human labels with adjudication notes |
| `markdown_wrap_revalidation` | fence-strip outcome for every wrapped failure |

`node_attempts.attempt_num` starts at 0 for the first attempt; retries follow
only on failure, so no attempt is logged after a valid one in the same run-node.

## Regenerating the corpus (optional, costs money)

Only needed to collect new data. Requires API keys for both vendors.

```bash
make install-latest
cp .env.example .env     # add OPENAI_API_KEY and ANTHROPIC_API_KEY
make pilot
```

Models are called through each vendor's own API with the parameters recorded
in the paper's appendix.

## Datasets

**HotpotQA** (Yang et al., EMNLP 2018), distractor configuration, validation
split, first records in dataset order. Distributed by its authors under
CC BY-SA 4.0.

**FinanceBench** (Islam et al., arXiv:2311.11944), the public
`PatronusAI/financebench` sample, first records in dataset order, evidence
truncated to 2,000 characters.

**FinanceBench question text is included in this artifact**, in
`paper/generated/question_manifest.csv` and in the `runs.question` column of
the locked database (it may also appear in `node_attempts.raw_output`). It is
redistributed under the dataset's CC BY-NC 4.0 licence; see `DATA_LICENSES.md`.
`src/schemaeval/data/financebench.py` regenerates the inputs from the original
source.

## Layout

```
src/schemaeval/
  schemas/        medium (baseline), medium_v2 (relaxed caps),
                  medium_v3_loose_regex (loosened identifier pattern)
  paradigms/      strict_repair.py — prompt, validate, retry with the error
  topologies/     sequential.py — identify -> gather -> answer
  data/           HotpotQA and FinanceBench loaders
  errors.py       the failure classifier
  prompts.py      the three system-prompt variants
  db.py           SQLite logging

scripts/          analysis and paper-number generation (see above)
paper/            LaTeX source; paper/generated/ is script output
results/archive/  the locked results database
tests/            fixture builder for smoke-testing the analysis
```

## Licence

Code and analysis outputs: MIT, see `LICENSE`. Third-party datasets keep their
own licences, as noted above.
