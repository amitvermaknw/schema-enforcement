#!/usr/bin/env bash
# Regenerates paper/generated/app_code.tex (Appendix B listings) from repo sources.
# Part of the build: run after the source commit, before committing paper/generated/.
set -euo pipefail
cd "$(dirname "$0")/.."
S=src/schemaeval
python scripts/review3.py appcode --repo . \
  --item "Baseline schema=$S/schemas/medium.py" \
  --item "System-prompt variants=$S/prompts.py" \
  --item "Per-node user prompts=$S/topologies/sequential.py::run_sequential_graph" \
  --item "Validation and retry loop=$S/paradigms/strict_repair.py::call_llm_strict_repair" \
  --item "Stage-1 predicates=$S/errors.py::_SCHEMA_META_KEYS,_SCHEMA_META_KEY_THRESHOLD,_EMBEDDED_JSON_RE,_looks_like_schema_mirroring,_looks_like_markdown_wrap,_looks_like_prose_preamble,_strip_code_fences,_heuristic_category" \
  --diff "medium_v2 changes=$S/schemas/medium.py..$S/schemas/medium_v2.py" \
  --diff "medium_v3 changes=$S/schemas/medium.py..$S/schemas/medium_v3_loose_regex.py"
