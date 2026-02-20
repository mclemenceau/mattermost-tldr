"""Tests for build_arg_parser."""

import pytest
from mattermost_tldr.cli import build_arg_parser, BACKENDS


@pytest.fixture
def parser():
    return build_arg_parser()


class TestBackendArg:
    def test_default_backend_is_copilot(self, parser):
        args = parser.parse_args(["--today"])
        assert args.backend == "copilot"

    def test_backend_claude(self, parser):
        args = parser.parse_args(["--today", "--backend", "claude"])
        assert args.backend == "claude"

    def test_all_defined_backends_accepted(self, parser):
        for backend in BACKENDS:
            args = parser.parse_args(["--today", "--backend", backend])
            assert args.backend == backend

    def test_invalid_backend_exits(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["--today", "--backend", "gpt4"])


class TestDateFlags:
    def test_today(self, parser):
        args = parser.parse_args(["--today"])
        assert args.today is True
        assert args.yesterday is False

    def test_yesterday(self, parser):
        args = parser.parse_args(["--yesterday"])
        assert args.yesterday is True
        assert args.today is False

    def test_this_week(self, parser):
        args = parser.parse_args(["--this-week"])
        assert args.this_week is True

    def test_last_week(self, parser):
        args = parser.parse_args(["--last-week"])
        assert args.last_week is True

    def test_days(self, parser):
        args = parser.parse_args(["--days", "7"])
        assert args.days == 7

    def test_hours(self, parser):
        args = parser.parse_args(["--hours", "4"])
        assert args.hours == 4

    def test_date_flags_mutually_exclusive(self, parser):
        pairs = [
            ["--today", "--yesterday"],
            ["--today", "--this-week"],
            ["--today", "--last-week"],
            ["--today", "--days", "3"],
            ["--today", "--hours", "4"],
            ["--yesterday", "--this-week"],
        ]
        for pair in pairs:
            with pytest.raises(SystemExit):
                parser.parse_args(pair)

    def test_no_date_flag_is_allowed(self, parser):
        # No date flag → args parsed without error (config fallback handles it at runtime)
        args = parser.parse_args([])
        assert args.today is False
        assert args.yesterday is False
        assert args.this_week is False
        assert args.last_week is False
        assert args.days is None
        assert args.hours is None


class TestChannelFlags:
    def test_all_channels_default_false(self, parser):
        args = parser.parse_args(["--today"])
        assert args.all_channels is False

    def test_all_channels_flag(self, parser):
        args = parser.parse_args(["--today", "--all-channels"])
        assert args.all_channels is True

    def test_direct_default_false(self, parser):
        args = parser.parse_args(["--today"])
        assert args.direct is False

    def test_direct_flag(self, parser):
        args = parser.parse_args(["--today", "--direct"])
        assert args.direct is True


class TestOutputFlags:
    def test_digest_only_default_false(self, parser):
        args = parser.parse_args(["--today"])
        assert args.digest_only is False

    def test_digest_only_flag(self, parser):
        args = parser.parse_args(["--today", "--digest-only"])
        assert args.digest_only is True

    def test_digest_default_none(self, parser):
        args = parser.parse_args(["--today"])
        assert args.digest is None

    def test_digest_path(self, parser):
        args = parser.parse_args(["--digest", "/some/path/digest.md"])
        assert args.digest == "/some/path/digest.md"

    def test_digest_and_digest_only_coexist(self, parser):
        # Both flags together are allowed (main() prints a note, not an error)
        args = parser.parse_args(["--digest", "file.md", "--digest-only"])
        assert args.digest == "file.md"
        assert args.digest_only is True


class TestConfigFlag:
    def test_default_config_path_set(self, parser):
        args = parser.parse_args(["--today"])
        assert "mattermost-tldr" in args.config

    def test_custom_config_path(self, parser):
        args = parser.parse_args(["--today", "--config", "/custom/config.yaml"])
        assert args.config == "/custom/config.yaml"
