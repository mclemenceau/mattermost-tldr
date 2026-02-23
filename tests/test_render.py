"""Tests for render_post and render_channel_markdown."""

import datetime as dt
from unittest.mock import MagicMock

from mattermost_tldr.render import render_channel_markdown, render_post

# A fixed base timestamp: 2026-02-20 10:00:00 UTC
TS_BASE = int(
    dt.datetime(2026, 2, 20, 10, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    * 1000
)
DATE_BASE = dt.date(2026, 2, 20)


def make_client(usernames=None):
    client = MagicMock()
    client.server_url = "https://mattermost.example.com"
    client.get_username.side_effect = lambda uid: (usernames or {}).get(
        uid, uid
    )
    return client


def make_post(post_id, user_id, message, create_at=TS_BASE, root_id=""):
    return {
        "id": post_id,
        "user_id": user_id,
        "message": message,
        "create_at": create_at,
        "root_id": root_id,
    }


def make_channel(ch_type="O", name="general", display_name="General"):
    return {
        "id": "chan1",
        "name": name,
        "display_name": display_name,
        "type": ch_type,
    }


# ---------------------------------------------------------------------------
# render_post
# ---------------------------------------------------------------------------


class TestRenderPost:
    def test_single_line(self):
        client = make_client({"u1": "alice"})
        post = make_post("p1", "u1", "Hello world")
        result = render_post(post, client)
        assert result.startswith("**alice**")
        assert "Hello world" in result

    def test_single_line_format(self):
        client = make_client({"u1": "alice"})
        post = make_post("p1", "u1", "Hi there")
        result = render_post(post, client)
        # Single-line: "**user** [HH:MM]: message"
        assert ": Hi there" in result

    def test_multi_line(self):
        client = make_client({"u1": "bob"})
        post = make_post("p1", "u1", "Line one\nLine two\nLine three")
        result = render_post(post, client)
        assert "**bob**" in result
        assert "Line one" in result
        assert "Line two" in result
        assert "Line three" in result
        # Multi-line uses colon + newline format
        assert ":\n" in result

    def test_empty_message_returns_empty_string(self):
        client = make_client()
        post = make_post("p1", "u1", "   \n  \n  ")
        assert render_post(post, client) == ""

    def test_blank_lines_stripped_from_message(self):
        client = make_client({"u1": "charlie"})
        post = make_post("p1", "u1", "First\n\n\nSecond")
        result = render_post(post, client)
        assert "First" in result
        assert "Second" in result

    def test_indent_prepended(self):
        client = make_client({"u1": "dave"})
        post = make_post("p1", "u1", "Reply here")
        result = render_post(post, client, indent="  ↳ ")
        assert result.startswith("  ↳ **dave**")

    def test_time_in_brackets(self):
        client = make_client({"u1": "eve"})
        ts = int(
            dt.datetime(
                2026, 2, 20, 14, 35, 0, tzinfo=dt.timezone.utc
            ).timestamp()
            * 1000
        )
        post = make_post("p1", "u1", "Hi", create_at=ts)
        result = render_post(post, client)
        assert "[14:35]" in result

    def test_username_resolved(self):
        client = make_client({"uid_xyz": "frank"})
        post = make_post("p1", "uid_xyz", "Hello")
        result = render_post(post, client)
        assert "**frank**" in result
        assert "uid_xyz" not in result

    def test_whitespace_only_lines_stripped(self):
        client = make_client({"u1": "grace"})
        post = make_post("p1", "u1", "  \n  valid  \n  ")
        result = render_post(post, client)
        assert "valid" in result


# ---------------------------------------------------------------------------
# render_channel_markdown
# ---------------------------------------------------------------------------


class TestRenderChannelMarkdown:
    def test_no_posts_shows_placeholder(self):
        client = make_client()
        result = render_channel_markdown(
            make_channel(), [], client, DATE_BASE, DATE_BASE
        )
        assert "*No messages in this period.*" in result

    def test_channel_header_type(self):
        client = make_client()
        result = render_channel_markdown(
            make_channel(ch_type="O"), [], client, DATE_BASE, DATE_BASE
        )
        assert "# Mattermost Channel: General" in result

    def test_dm_header_type(self):
        client = make_client()
        ch = make_channel(ch_type="D", name="u1__u2", display_name="")
        result = render_channel_markdown(
            ch, [], client, DATE_BASE, DATE_BASE, display_name="DM with alice"
        )
        assert "# Mattermost Direct Message: DM with alice" in result

    def test_group_dm_header_type(self):
        client = make_client()
        ch = make_channel(ch_type="G", name="group123", display_name="My Group")
        result = render_channel_markdown(ch, [], client, DATE_BASE, DATE_BASE)
        assert "# Mattermost Direct Message: My Group" in result

    def test_server_url_in_header(self):
        client = make_client()
        result = render_channel_markdown(
            make_channel(), [], client, DATE_BASE, DATE_BASE
        )
        assert "https://mattermost.example.com" in result

    def test_period_in_header(self):
        client = make_client()
        result = render_channel_markdown(
            make_channel(),
            [],
            client,
            dt.date(2026, 2, 1),
            dt.date(2026, 2, 20),
        )
        assert "2026-02-01" in result
        assert "2026-02-20" in result

    def test_display_name_override(self):
        client = make_client()
        ch = make_channel(name="some-slug", display_name="Original")
        result = render_channel_markdown(
            ch, [], client, DATE_BASE, DATE_BASE, display_name="Override"
        )
        assert "Override" in result
        assert "Original" not in result

    def test_post_rendered(self):
        client = make_client({"u1": "alice"})
        post = make_post("p1", "u1", "Hello channel")
        result = render_channel_markdown(
            make_channel(), [post], client, DATE_BASE, DATE_BASE
        )
        assert "Hello channel" in result
        assert "**alice**" in result

    def test_thread_reply_nested_after_root(self):
        client = make_client({"u1": "alice", "u2": "bob"})
        root = make_post("root1", "u1", "Root message")
        reply = make_post(
            "reply1",
            "u2",
            "Reply message",
            create_at=TS_BASE + 60_000,
            root_id="root1",
        )
        result = render_channel_markdown(
            make_channel(), [root, reply], client, DATE_BASE, DATE_BASE
        )
        root_pos = result.index("Root message")
        reply_pos = result.index("Reply message")
        assert root_pos < reply_pos

    def test_thread_reply_indented(self):
        client = make_client({"u1": "alice", "u2": "bob"})
        root = make_post("root1", "u1", "Root message")
        reply = make_post(
            "reply1",
            "u2",
            "Reply message",
            create_at=TS_BASE + 60_000,
            root_id="root1",
        )
        result = render_channel_markdown(
            make_channel(), [root, reply], client, DATE_BASE, DATE_BASE
        )
        assert "  ↳ **bob**" in result

    def test_unrelated_posts_not_nested(self):
        client = make_client({"u1": "alice", "u2": "bob"})
        p1 = make_post("p1", "u1", "First post")
        p2 = make_post("p2", "u2", "Second post", create_at=TS_BASE + 60_000)
        result = render_channel_markdown(
            make_channel(), [p1, p2], client, DATE_BASE, DATE_BASE
        )
        # Neither post should have the reply indent
        lines = result.splitlines()
        alice_line = next(ln for ln in lines if "First post" in ln)
        bob_line = next(ln for ln in lines if "Second post" in ln)
        assert not alice_line.startswith("  ↳")
        assert not bob_line.startswith("  ↳")

    def test_posts_grouped_by_day(self):
        client = make_client({"u1": "alice"})
        ts_thu = int(
            dt.datetime(
                2026, 2, 19, 10, 0, 0, tzinfo=dt.timezone.utc
            ).timestamp()
            * 1000
        )
        ts_fri = int(
            dt.datetime(
                2026, 2, 20, 10, 0, 0, tzinfo=dt.timezone.utc
            ).timestamp()
            * 1000
        )
        p1 = make_post("p1", "u1", "Thursday message", create_at=ts_thu)
        p2 = make_post("p2", "u1", "Friday message", create_at=ts_fri)
        result = render_channel_markdown(
            make_channel(),
            [p1, p2],
            client,
            dt.date(2026, 2, 19),
            dt.date(2026, 2, 20),
        )
        assert "Thursday, 2026-02-19" in result
        assert "Friday, 2026-02-20" in result

    def test_day_headers_in_chronological_order(self):
        client = make_client({"u1": "alice"})
        ts_thu = int(
            dt.datetime(
                2026, 2, 19, 10, 0, 0, tzinfo=dt.timezone.utc
            ).timestamp()
            * 1000
        )
        ts_fri = int(
            dt.datetime(
                2026, 2, 20, 10, 0, 0, tzinfo=dt.timezone.utc
            ).timestamp()
            * 1000
        )
        p1 = make_post("p1", "u1", "Thursday", create_at=ts_thu)
        p2 = make_post("p2", "u1", "Friday", create_at=ts_fri)
        result = render_channel_markdown(
            make_channel(),
            [p1, p2],
            client,
            dt.date(2026, 2, 19),
            dt.date(2026, 2, 20),
        )
        thu_pos = result.index("Thursday, 2026-02-19")
        fri_pos = result.index("Friday, 2026-02-20")
        assert thu_pos < fri_pos

    def test_empty_post_message_excluded(self):
        client = make_client({"u1": "alice"})
        empty_post = make_post("p1", "u1", "   ")
        result = render_channel_markdown(
            make_channel(), [empty_post], client, DATE_BASE, DATE_BASE
        )
        # Empty post should not appear; channel header still should
        assert "**alice**" not in result
