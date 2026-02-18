#!/usr/bin/env python3
"""
mattermost-assistant — Run mattermost-digest then summarize with an AI assistant.

Usage:
    mattermost-assistant                        # uses config defaults (Claude)
    mattermost-assistant --today --direct
    mattermost-assistant --last-week
    mattermost-assistant --backend copilot      # use GitHub Copilot CLI instead
    mattermost-assistant --digest path/to/digest.md   # skip digest generation

All arguments (except --digest and --backend) are forwarded to mattermost-digest.
The summary prompt is read from ~/.config/mattermost-digest/prompt.md.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "mattermost-digest"
PROMPT_FILE = CONFIG_DIR / "prompt.md"

BACKENDS: dict[str, dict] = {
    "claude": {
        # Reads the prompt from stdin: claude -p
        "cmd":        ["claude", "-p"],
        "input_mode": "stdin",
        "label":      "Claude",
    },
    "copilot": {
        # Digest is written to a temp file; a short --prompt references it.
        # copilot is an agentic CLI that can read files via its built-in tools.
        "cmd":        ["copilot", "--silent", "--prompt"],
        "input_mode": "file",
        "label":      "GitHub Copilot",
    },
}

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
    parser = argparse.ArgumentParser(
        prog="mattermost-assistant",
        description="Run mattermost-digest then summarize with an AI assistant.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mattermost-assistant --today
  mattermost-assistant --last-week --direct
  mattermost-assistant --backend copilot --today
  mattermost-assistant --digest path/to/digest.md   # skip digest generation

All arguments except --digest and --backend are forwarded to mattermost-digest.
The summary prompt is read from ~/.config/mattermost-digest/prompt.md.

Backends:
  claude   (default) Uses the Claude CLI: claude -p
  copilot            Uses GitHub Copilot CLI: copilot --silent --prompt "..."
        """,
    )
    parser.add_argument("--digest", metavar="FILE",
                        help="Path to an existing digest file (skips running mattermost-digest)")
    parser.add_argument(
        "--backend", choices=list(BACKENDS), default="claude", metavar="BACKEND",
        help="AI backend to use for summarisation: claude (default) or copilot",
    )
    known, forwarded = parser.parse_known_args()

    backend = BACKENDS[known.backend]

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

    print(f"\nSummarising with {backend['label']} ...\n")
    if backend["input_mode"] == "stdin":
        result = subprocess.run(backend["cmd"], input=full_message, capture_output=True, text=True)
    else:  # "file" — write digest to a temp file, pass instructions as --prompt
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".md", prefix="mattermost_digest_")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(digest_content)
            copilot_prompt = (
                f"{prompt}\n\n"
                f"The Mattermost digest to analyse is in the file: {tmp_path}\n\n"
                f"Output the summary as plain text only. Do not write any files."
            )
            result = subprocess.run(
                backend["cmd"] + [copilot_prompt],
                capture_output=True, text=True,
            )
        finally:
            os.unlink(tmp_path)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="", file=sys.stderr)
        sys.exit(result.returncode)

    summary_path = digest_path.parent / digest_path.name.replace("digest_", "summary_", 1)
    summary_path.write_text(result.stdout, encoding="utf-8")
    print(f"\n→ Summary written to {summary_path}")
