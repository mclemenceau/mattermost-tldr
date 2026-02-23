"""Shared pytest fixtures and session-level safeguards."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def guard_subprocess():
    """Prevent any test from accidentally spawning a real subprocess.

    If a test genuinely needs subprocess.run it must mock it explicitly,
    which overrides this guard for the duration of that mock's context.
    Any call that slips through raises RuntimeError rather than launching
    copilot, claude, or any other external process.
    """

    def _deny(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", "<unknown>")
        raise RuntimeError(
            f"subprocess.run reached the real implementation during a test.\n"
            f"Command attempted: {cmd!r}\n"
            f"Wrap the call to run_ai_summary with mock_subprocess() or "
            f"patch('mattermost_tldr.cli.subprocess.run') explicitly."
        )

    with patch("mattermost_tldr.summary.subprocess.run", side_effect=_deny):
        yield
