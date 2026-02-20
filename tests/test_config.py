"""Tests for load_config and ensure_prompt_file."""

from unittest.mock import patch

import pytest

from mattermost_tldr.cli import DEFAULT_PROMPT, ensure_prompt_file, load_config


class TestLoadConfig:
    def test_loads_valid_yaml(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("server_url: https://example.com\ntoken: abc123\n")
        result = load_config(cfg)
        assert result["server_url"] == "https://example.com"
        assert result["token"] == "abc123"

    def test_exits_if_file_missing(self, tmp_path):
        with pytest.raises(SystemExit):
            load_config(tmp_path / "nonexistent.yaml")

    def test_returns_empty_dict_for_empty_file(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("")
        result = load_config(cfg)
        assert result == {}

    def test_loads_nested_values(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("channels:\n  - general\n  - random\n")
        result = load_config(cfg)
        assert result["channels"] == ["general", "random"]

    def test_exits_with_nonzero_code(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            load_config(tmp_path / "missing.yaml")
        assert exc_info.value.code != 0


class TestEnsurePromptFile:
    def test_creates_file_if_missing(self, tmp_path):
        prompt_path = tmp_path / "prompt.md"
        with (
            patch("mattermost_tldr.cli.CONFIG_DIR", tmp_path),
            patch("mattermost_tldr.cli.PROMPT_FILE", prompt_path),
        ):
            result = ensure_prompt_file()
        assert prompt_path.exists()
        assert result == DEFAULT_PROMPT

    def test_written_content_matches_default_prompt(self, tmp_path):
        prompt_path = tmp_path / "prompt.md"
        with (
            patch("mattermost_tldr.cli.CONFIG_DIR", tmp_path),
            patch("mattermost_tldr.cli.PROMPT_FILE", prompt_path),
        ):
            ensure_prompt_file()
        assert prompt_path.read_text(encoding="utf-8") == DEFAULT_PROMPT

    def test_does_not_overwrite_existing_file(self, tmp_path):
        prompt_path = tmp_path / "prompt.md"
        prompt_path.write_text("My custom prompt", encoding="utf-8")
        with (
            patch("mattermost_tldr.cli.CONFIG_DIR", tmp_path),
            patch("mattermost_tldr.cli.PROMPT_FILE", prompt_path),
        ):
            result = ensure_prompt_file()
        assert result == "My custom prompt"

    def test_creates_config_dir_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        prompt_path = nested / "prompt.md"
        with (
            patch("mattermost_tldr.cli.CONFIG_DIR", nested),
            patch("mattermost_tldr.cli.PROMPT_FILE", prompt_path),
        ):
            ensure_prompt_file()
        assert nested.is_dir()
        assert prompt_path.exists()
