# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# Quality gate. Prefer the project venv when present, otherwise use the active
# interpreter, so the same targets work locally and on CI (which has no .venv).
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)

RUFF      = $(PYTHON) -m ruff
MYPY      = $(PYTHON) -m mypy
PYTEST    = $(PYTHON) -m pytest
PIP_AUDIT = $(PYTHON) -m pip_audit
VULTURE   = $(PYTHON) -m vulture
DEPTRY    = $(PYTHON) -m deptry
SECRETS   = $(PYTHON) -m detect_secrets.pre_commit_hook

.DEFAULT_GOAL := check
.PHONY: check lint format format-check typecheck test audit

check: lint format-check typecheck test audit  ## Run every check, in order, failing on the first error

lint:  ## Lint with ruff (no writes)
	$(RUFF) check .

format:  ## Auto-format with ruff (writes files)
	$(RUFF) format .

format-check:  ## Verify formatting without writing
	$(RUFF) format --check .

typecheck:  ## Type-check the shipped packages with mypy
	$(MYPY) k2kremote k2kmaced

test:  ## Run the test suite with coverage
	$(PYTEST) --cov=k2kremote --cov=k2kmaced

audit:  ## Vulnerability, dead-code, dependency and secret scans
	$(PIP_AUDIT) . --progress-spinner off
	$(VULTURE)
	$(DEPTRY) .
	git ls-files -z --cached --others --exclude-standard | xargs -0 $(SECRETS) --baseline .secrets.baseline
