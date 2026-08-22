.PHONY: install pilot test lint format clean clean-db help

help:
	@echo "Available targets:"
	@echo "  install     Create venv and install dependencies"
	@echo "  pilot       Run the pilot experiment (5 samples)"
	@echo "  test        Run unit tests"
	@echo "  lint        Run ruff linter"
	@echo "  format      Run black formatter"
	@echo "  clean       Remove __pycache__ and .pyc files"
	@echo "  clean-db    Delete results/experiments.db"

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
	@echo ""
	@echo "Done. Activate the venv with:  source .venv/bin/activate"
	@echo "Then copy .env.example to .env and fill in your API keys."

pilot:
	. .venv/bin/activate && python scripts/run_pilot.py

test:
	. .venv/bin/activate && pytest tests/ -v

lint:
	. .venv/bin/activate && ruff check src/ scripts/

format:
	. .venv/bin/activate && black src/ scripts/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

clean-db:
	rm -f results/experiments.db results/experiments.db-journal
	@echo "Deleted results/experiments.db"
