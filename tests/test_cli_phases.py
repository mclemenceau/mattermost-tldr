"""Tests for the private phase helpers extracted from main()."""

import argparse
import logging
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from mattermost_tldr.cli import (
    _authenticate,
    _collect_channel_targets,
    _fetch_and_render_channels,
    _handle_existing_digest,
    _resolve_team,
    _resolve_time_window,
    _TimeWindow,
    _validate_credentials,
    _write_digest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args(**kwargs) -> argparse.Namespace:
    defaults = dict(
        today=False,
        yesterday=False,
        this_week=False,
        last_week=False,
        days=None,
        hours=None,
        digest=None,
        digest_only=False,
        backend="copilot",
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# _validate_credentials
# ---------------------------------------------------------------------------


class TestValidateCredentials:
    def test_returns_url_and_token(self):
        url, tok = _validate_credentials(
            {"server_url": "https://chat.example.com", "token": "abc123"}
        )
        assert url == "https://chat.example.com"
        assert tok == "abc123"

    def test_strips_trailing_slash_from_url(self):
        url, _ = _validate_credentials(
            {"server_url": "https://chat.example.com/", "token": "abc123"}
        )
        assert url == "https://chat.example.com"

    def test_missing_server_url_exits(self):
        with pytest.raises(SystemExit):
            _validate_credentials({"token": "abc123"})

    def test_empty_server_url_exits(self):
        with pytest.raises(SystemExit):
            _validate_credentials({"server_url": "", "token": "abc123"})

    def test_missing_token_exits(self):
        with pytest.raises(SystemExit):
            _validate_credentials({"server_url": "https://chat.example.com"})

    def test_placeholder_token_exits(self):
        with pytest.raises(SystemExit):
            _validate_credentials(
                {
                    "server_url": "https://chat.example.com",
                    "token": "your_personal_access_token_here",
                }
            )

    def test_env_var_token_overrides_config(self, monkeypatch):
        monkeypatch.setenv("MATTERMOST_TOKEN", "env_token")
        _, tok = _validate_credentials(
            {"server_url": "https://chat.example.com", "token": "config_tok"}
        )
        assert tok == "env_token"

    def test_empty_env_var_falls_back_to_config(self, monkeypatch):
        monkeypatch.setenv("MATTERMOST_TOKEN", "")
        _, tok = _validate_credentials(
            {"server_url": "https://chat.example.com", "token": "config_tok"}
        )
        assert tok == "config_tok"


# ---------------------------------------------------------------------------
# _resolve_time_window — hours mode
# ---------------------------------------------------------------------------

FIXED_NOW = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)


class TestResolveTimeWindowHours:
    def test_after_and_before_timestamps(self):
        args = _args(hours=2)
        with patch("mattermost_tldr.cli.datetime") as mock_dt:
            mock_dt.now.return_value = FIXED_NOW
            window = _resolve_time_window(args, {})

        expected_start = FIXED_NOW - timedelta(hours=2)
        assert window.after_ts == int(expected_start.timestamp() * 1000)
        assert window.before_ts == int(FIXED_NOW.timestamp() * 1000)

    def test_period_label(self):
        args = _args(hours=4)
        with patch("mattermost_tldr.cli.datetime") as mock_dt:
            mock_dt.now.return_value = FIXED_NOW
            window = _resolve_time_window(args, {})

        # FIXED_NOW is 10:00 UTC, so 4 h back = 06:00 UTC
        assert window.period_label == "2026-02-20T0600_to_2026-02-20T1000"

    def test_period_label_is_unique_per_run(self):
        """Two runs at different times must produce different labels."""
        args = _args(hours=1)
        times = [
            datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 20, 11, 0, 0, tzinfo=timezone.utc),
        ]
        labels = []
        for t in times:
            with patch("mattermost_tldr.cli.datetime") as mock_dt:
                mock_dt.now.return_value = t
                window = _resolve_time_window(args, {})
            labels.append(window.period_label)

        assert labels[0] != labels[1]

    def test_date_range_spans_midnight_boundary(self):
        # 01:00 UTC on the 20th, going back 3 hours → starts on the 19th
        midnight_plus = datetime(2026, 2, 20, 1, 0, 0, tzinfo=timezone.utc)
        args = _args(hours=3)
        with patch("mattermost_tldr.cli.datetime") as mock_dt:
            mock_dt.now.return_value = midnight_plus
            window = _resolve_time_window(args, {})

        assert window.date_from < window.date_to

    def test_returns_timewindow_instance(self):
        args = _args(hours=1)
        with patch("mattermost_tldr.cli.datetime") as mock_dt:
            mock_dt.now.return_value = FIXED_NOW
            window = _resolve_time_window(args, {})

        assert isinstance(window, _TimeWindow)


# ---------------------------------------------------------------------------
# _resolve_time_window — date mode
# ---------------------------------------------------------------------------

FIXED_DATE = date(2026, 2, 20)  # Friday


class TestResolveTimeWindowDate:
    @pytest.fixture(autouse=True)
    def freeze_today(self, monkeypatch):
        class _FrozenDate(date):
            @classmethod
            def today(cls):
                return FIXED_DATE

        monkeypatch.setattr("mattermost_tldr.cli.date", _FrozenDate)

    def test_today_flag_produces_single_day_label(self):
        window = _resolve_time_window(_args(today=True), {})
        assert window.date_from == FIXED_DATE
        assert window.date_to == FIXED_DATE
        assert window.period_label == str(FIXED_DATE)

    def test_multi_day_range_label_contains_to(self):
        window = _resolve_time_window(_args(days=3), {})
        assert "_to_" in window.period_label

    def test_after_ts_is_start_of_day_utc(self):
        window = _resolve_time_window(_args(today=True), {})
        expected = int(
            datetime(2026, 2, 20, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert window.after_ts == expected

    def test_before_ts_is_end_of_day_utc(self):
        window = _resolve_time_window(_args(today=True), {})
        expected = int(
            datetime(2026, 2, 20, 23, 59, 59, tzinfo=timezone.utc).timestamp()
            * 1000
        )
        assert window.before_ts == expected

    def test_inverted_date_range_exits(self):
        with patch(
            "mattermost_tldr.cli.date_range_from_args",
            return_value=(date(2026, 2, 20), date(2026, 2, 10)),
        ):
            with pytest.raises(SystemExit):
                _resolve_time_window(_args(), {})


# ---------------------------------------------------------------------------
# _authenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    def test_returns_me_dict_on_success(self):
        client = MagicMock()
        client.get_me.return_value = {"id": "u1", "username": "alice"}
        me = _authenticate(client)
        assert me["username"] == "alice"

    def test_http_error_exits(self):
        client = MagicMock()
        client.get_me.side_effect = requests.HTTPError("401")
        with pytest.raises(SystemExit):
            _authenticate(client)


# ---------------------------------------------------------------------------
# _resolve_team
# ---------------------------------------------------------------------------


class TestResolveTeam:
    def test_empty_team_name_returns_none_without_api_call(self):
        client = MagicMock()
        result = _resolve_team(client, "")
        assert result is None
        client.find_team.assert_not_called()

    def test_returns_team_id(self):
        client = MagicMock()
        client.find_team.return_value = {
            "id": "t1",
            "name": "myteam",
            "display_name": "My Team",
        }
        result = _resolve_team(client, "myteam")
        assert result == "t1"

    def test_value_error_exits(self):
        client = MagicMock()
        client.find_team.side_effect = ValueError("not found")
        with pytest.raises(SystemExit):
            _resolve_team(client, "nonexistent")

    def test_http_error_exits(self):
        client = MagicMock()
        client.find_team.side_effect = requests.HTTPError("503")
        with pytest.raises(SystemExit):
            _resolve_team(client, "myteam")


# ---------------------------------------------------------------------------
# _collect_channel_targets
# ---------------------------------------------------------------------------


def _make_channel(
    name: str,
    display: str | None = None,
    ch_type: str = "O",
    last_post_at: int = 9999,
) -> dict:
    return {
        "id": f"id_{name}",
        "name": name,
        "display_name": display or name.capitalize(),
        "type": ch_type,
        "last_post_at": last_post_at,
    }


class TestCollectChannelTargets:
    def test_use_all_includes_active_channels(self):
        client = MagicMock()
        after_ts = 1000
        ch_active = _make_channel("general", last_post_at=2000)
        ch_stale = _make_channel("old", last_post_at=500)
        client.get_all_channels.return_value = [ch_active, ch_stale]

        targets = _collect_channel_targets(
            client, {"id": "u1"}, None, [], True, False, after_ts
        )

        assert len(targets) == 1
        assert targets[0][1] == "General"

    def test_named_channel_found_via_team(self):
        client = MagicMock()
        ch = _make_channel("town-square")
        client.find_channel.return_value = ch

        targets = _collect_channel_targets(
            client, {"id": "u1"}, "team1", ["town-square"], False, False, 0
        )

        assert len(targets) == 1
        assert targets[0][2] == "town-square"

    def test_named_channel_not_found_is_skipped(self):
        client = MagicMock()
        client.find_channel.return_value = None
        client._get.side_effect = requests.HTTPError()

        targets = _collect_channel_targets(
            client, {"id": "u1"}, "team1", ["missing"], False, False, 0
        )

        assert targets == []

    def test_named_channel_found_via_search_fallback(self):
        client = MagicMock()
        ch = _make_channel("off-topic")
        client.find_channel.return_value = None
        client._get.return_value = ch

        targets = _collect_channel_targets(
            client, {"id": "u1"}, "team1", ["off-topic"], False, False, 0
        )

        assert len(targets) == 1

    def test_use_direct_appends_dm_channels(self):
        client = MagicMock()
        dm = _make_channel("u1__u2", ch_type="D")
        client.get_direct_channels.return_value = [dm]
        client.dm_display_name.return_value = "DM with bob"

        targets = _collect_channel_targets(
            client, {"id": "u1"}, None, [], False, True, 0
        )

        assert len(targets) == 1
        label, safe = targets[0][1], targets[0][2]
        assert label == "DM with bob"
        # "DM with " prefix replaced with "dm_"
        assert safe == "dm_bob"

    def test_use_direct_no_channels_found(self):
        client = MagicMock()
        client.get_direct_channels.return_value = []

        targets = _collect_channel_targets(
            client, {"id": "u1"}, None, [], False, True, 0
        )

        assert targets == []

    def test_use_direct_skips_stale_channels(self):
        client = MagicMock()
        dm_active = _make_channel("u1__u2", ch_type="D", last_post_at=2000)
        dm_stale = _make_channel("u1__u3", ch_type="D", last_post_at=500)
        client.get_direct_channels.return_value = [dm_active, dm_stale]
        client.dm_display_name.return_value = "DM with alice"

        targets = _collect_channel_targets(
            client, {"id": "u1"}, None, [], False, True, 1000
        )

        assert len(targets) == 1


# ---------------------------------------------------------------------------
# _fetch_and_render_channels
# ---------------------------------------------------------------------------


class TestFetchAndRenderChannels:
    def _target(self, ch_id: str = "ch1", label: str = "General"):
        return ({"id": ch_id}, label, label.lower())

    def test_renders_channels_with_posts(self):
        client = MagicMock()
        client.get_posts_in_range.return_value = [
            {"id": "p1", "create_at": 1000, "message": "hello"}
        ]

        with patch(
            "mattermost_tldr.cli.render_channel_markdown",
            return_value="# General\nhello",
        ):
            markdowns = _fetch_and_render_channels(
                client,
                [self._target()],
                0,
                9999,
                date(2026, 2, 20),
                date(2026, 2, 20),
            )

        assert markdowns == ["# General\nhello"]

    def test_skips_channels_with_no_posts(self):
        client = MagicMock()
        client.get_posts_in_range.return_value = []

        markdowns = _fetch_and_render_channels(
            client,
            [self._target()],
            0,
            9999,
            date(2026, 2, 20),
            date(2026, 2, 20),
        )

        assert markdowns == []

    def test_skips_channel_on_http_error(self):
        client = MagicMock()
        client.get_posts_in_range.side_effect = requests.HTTPError()

        markdowns = _fetch_and_render_channels(
            client,
            [self._target()],
            0,
            9999,
            date(2026, 2, 20),
            date(2026, 2, 20),
        )

        assert markdowns == []

    def test_continues_after_failed_channel(self):
        client = MagicMock()
        client.get_posts_in_range.side_effect = [
            requests.HTTPError(),
            [{"id": "p1", "create_at": 1000, "message": "hi"}],
        ]

        with patch(
            "mattermost_tldr.cli.render_channel_markdown",
            return_value="# ch2",
        ):
            markdowns = _fetch_and_render_channels(
                client,
                [self._target("ch1"), self._target("ch2")],
                0,
                9999,
                date(2026, 2, 20),
                date(2026, 2, 20),
            )

        assert markdowns == ["# ch2"]


# ---------------------------------------------------------------------------
# _write_digest
# ---------------------------------------------------------------------------


class TestWriteDigest:
    def test_writes_file_and_returns_path(self, tmp_path):
        path = _write_digest(["# Content"], tmp_path, "2026-02-20")
        assert path is not None
        assert path.exists()
        assert path.name == "digest_2026-02-20.md"
        assert "# Content" in path.read_text()

    def test_joins_multiple_markdowns_with_separator(self, tmp_path):
        path = _write_digest(["A", "B"], tmp_path, "test")
        assert path is not None
        assert "---" in path.read_text()

    def test_empty_markdowns_returns_none(self, tmp_path):
        result = _write_digest([], tmp_path, "2026-02-20")
        assert result is None

    def test_empty_markdowns_creates_no_file(self, tmp_path):
        _write_digest([], tmp_path, "2026-02-20")
        assert not (tmp_path / "digest_2026-02-20.md").exists()


# ---------------------------------------------------------------------------
# _handle_existing_digest
# ---------------------------------------------------------------------------


class TestHandleExistingDigest:
    def test_exits_if_digest_file_not_found(self, tmp_path):
        args = _args(digest=str(tmp_path / "nope.md"), backend="copilot")
        with pytest.raises(SystemExit):
            _handle_existing_digest(args)

    def test_calls_run_ai_summary_with_correct_args(self, tmp_path):
        digest_file = tmp_path / "digest.md"
        digest_file.write_text("content")
        args = _args(digest=str(digest_file), backend="copilot")

        with patch("mattermost_tldr.cli.run_ai_summary") as mock_summary:
            _handle_existing_digest(args)

        mock_summary.assert_called_once_with(digest_file, "copilot")

    def test_digest_only_note_is_logged(self, tmp_path, caplog):
        digest_file = tmp_path / "digest.md"
        digest_file.write_text("content")
        args = _args(
            digest=str(digest_file), digest_only=True, backend="copilot"
        )

        with patch("mattermost_tldr.cli.run_ai_summary"):
            with caplog.at_level(logging.INFO, logger="mattermost_tldr.cli"):
                _handle_existing_digest(args)

        assert any(
            "--digest-only has no effect" in r.message for r in caplog.records
        )

    def test_digest_only_false_no_note_logged(self, tmp_path, caplog):
        digest_file = tmp_path / "digest.md"
        digest_file.write_text("content")
        args = _args(
            digest=str(digest_file), digest_only=False, backend="copilot"
        )

        with patch("mattermost_tldr.cli.run_ai_summary"):
            with caplog.at_level(logging.INFO, logger="mattermost_tldr.cli"):
                _handle_existing_digest(args)

        assert not any(
            "--digest-only has no effect" in r.message for r in caplog.records
        )
