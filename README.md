# Artifact: a fine-grained failure taxonomy for prompt-enforced Pydantic schemas

Code, data and analysis for the TMLR submission *When "JSON Only" Isn't Enough:
A Fine-Grained Failure Taxonomy for Prompt-Enforced Pydantic Schemas Across LLM
Families*.

Anonymised for double-blind review.

## What is here

The paper reports **3,997 generation attempts** across 18 configurations, drawn
from a full corpus of 4,396 attempts. Every attempt, including retries, is
stored with its raw completion, validation outcome, error details and assigned
category. Every number in the paper is regenerated from that database by the
scripts below; none is typed by hand.

| Item | Location |
|---|---|
| Results database (authoritative record) | `results/archive/paper1_FINAL_DATA_locked_v4_20260913.db` |
| Failure classifier (Stage-1 predicates, Stage-2 mapping) | `src/schemaeval/errors.py` |
| Schemas: baseline and the two variants | `src/schemaeval/schemas/` |
| Prompt variants (baseline, aggressive, few-shot) | `src/schemaeval/prompts.py` |
| Pipeline (three-node sequential, strict-repair loop) | `src/schemaeval/topologies/`, `src/schemaeval/paradigms/` |
| Hand-label record (144 blind labels) | `hand_labels` table in the database |
| Analysis producing every `\pn{}` number | `scripts/make_paper_numbers.py`, `scripts/review3.py` |
| Paper source | `paper/` |

**Database identity.** sha256 begins `d0f406f00882`. Verify with:

```bash
shasum -a 256 results/archive/paper1_FINAL_DATA_locked_v4_20260913.db
```

**Analysis version.** This archive is the repository at tag `tmlr-submission`.
The commit hash recorded by the analysis scripts is printed in Appendix A of the
paper; resolve it with `git rev-parse tmlr-submission` in the source repository.

## Reproducing the paper's numbers

No API keys and no model calls are needed: the analysis runs entirely against
the stored database.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DB=results/archive/paper1_FINAL_DATA_locked_v4_20260913.db

python scripts/review3.py numbers --db $DB --out paper/generated --repo .
python scripts/make_paper_numbers.py     # merges and writes paper_numbers.json
python scripts/render_paper_assets.py    # numbers.tex, keys.txt, tables, figure
python scripts/lint_numbers.py           # fails on hard-coded or unknown numbers
```

`scripts/make_paper_numbers.py` checks a set of golden invariants and exits
non-zero if any disagrees with the database.

Other analyses reported in the paper:

```bash
# first-attempt audit behind Appendix E
python scripts/review3.py audit --db $DB --out audit_review3.md

# counterfactual revalidation of Section 4.3 (needs pydantic)
python scripts/review3.py counterfactual --db $DB --pythonpath src \
  --medium identify=schemaeval.schemas.medium:IdentifyOutput,gather=schemaeval.schemas.medium:GatherOutput,answer=schemaeval.schemas.medium:AnswerOutput \
  --v2 identify=schemaeval.schemas.medium_v2:IdentifyOutput,gather=schemaeval.schemas.medium_v2:GatherOutput,answer=schemaeval.schemas.medium_v2:AnswerOutput \
  --fresh-attempts 324 --fresh-failures 24

# fence-strip revalidation of Section 4.4
python scripts/fence_strip_revalidation.py --help
```

Building the PDF requires a LaTeX installation:

```bash
cd paper && latexmk -pdf main.tex
```

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
cp .env.example .env     # add OPENAI_API_KEY and ANTHROPIC_API_KEY
python scripts/run_pilot.py
```

Models are called through each vendor's own API with the parameters recorded in
Appendix A of the paper.

## Datasets

**HotpotQA** (Yang et al., EMNLP 2018), distractor configuration, validation
split, first records in dataset order. Distributed by its authors under
CC BY-SA 4.0.

**FinanceBench** (Islam et al., arXiv:2311.11944), the public
`PatronusAI/financebench` sample, first records in dataset order, evidence
truncated to 2,000 characters. The release is gated and requires accepting its
licence on HuggingFace before download.

**FinanceBench question text is withheld from this artifact** under that
licence: rows in `paper/generated/question_manifest.csv` carry the record hash
but not the text. `src/schemaeval/data/financebench.py` regenerates the inputs
from the original source once you have accepted the licence.

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
doc/              analysis runbook
```

## Licence

Code and analysis outputs: MIT, see `LICENSE`. Third-party datasets keep their
own licences, as noted above.
