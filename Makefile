VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF   := $(VENV)/bin/ruff
MYPY   := $(VENV)/bin/mypy
BLACK  := $(VENV)/bin/black

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  setup       Create .venv and install package + dev dependencies"
	@echo "  lint        Run ruff linter"
	@echo "  format      Auto-format code with ruff and black"
	@echo "  type-check  Run mypy static type checker"
	@echo "  check       Run lint, format check (ruff + black), and type-check"
	@echo "  test        Run the full test suite with coverage"
	@echo "  build       Build source distribution and wheel (dist/)"
	@echo "  bump-patch  Bump patch version, commit, and tag"
	@echo "  bump-minor  Bump minor version, commit, and tag"
	@echo "  bump-major  Bump major version, commit, and tag"
	@echo "  install     Install globally with pipx (for end-user use)"
	@echo "  uninstall   Remove the pipx installation"
	@echo "  clean       Remove .venv, cache files, and build artefacts"

# ---------------------------------------------------------------------------
# Development environment
# ---------------------------------------------------------------------------

.PHONY: setup
setup: $(VENV)/bin/activate

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -e ".[dev]"
	@echo "Virtualenv ready. Run: source $(VENV)/bin/activate"

# ---------------------------------------------------------------------------
# Linting, formatting, type checking
# ---------------------------------------------------------------------------

.PHONY: lint format type-check check
lint: setup
	$(RUFF) check .

format: setup
	$(RUFF) format .
	$(BLACK) .

type-check: setup
	$(MYPY) src/

check: setup lint type-check
	$(RUFF) format --check .

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

.PHONY: test
test: setup
	$(PYTEST)

# ---------------------------------------------------------------------------
# Build distribution packages
# ---------------------------------------------------------------------------

.PHONY: build
build: setup
	$(PYTHON) -m build

# ---------------------------------------------------------------------------
# Version bumping (bump-my-version)
# ---------------------------------------------------------------------------

.PHONY: bump-patch bump-minor bump-major
bump-patch: setup
	$(VENV)/bin/bump-my-version bump patch

bump-minor: setup
	$(VENV)/bin/bump-my-version bump minor

bump-major: setup
	$(VENV)/bin/bump-my-version bump major

# ---------------------------------------------------------------------------
# Global install / uninstall via pipx
# ---------------------------------------------------------------------------

.PHONY: install uninstall
install:
	pipx install .

uninstall:
	pipx uninstall mattermost-tldr

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

.PHONY: clean
clean:
	rm -rf $(VENV)
	rm -rf dist/
	rm -rf .coverage .pytest_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	@echo "Clean."
