"""Configuration constants, prompt management, and config loading."""

import logging
import sys
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_PROMPT",
    "CONFIG_DIR",
    "PROMPT_FILE",
    "DEFAULT_CONFIG",
    "ensure_prompt_file",
    "load_config",
    "resolve_prompt_file",
]

DEFAULT_PROMPT = """\
You are my personal Mattermost assistant. Analyze the digest below and give me a
concise, actionable summary. Focus on:

## What I need to follow up on
List any open questions, requests, or action items directed at me or
left unanswered.

## What is most important
Highlight decisions made, critical updates, or anything that needs my
attention soon.

## People
Pay special attention to messages from or about the following people:
- (add names here)

## Keywords to watch for
Flag any messages containing:
- (add keywords here, e.g. "urgent", "deadline", "blocker")

---
Keep the summary structured and brief. Skip channels or threads with
no meaningful activity.
"""

CONFIG_DIR = Path.home() / ".config" / "mattermost-tldr"
PROMPT_FILE = CONFIG_DIR / "prompt.md"
DEFAULT_CONFIG = CONFIG_DIR / "config.yaml"


def ensure_prompt_file() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not PROMPT_FILE.exists():
        PROMPT_FILE.write_text(DEFAULT_PROMPT, encoding="utf-8")
        log.info(
            "Created default prompt at %s"
            " — edit it to personalise your summaries.",
            PROMPT_FILE,
        )
    return PROMPT_FILE.read_text(encoding="utf-8")


def resolve_prompt_file(name_or_path: str) -> str:
    """Load prompt text from a file path or a named preset.

    Resolution order:
    1. ``name_or_path`` as a literal path – used if the file exists.
    2. ``CONFIG_DIR/<name_or_path>`` (appending ``.md`` when the argument
       has no suffix) – used if that file exists.

    Exits with an error message when neither location is found.
    """
    direct = Path(name_or_path)
    if direct.exists():
        return direct.read_text(encoding="utf-8")

    stem = (
        name_or_path if name_or_path.endswith(".md") else f"{name_or_path}.md"
    )
    config_path = CONFIG_DIR / stem
    if config_path.exists():
        return config_path.read_text(encoding="utf-8")

    log.error(
        "Error: prompt file not found: '%s'. "
        "Provide a valid file path or place a preset at %s.",
        name_or_path,
        config_path,
    )
    sys.exit(1)


def load_config(path: Path) -> dict:
    if not path.exists():
        log.error("Error: Config file not found: %s", path)
        log.error(
            "Copy examples/config.example.yaml to %s and fill in your details.",
            DEFAULT_CONFIG,
        )
        sys.exit(1)
    with path.open() as f:
        return yaml.safe_load(f) or {}
