# Third-party data licences

The code in this artifact is licensed separately (see `LICENSE`). The following
third-party data appears in `paper/generated/question_manifest.csv` and in
`results/archive/paper1_FINAL_DATA_locked_v4_20260913.db` (question text, and
model outputs that may quote it). Each retains its original licence.

## FinanceBench
- Source: Islam et al. (2023), "FinanceBench: A New Benchmark for Financial
  Question Answering", arXiv:2311.11944; open-source sample
  `PatronusAI/financebench` (Hugging Face), (c) Patronus AI.
- Licence: CC BY-NC 4.0 - https://creativecommons.org/licenses/by-nc/4.0/
- Modifications: first records in dataset order only; evidence truncated to
  2,000 characters with a truncation marker.
- These portions may not be used for commercial purposes.

## HotpotQA
- Source: Yang et al. (2018), "HotpotQA: A Dataset for Diverse, Explainable
  Multi-hop Question Answering", EMNLP 2018; Hugging Face `hotpot_qa`,
  `distractor` configuration, `validation` split.
- Licence: CC BY-SA 4.0 - https://creativecommons.org/licenses/by-sa/4.0/
- Modifications: none to the question text. The first n records of the split
  are used, question field only; context passages are not used.

Provided as-is, without warranties, per the respective licences.
