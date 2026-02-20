"""Tests for run_ai_summary.

All filesystem and subprocess calls are mocked so tests run in full isolation.
"""

import pytest
from unittest.mock import patch, MagicMock

from mattermost_tldr.cli import run_ai_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mock_prompt():
    """Patch ensure_prompt_file so no ~/.config directory is touched."""
    return patch("mattermost_tldr.cli.ensure_prompt_file", return_value="Summarise this:\n")


def mock_subprocess(stdout="Summary output", returncode=0, stderr=""):
    """Patch subprocess.run in the module under test."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = stderr
    return patch("mattermost_tldr.cli.subprocess.run", return_value=result)


def make_digest(tmp_path, name="digest_2026-02-20.md", content="# Digest\n\nSome content."):
    """Write a digest file inside pytest's isolated tmp_path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# Stable fake path returned by the mocked mkstemp
FAKE_TMP_PATH = "/tmp/mattermost_digest_fake.md"


@pytest.fixture
def copilot_io():
    """Mock every filesystem call made by the copilot (file-mode) backend.

    Yields the mock for os.unlink so individual tests can assert on it.
    """
    mock_file = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_file)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("mattermost_tldr.cli.tempfile.mkstemp", return_value=(5, FAKE_TMP_PATH)), \
         patch("mattermost_tldr.cli.os.fdopen", return_value=mock_cm), \
         patch("mattermost_tldr.cli.os.unlink") as mock_unlink:
        yield mock_unlink


# ---------------------------------------------------------------------------
# stdin backend (claude)
# ---------------------------------------------------------------------------

class TestRunAiSummaryStdin:
    def test_invokes_correct_command(self, tmp_path):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess() as mock_run:
            run_ai_summary(digest, "claude")
        assert mock_run.call_args[0][0] == ["claude", "-p"]

    def test_passes_prompt_prepended_to_digest(self, tmp_path):
        digest = make_digest(tmp_path, content="Digest body here.")
        with mock_prompt(), mock_subprocess() as mock_run:
            run_ai_summary(digest, "claude")
        stdin_input = mock_run.call_args[1]["input"]
        assert "Summarise this:" in stdin_input
        assert "Digest body here." in stdin_input
        # Prompt must come before the digest
        assert stdin_input.index("Summarise this:") < stdin_input.index("Digest body here.")

    def test_capture_output_and_text_mode(self, tmp_path):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess() as mock_run:
            run_ai_summary(digest, "claude")
        kwargs = mock_run.call_args[1]
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True

    def test_writes_summary_file(self, tmp_path):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess(stdout="The summary."):
            run_ai_summary(digest, "claude")
        summary = tmp_path / "summary_2026-02-20.md"
        assert summary.exists()
        assert summary.read_text() == "The summary."

    def test_summary_filename_derived_from_digest_name(self, tmp_path):
        digest = make_digest(tmp_path, name="digest_last_4h.md")
        with mock_prompt(), mock_subprocess(stdout="ok"):
            run_ai_summary(digest, "claude")
        assert (tmp_path / "summary_last_4h.md").exists()

    def test_nonzero_returncode_exits(self, tmp_path):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess(stdout="", returncode=1, stderr="boom"):
            with pytest.raises(SystemExit) as exc_info:
                run_ai_summary(digest, "claude")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# file backend (copilot)
# ---------------------------------------------------------------------------

class TestRunAiSummaryFile:
    def test_invokes_copilot_command(self, tmp_path, copilot_io):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess(stdout="copilot summary") as mock_run:
            run_ai_summary(digest, "copilot")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "copilot"
        assert "--prompt" in cmd

    def test_fake_temp_path_referenced_in_prompt(self, tmp_path, copilot_io):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess(stdout="ok") as mock_run:
            run_ai_summary(digest, "copilot")
        prompt_arg = mock_run.call_args[0][0][-1]  # last element of cmd list
        assert FAKE_TMP_PATH in prompt_arg

    def test_digest_content_written_to_temp_file(self, tmp_path, copilot_io):
        digest = make_digest(tmp_path, content="Important content.")
        with mock_prompt(), mock_subprocess(stdout="ok"), \
             patch("mattermost_tldr.cli.os.fdopen") as mock_fdopen:
            mock_file = MagicMock()
            mock_cm = MagicMock()
            mock_cm.__enter__ = MagicMock(return_value=mock_file)
            mock_cm.__exit__ = MagicMock(return_value=False)
            mock_fdopen.return_value = mock_cm
            run_ai_summary(digest, "copilot")
        mock_file.write.assert_called_once_with("Important content.")

    def test_temp_file_cleaned_up_on_success(self, tmp_path, copilot_io):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess(stdout="ok"):
            run_ai_summary(digest, "copilot")
        copilot_io.assert_called_once_with(FAKE_TMP_PATH)

    def test_temp_file_cleaned_up_on_subprocess_failure(self, tmp_path, copilot_io):
        """The finally block must delete the temp file even when the subprocess fails."""
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess(returncode=1, stderr="err"):
            with pytest.raises(SystemExit):
                run_ai_summary(digest, "copilot")
        copilot_io.assert_called_once_with(FAKE_TMP_PATH)

    def test_writes_summary_file(self, tmp_path, copilot_io):
        digest = make_digest(tmp_path)
        with mock_prompt(), mock_subprocess(stdout="copilot output"):
            run_ai_summary(digest, "copilot")
        summary = tmp_path / "summary_2026-02-20.md"
        assert summary.exists()
        assert summary.read_text() == "copilot output"
