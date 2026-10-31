PYTHON ?= python3
VENV ?= .tmp/ci-venv
PY := $(VENV)/bin/python
PATTERNS ?= .patterns
LINT_PATHS := scripts/validate-kits.py scripts/run-kit-tests.py scripts/tests claude-code/files claude-code/tests claude-code/scripts/test claude-code/scripts/verify
LINT_PATHS += codex/files codex/tests codex/scripts antigravity/files antigravity/tests antigravity/scripts scripts/verify-native-cli.py
GITLEAKS ?= gitleaks

.PHONY: setup check lint test validate security
setup:
	@if command -v uv >/dev/null 2>&1; then uv venv --python $(PYTHON) --seed $(VENV); else $(PYTHON) -m venv $(VENV); fi
	$(PY) -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r requirements-dev.lock
	npm --prefix opencode-go-provider ci --ignore-scripts --no-audit --no-fund
	npm --prefix pi-coding-agent ci --ignore-scripts --no-audit --no-fund

check: lint validate test security

lint:
	$(PY) -m ruff check $(LINT_PATHS)
	$(PY) -m ruff format --check $(LINT_PATHS)
	shellcheck claude-code/files/home/.local/bin/claude
	shellcheck codex/files/home/.local/bin/codex antigravity/files/home/.local/bin/agy

validate:
	$(PY) scripts/validate-kits.py --patterns $(PATTERNS)

test:
	$(PY) -m pytest scripts/tests -q
	$(PY) scripts/run-kit-tests.py all

security:
	$(PY) -m pip_audit --strict --require-hashes --disable-pip -r requirements-dev.lock
	$(PY) -m pip_audit --strict --require-hashes --disable-pip -r claude-code/files/home/claude-code/requirements.lock
	$(PY) $(PATTERNS)/scripts/scan_unsafe_shell.py claude-code
	$(GITLEAKS) dir --redact --no-banner --log-level warn claude-code
	$(GITLEAKS) dir --redact --no-banner --log-level warn scripts
	$(PY) $(PATTERNS)/scripts/scan_unsafe_shell.py codex antigravity
	$(GITLEAKS) dir --redact --no-banner --log-level warn codex
	$(GITLEAKS) dir --redact --no-banner --log-level warn antigravity
	$(GITLEAKS) git --redact --no-banner --log-level warn .
