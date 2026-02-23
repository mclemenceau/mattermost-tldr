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
