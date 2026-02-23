# Contributing to mattermost-tldr

Thank you for your interest in contributing! This document explains how
to get involved, what is expected, and how to get your changes merged.

---

## Before you start

For anything beyond a typo fix or a small bug, **please open an issue
first**. Describe what you want to change and why. This avoids wasted
effort on both sides and gives us a chance to discuss the best approach
before any code is written.

For small, obvious fixes (typos, broken links, trivial bugs) you can go
straight to a pull request.

---

## Development setup

```bash
git clone https://github.com/<your-fork>/mattermost-tldr.git
cd mattermost-tldr
make setup   # create .venv and install package + dev dependencies
```

---

## Workflow

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b my-feature
   ```
2. **Write tests first.** Bug fixes should include a failing test that
   reproduces the issue before the fix. New features should have tests
   that cover the expected behaviour.
3. **Make your changes**, keeping commits small and focused. Each commit
   should represent one logical change and be independently
   understandable.
4. **Verify everything passes** before pushing:
   ```bash
   make check   # lint + format check + type check
   make test    # full test suite with coverage
   ```
5. **Open a pull request** against `main`. Fill in the PR description
   with:
   - What the change does and why
   - How you tested it
   - Any tradeoffs or alternatives you considered

---

## Code standards

- Follow PEP 8; `ruff` is the enforced linter and formatter.
- Add type annotations to all public functions and methods.
- Keep line length at 80 characters (configured in `pyproject.toml`).
- Do not use `print()` — use `logging` instead.
- Do not silently swallow exceptions — log or re-raise with context.
- Maintain test coverage at or above *90%**. New modules must ship with
  corresponding tests.

Run the full quality check at any time:

```bash
make check   # ruff lint + format check + mypy
make test    # pytest with coverage report
```

All of these run automatically in CI on every pull request.

---

## AI-assisted contributions

AI-assisted code is welcome. If you used an AI tool (GitHub Copilot,
Claude, ChatGPT, etc.) to write or substantially revise code in your PR,
please mention it in the PR description. You are still responsible for
reviewing, understanding, and testing everything you submit — the same
quality bar applies regardless of how the code was written.

---

## Commit messages

Write commit messages in the imperative mood, describing *what* the
change does and *why* (not just *what* the diff shows):

```
Add --hours flag to support sub-day time windows

Previously only full-day ranges were supported. This adds an --hours N
flag for catching up on recent activity without needing to process an
entire day's worth of messages.
```

---

## What makes a good PR

- It solves one problem clearly.
- It includes tests.
- `make check` and `make test` pass.
- The description explains the motivation, not just the mechanics.
- It has been reviewed by the author before submission (no debug code,
  no leftover TODOs, no accidental file inclusions).

---

## Questions?

Open an issue and tag it `question`. We're happy to help.
