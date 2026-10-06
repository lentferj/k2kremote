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

# Audits THIS PROJECT's dependency closure, not the ambient environment, so it
# is `pip-audit -r <the declared dependencies>` rather than a bare `pip-audit`.
#
# vinsynlib is filtered out of the list handed to pip-audit. It is this
# family's own library and, in a checkout beside it, an editable local install
# rather than a package on an index -- so pip cannot resolve it and pip-audit
# would fail *resolving*, reporting nothing about anything and failing the gate
# for a reason that is not a vulnerability. It is reviewed where it lives.
# Auditing what is *declared* is the point of this target, so every other
# declared dependency is still audited, and a new dependency added later is
# audited without anyone editing this file.
audit:  ## Vulnerability, dead-code, dependency and secret scans
	@echo "== pip-audit (project dependencies, vinsynlib filtered out)"
	@$(PYTHON) -c "import pathlib, tomllib; \
	    data = tomllib.load(open('pyproject.toml', 'rb')); \
	    pathlib.Path('.audit-runtime-req.txt').write_text(\
	        ''.join(r + chr(10) for r in data['project']['dependencies'] \
	        if not r.startswith('vinsynlib')))"
	@$(PIP_AUDIT) --progress-spinner off -r .audit-runtime-req.txt || \
	    (rm -f .audit-runtime-req.txt; exit 1)
	@rm -f .audit-runtime-req.txt
	$(VULTURE)
	$(DEPTRY) .
	git ls-files -z --cached --others --exclude-standard | xargs -0 $(SECRETS) --baseline .secrets.baseline
