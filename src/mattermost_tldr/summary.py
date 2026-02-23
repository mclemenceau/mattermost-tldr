"""AI summarization backends."""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import ensure_prompt_file

log = logging.getLogger(__name__)

__all__ = ["BACKENDS", "run_ai_summary"]

BACKENDS: dict[str, dict] = {
    "copilot": {
        # Digest is written to a temp file; a short --prompt references it.
        "cmd": ["copilot", "--silent", "--prompt"],
        "input_mode": "file",
        "label": "GitHub Copilot",
    },
    "claude": {
        # Reads the prompt from stdin: claude -p
        "cmd": ["claude", "-p"],
        "input_mode": "stdin",
        "label": "Claude",
    },
}


def run_ai_summary(digest_path: Path, backend_key: str) -> None:
    backend = BACKENDS[backend_key]
    prompt = ensure_prompt_file()

    digest_content = digest_path.read_text(encoding="utf-8")
    full_message = f"{prompt}\n\n---\n\n{digest_content}"

    log.info("Summarising with %s ...", backend["label"])

    if backend["input_mode"] == "stdin":
        result = subprocess.run(
            backend["cmd"], input=full_message, capture_output=True, text=True
        )
    else:  # "file"
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".md", prefix="mattermost_digest_"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(digest_content)
            copilot_prompt = (
                f"{prompt}\n\n"
                f"The Mattermost digest to analyse is in the file:"
                f" {tmp_path}\n\n"
                "Output the summary as plain text only."
                " Do not write any files."
            )
            result = subprocess.run(
                backend["cmd"] + [copilot_prompt],
                capture_output=True,
                text=True,
            )
        finally:
            os.unlink(tmp_path)

    print(result.stdout, end="")
    if result.returncode != 0:
        log.error("%s", result.stderr.strip())
        sys.exit(result.returncode)

    summary_path = digest_path.parent / digest_path.name.replace(
        "digest_", "summary_", 1
    )
    summary_path.write_text(result.stdout, encoding="utf-8")
    log.info("→ Summary written to %s", summary_path)
