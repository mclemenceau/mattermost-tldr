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

## Git Workflow

**MANDATORY: Follow these steps before and during any large change.**

### Branching

Before any refactoring or change touching more than ~3 files, ALWAYS:

1. Run `git status` to confirm the current branch and working tree state
2. Create a new branch: `git checkout -b <type>/<short-description>`
   - Use types: `refactor/`, `feature/`, `fix/`, `chore/`
   - Example: `git checkout -b refactor/simplify-export-pipeline`
3. Confirm the branch is active before writing any code
4. Never make multi-file changes directly on `main` or the current working branch

### Atomic Commits

**Commit incrementally during large changes.** Do not batch everything into one commit at the end. After each logical unit of work is complete and tests pass, create a commit. A logical unit is one of:

- A single function or class refactored
- A new test suite added
- A dependency or configuration change
- A standalone bug fix

Run `pytest` before each commit to confirm nothing is broken.

```bash
git add -p          # stage changes interactively — prefer this over `git add .`
git commit -m "refactor: simplify export pipeline entry point"
```

### End-of-change Review

At the end of any multi-commit change, ALWAYS run:

```bash
git log --oneline origin/main..HEAD
```

Summarize the commits made before considering the work done. This gives a human
reviewer a clear picture of the change history before a PR is opened.

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

**Maintain a minimum of 90% coverage.** Do not merge changes that drop coverage below this threshold.

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
- [ ] Coverage is at or above **90%**
- [ ] `git log --oneline origin/main..HEAD` reviewed and commits are logical and clean

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

- **Create a branch for large changes.** Before any refactoring or change touching more than ~3 files, ALWAYS follow the Git Workflow section above. Do not skip branching even if the change seems straightforward.
- **Ask before large refactors.** If a change affects more than ~3 files or alters public APIs, confirm the approach first.
- **Commit incrementally.** Do not accumulate all changes into a single commit. Follow the Atomic Commits section above.
- **Explain non-obvious decisions.** If a fix is subtle, add an inline comment.
- **Prefer small, focused commits.** Each logical change should be independently understandable.
- **Do not guess at intent.** If a requirement is ambiguous, ask a clarifying question before writing code.
- **Surface tradeoffs.** If there are multiple valid approaches, briefly describe them before choosing one.