# ─────────────────────────────────────────────────────────────────────────────
# forge-mock Makefile
# Usage: make <target>
# Requires: uv (https://docs.astral.sh/uv/)
# ─────────────────────────────────────────────────────────────────────────────

.DEFAULT_GOAL := help
.PHONY: help install build clean lint lint-fix format format-check typecheck check test test-cov test-fast smoke smoke-parquet smoke-csv smoke-sql smoke-config smoke-seed smoke-corrupt all

# ── Config ────────────────────────────────────────────────────────────────────

UV        := uv
RUN       := $(UV) run
SRC       := src/
TESTS     := tests/
EXAMPLES  := examples/ecommerce.sql
CONFIG    := examples/ecommerce_config.yaml
SMOKE_DIR := /tmp/forge-mock-smoke

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  ⚒  forge-mock — local dev targets"
	@echo ""
	@echo "  Setup"
	@echo "    install        uv sync (all deps incl. dev)"
	@echo "    build          uv build → dist/"
	@echo "    clean          remove build artefacts and smoke output"
	@echo ""
	@echo "  Code quality"
	@echo "    lint           ruff check (report only)"
	@echo "    lint-fix       ruff check --fix (auto-fix safe issues)"
	@echo "    format         ruff format (rewrite files)"
	@echo "    format-check   ruff format --check (CI-style, no writes)"
	@echo "    typecheck      mypy src/"
	@echo "    check          lint + format-check + typecheck"
	@echo ""
	@echo "  Tests"
	@echo "    test           pytest"
	@echo "    test-cov       pytest + html coverage report"
	@echo "    test-fast      pytest -x (stop on first failure)"
	@echo ""
	@echo "  CLI smoke tests"
	@echo "    smoke          run all smoke tests"
	@echo "    smoke-parquet  generate parquet, assert files exist"
	@echo "    smoke-csv      generate csv, assert row counts"
	@echo "    smoke-sql      generate sql, assert INSERT INTO present"
	@echo "    smoke-config   generate with yaml config override"
	@echo "    smoke-seed     determinism check (seed=99 × 2, diff)"
	@echo "    smoke-corrupt  corruption mode (--corrupt 0.1)"
	@echo ""
	@echo "  Composite"
	@echo "    all            install → check → test → smoke"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────

install:
	$(UV) sync

build:
	$(UV) build

clean:
	rm -rf dist/ .coverage htmlcov/ coverage.xml .mypy_cache .ruff_cache \
	       $(SMOKE_DIR) \
	       $$(find . -type d -name __pycache__) \
	       $$(find . -type d -name "*.egg-info")
	@echo "Clean."

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	$(RUN) ruff check $(SRC) $(TESTS)

lint-fix:
	$(RUN) ruff check --fix $(SRC) $(TESTS)

format:
	$(RUN) ruff format $(SRC) $(TESTS)

format-check:
	$(RUN) ruff format --check $(SRC) $(TESTS)

typecheck:
	$(RUN) mypy $(SRC)

check: lint format-check typecheck

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	$(RUN) pytest $(TESTS)

test-cov:
	$(RUN) pytest $(TESTS) \
	  --cov=$(SRC) \
	  --cov-report=term-missing \
	  --cov-report=html:htmlcov
	@echo ""
	@echo "  Coverage report → htmlcov/index.html"

test-fast:
	$(RUN) pytest $(TESTS) -x --tb=short

# ── CLI smoke tests ───────────────────────────────────────────────────────────

smoke: smoke-parquet smoke-csv smoke-sql smoke-config smoke-seed smoke-corrupt
	@echo ""
	@echo "  ✓ All smoke tests passed."

smoke-parquet:
	@echo "── smoke: parquet ──────────────────────────────────────────"
	$(RUN) forge-mock generate $(EXAMPLES) \
	  --rows 50 --format parquet --seed 42 \
	  --output $(SMOKE_DIR)/parquet
	@for t in customers categories products orders order_items; do \
	  f="$(SMOKE_DIR)/parquet/$${t}.parquet"; \
	  if [ ! -f "$$f" ]; then echo "MISSING: $$f"; exit 1; fi; \
	  echo "  OK  $$f"; \
	done

smoke-csv:
	@echo "── smoke: csv ──────────────────────────────────────────────"
	$(RUN) forge-mock generate $(EXAMPLES) \
	  --rows 50 --format csv --seed 42 \
	  --output $(SMOKE_DIR)/csv
	@for t in customers categories products orders order_items; do \
	  f="$(SMOKE_DIR)/csv/$${t}.csv"; \
	  if [ ! -f "$$f" ]; then echo "MISSING: $$f"; exit 1; fi; \
	  lines=$$(wc -l < "$$f"); \
	  if [ "$$lines" -ne 51 ]; then \
	    echo "WRONG ROW COUNT in $$f: expected 51, got $$lines"; exit 1; \
	  fi; \
	  echo "  OK  $$f ($$lines lines)"; \
	done

smoke-sql:
	@echo "── smoke: sql ──────────────────────────────────────────────"
	$(RUN) forge-mock generate $(EXAMPLES) \
	  --rows 50 --format sql --seed 42 \
	  --output $(SMOKE_DIR)/sql
	@for t in customers categories products orders order_items; do \
	  f="$(SMOKE_DIR)/sql/$${t}.sql"; \
	  if [ ! -f "$$f" ]; then echo "MISSING: $$f"; exit 1; fi; \
	  if ! grep -q "INSERT INTO" "$$f"; then \
	    echo "NO INSERT INTO in $$f"; exit 1; \
	  fi; \
	  echo "  OK  $$f"; \
	done

smoke-config:
	@echo "── smoke: yaml config ──────────────────────────────────────"
	$(RUN) forge-mock generate $(EXAMPLES) \
	  --rows 50 --format csv --seed 42 \
	  --config $(CONFIG) \
	  --output $(SMOKE_DIR)/config
	@[ -f "$(SMOKE_DIR)/config/orders.csv" ] \
	  && echo "  OK  config override run completed" \
	  || (echo "MISSING orders.csv"; exit 1)

smoke-seed:
	@echo "── smoke: determinism ──────────────────────────────────────"
	$(RUN) forge-mock generate $(EXAMPLES) \
	  --rows 25 --format csv --seed 99 --output $(SMOKE_DIR)/seed-a
	$(RUN) forge-mock generate $(EXAMPLES) \
	  --rows 25 --format csv --seed 99 --output $(SMOKE_DIR)/seed-b
	@diff $(SMOKE_DIR)/seed-a/customers.csv $(SMOKE_DIR)/seed-b/customers.csv \
	  && echo "  OK  seed=99 produces identical output" \
	  || (echo "FAIL: outputs differ with same seed"; exit 1)

smoke-corrupt:
	@echo "── smoke: corrupt mode ─────────────────────────────────────"
	$(RUN) forge-mock generate $(EXAMPLES) \
	  --rows 50 --format csv --seed 42 --corrupt 0.1 \
	  --output $(SMOKE_DIR)/corrupt
	@[ -f "$(SMOKE_DIR)/corrupt/customers.csv" ] \
	  && echo "  OK  corrupt mode completed without crash" \
	  || (echo "MISSING output"; exit 1)

# ── Composite ─────────────────────────────────────────────────────────────────

all: install check test smoke