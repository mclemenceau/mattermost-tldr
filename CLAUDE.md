# CLAUDE.md — Project Instructions for Claude

This file configures how Claude assists with this project. Follow these instructions in every session.

---

## Project Overview

mattermost-tldr export Mattermost messages to markdown and summarize with AI

---

## Tech Stack

- **Language:** Python 3.x
- **Package manager:** `pipx`
- **Test framework:** `pytest`
- **Linting:** `ruff`
- **Formatting:** `black`
- **Type checking:** `mypy`
- **Coverage:** `pytest-cov`

---

## Environment Setup

```bash
make setup       # Create .venv and install package + dev dependencies
make test        # Run the full test suite with coverage
make install     # Install globally with pipx (for end-user use)
make uninstall   # Remove the pipx installation
make clean       # Remove .venv, cache files, and build artefacts
```

Or manually:

```bash
pip install -e ".[dev]"
```

---

## Code Style & Linting

**Always run linting before and after making changes.**

```bash
ruff check .          # lint
ruff check . --fix    # auto-fix safe issues
ruff format .         # format
mypy .                # type check
```

- Follow PEP 8 and the project's `ruff` configuration in `pyproject.toml`.
- Do **not** disable linting rules inline (e.g., `# noqa`) unless truly necessary, and always add a comment explaining why.
- Keep line length at **80 characters** (adjust to match `pyproject.toml`).
- Use type annotations on all public functions and methods.
- Prefer explicit imports over wildcard imports.

---

## Testing Workflow

**Test-first approach: write or update tests before fixing bugs or implementing features.**

```bash
pytest                          # run all tests
pytest -x                       # stop on first failure
pytest tests/test_foo.py -v     # run a specific file
pytest -k "test_name"           # run matching tests
```

### When making changes:

1. **Bug fixes:** Write a failing test that reproduces the bug, then fix it.
2. **New features:** Write the test(s) first, then implement the feature until tests pass.
3. **Refactoring:** Ensure existing tests pass before and after — do not change test assertions during a refactor unless the behavior intentionally changes.

### Test conventions:

- Place tests in `tests/` mirroring the source structure (e.g., `src/foo/bar.py` → `tests/foo/test_bar.py`).
- Use descriptive test names: `test_<function>_<scenario>_<expected_result>`.
- Use `pytest.mark.parametrize` for data-driven tests.
- Mock external I/O (network, filesystem, time) — tests must be deterministic and fast.
- Keep unit tests isolated; use integration tests for cross-component behavior.

---

## Code Coverage

**Maintain a minimum of 60% coverage.** Do not merge changes that drop coverage below this threshold.

```bash
pytest --cov=src --cov-report=term-missing          # coverage in terminal
pytest --cov=src --cov-report=html                  # HTML report in htmlcov/
```

- When adding new modules, add corresponding tests to maintain coverage.
- Coverage exclusions (e.g., `# pragma: no cover`) must be justified in a comment.
- Focus coverage on business logic; it's acceptable to exclude `if __name__ == "__main__"` blocks.

---

## CI / Pre-commit Checklist

Before considering any change complete, verify:

- [ ] `ruff check .` passes with no errors
- [ ] `ruff format --check .` passes (no formatting diff)
- [ ] `mypy .` passes with no errors
- [ ] `pytest` passes with no failures
- [ ] Coverage is at or above **60%**

---

## Project Structure

```
.
├── src/
│   └── <package>/       # Main source package
├── tests/               # Mirrors src/ structure
├── pyproject.toml       # Project metadata, deps, tool config
├── CLAUDE.md            # This file
└── README.md
```

---

## Common Pitfalls to Avoid

- Do not introduce new dependencies without updating `pyproject.toml`.
- Do not silently swallow exceptions — log or re-raise with context.
- Do not use mutable default arguments (`def f(x=[]):`).
- Avoid `print()` for debugging in committed code — use `logging`.
- Do not leave `TODO` comments untracked; convert them to issues or address them.

---

## Claude-specific Guidance

- **Ask before large refactors.** If a change affects more than ~3 files or alters public APIs, confirm the approach first.
- **Explain non-obvious decisions.** If a fix is subtle, add an inline comment.
- **Prefer small, focused commits.** Each logical change should be independently understandable.
- **Do not guess at intent.** If a requirement is ambiguous, ask a clarifying question before writing code.
- **Surface tradeoffs.** If there are multiple valid approaches, briefly describe them before choosing one.