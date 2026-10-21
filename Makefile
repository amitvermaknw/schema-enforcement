# Artifact for "Why Does Structured Output Fail? An Empirical Study of
# Prompt-Enforced Pydantic Schemas Across Nine LLMs".
#
# Everything except `pilot` runs offline against the locked database:
# no API keys, no model calls. Python 3.12.
#
#   make install   create .venv from requirements-lock.txt (verified analysis env)
#   make repro     regenerate every number and run every check in the README
#   make paper     build the PDF (needs a LaTeX installation)

PY      ?= .venv/bin/python
DB      := results/archive/paper1_FINAL_DATA_locked_v4_20260913.db
DB_SHA  := d0f406f00882dadb4c0aa0b1bea3a4a77b562c80ec46f19fe7d6ad7d4ebfbeb4
GEN     := paper/generated
TMP     ?= /tmp

.PHONY: help install install-latest verify-db numbers lint-numbers audit counterfactual \
        check-reclassify check-revalidate repro paper lint-code format pilot clean clean-db

help:
	@echo "Offline (no API keys):"
	@echo "  install           create .venv from requirements-lock.txt (Python 3.12)"
	@echo "  install-latest    create .venv from requirements.txt (unpinned; may drift)"
	@echo "  verify-db         check the locked database's SHA-256"
	@echo "  numbers           regenerate paper/generated/* from the locked database"
	@echo "  lint-numbers      fail on hard-coded or unknown numbers in the paper"
	@echo "  audit             first-attempt audit (Appendix E) -> audit_review3.md"
	@echo "  counterfactual    counterfactual revalidation (Section 4.3)"
	@echo "  check-reclassify  re-run the classifier on a copy; expect 0 changed labels"
	@echo "  check-revalidate  revalidate all 4396 stored completions; expect full agreement"
	@echo "  repro             all of the above, in order"
	@echo "  paper             build paper/main_emse.tex (needs LaTeX)"
	@echo "  lint-code / format  ruff / black"
	@echo "Online (needs API keys in .env, costs money):"
	@echo "  pilot             small pilot run"

install:
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-lock.txt

install-latest:
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

verify-db:
	@$(PY) -c "import hashlib,sys; h=hashlib.sha256(open('$(DB)','rb').read()).hexdigest(); print('locked DB sha256', h, 'OK' if h=='$(DB_SHA)' else 'MISMATCH'); sys.exit(h!='$(DB_SHA)')"

numbers: verify-db
	$(PY) scripts/review3.py numbers --db $(DB) --out $(GEN) --repo .
	$(PY) scripts/make_paper_numbers.py
	$(PY) scripts/render_paper_assets.py

lint-numbers:
	$(PY) scripts/lint_numbers.py

audit: verify-db
	$(PY) scripts/review3.py audit --db $(DB) --out audit_review3.md

counterfactual: verify-db
	$(PY) scripts/review3.py counterfactual --db $(DB) --pythonpath src \
	  --medium identify=schemaeval.schemas.medium:IdentifyOutput,gather=schemaeval.schemas.medium:GatherOutput,answer=schemaeval.schemas.medium:AnswerOutput \
	  --v2 identify=schemaeval.schemas.medium_v2:IdentifyOutput,gather=schemaeval.schemas.medium_v2:GatherOutput,answer=schemaeval.schemas.medium_v2:AnswerOutput \
	  --fresh-attempts 324 --fresh-failures 24

check-reclassify: verify-db
	cp $(DB) $(TMP)/reclass_check.db
	DB_PATH=$(TMP)/reclass_check.db $(PY) scripts/reclassify_all.py --dry-run | tee $(TMP)/reclass_check.out
	@grep -qE 'Total rows examined:[[:space:]]+1326' $(TMP)/reclass_check.out
	@grep -qE 'Rows to update:[[:space:]]+0' $(TMP)/reclass_check.out
	@echo "check-reclassify OK"

check-revalidate: verify-db
	$(PY) scripts/revalidate_all.py --db $(DB) | tee $(TMP)/revalidate_check.out
	@grep -qE '^agree: 4396$$' $(TMP)/revalidate_check.out
	@echo "check-revalidate OK"

repro: numbers lint-numbers audit counterfactual check-reclassify check-revalidate verify-db
	@echo "repro OK: all numbers regenerated and all checks passed"

# main.tex is the archived TMLR submission; main_emse.tex is the current manuscript.
paper:
	cd paper && latexmk -pdf main_emse.tex

lint-code:
	$(PY) -m ruff check src/ scripts/

format:
	$(PY) -m black src/ scripts/ tests/

pilot:
	$(PY) scripts/run_pilot.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

clean-db:
	rm -f results/experiments.db results/experiments.db-journal
	@echo "Deleted results/experiments.db (the locked archive DB is untouched)"
