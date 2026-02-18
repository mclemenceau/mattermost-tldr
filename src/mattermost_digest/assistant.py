#!/usr/bin/env python3
"""
mattermost-assistant — Run mattermost-digest then summarize with Claude.

Usage:
    mattermost-assistant                        # uses config defaults
    mattermost-assistant --today --direct
    mattermost-assistant --last-week
    mattermost-assistant --digest path/to/digest.md   # skip digest generation

All arguments (except --digest) are forwarded to mattermost-digest.
The summary prompt is read from ~/.config/mattermost-digest/prompt.md.
"""

import argparse
import subprocess
import sys
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "mattermost-digest"
PROMPT_FILE = CONFIG_DIR / "prompt.md"

DEFAULT_PROMPT = """\
You are my personal Mattermost assistant. Analyze the digest below and give me a
concise, actionable summary. Focus on:

## What I need to follow up on
List any open questions, requests, or action items directed at me or left unanswered.

## What is most important
Highlight decisions made, critical updates, or anything that needs my attention soon.

## People
Pay special attention to messages from or about the following people:
- (add names here)

## Keywords to watch for
Flag any messages containing:
- (add keywords here, e.g. "urgent", "deadline", "blocker")

---
Keep the summary structured and brief. Skip channels or threads with no meaningful activity.
"""


def ensure_prompt_file() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not PROMPT_FILE.exists():
        PROMPT_FILE.write_text(DEFAULT_PROMPT, encoding="utf-8")
        print(f"Created default prompt at {PROMPT_FILE} — edit it to personalise your summaries.")
    return PROMPT_FILE.read_text(encoding="utf-8")


def run_digest(args: list[str]) -> Path | None:
    """Run mattermost-digest, print its output, and return the generated file path."""
    result = subprocess.run(
        ["mattermost-digest"] + args,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
        sys.exit(result.returncode)

    for line in result.stdout.splitlines():
        if line.startswith("→ Written to "):
            return Path(line.removeprefix("→ Written to ").strip())
    return None


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--digest", metavar="FILE")
    known, forwarded = parser.parse_known_args()

    prompt = ensure_prompt_file()

    if known.digest:
        digest_path = Path(known.digest)
        if not digest_path.exists():
            print(f"Error: digest file not found: {digest_path}", file=sys.stderr)
            sys.exit(1)
    else:
        digest_path = run_digest(forwarded)
        if digest_path is None:
            print("\nNo digest file was generated — nothing to summarise.")
            sys.exit(0)

    digest_content = digest_path.read_text(encoding="utf-8")

    full_message = f"{prompt}\n\n---\n\n{digest_content}"

    print("\nSummarising with Claude ...\n")
    result = subprocess.run(["claude", "-p", full_message], capture_output=True, text=True)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
        sys.exit(result.returncode)

    summary_path = digest_path.parent / digest_path.name.replace("digest_", "summary_", 1)
    summary_path.write_text(result.stdout, encoding="utf-8")
    print(f"\n→ Summary written to {summary_path}")
