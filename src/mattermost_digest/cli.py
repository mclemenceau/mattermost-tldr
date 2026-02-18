#!/usr/bin/env python3
"""
mattermost-digest — Export Mattermost channel messages to LLM-ready markdown.

Usage:
    mattermost-digest                        # uses config.yaml, dates from config
    mattermost-digest --today
    mattermost-digest --yesterday
    mattermost-digest --this-week
    mattermost-digest --last-week
    mattermost-digest --days 3              # last 3 days
    mattermost-digest --all-channels        # export all subscribed channels
    mattermost-digest --direct              # also fetch direct/group messages
    mattermost-digest --all-channels --direct  # everything
    mattermost-digest --config path/to/config.yaml --today
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml


# ---------------------------------------------------------------------------
# Date range helpers
# ---------------------------------------------------------------------------

def date_range_from_args(args, config: dict) -> tuple[date, date]:
    """Resolve the effective (date_from, date_to) from CLI flags and config."""
    today = date.today()

    if args.today:
        return today, today
    if args.yesterday:
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if args.this_week:
        # Monday → today
        monday = today - timedelta(days=today.weekday())
        return monday, today
    if args.last_week:
        # Last Monday → last Sunday
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_sunday = last_monday + timedelta(days=6)
        return last_monday, last_sunday
    if args.days is not None:
        start = today - timedelta(days=args.days - 1)
        return start, today

    # Fall back to config file values
    raw_from = config.get("date_from")
    raw_to   = config.get("date_to", str(today))

    if not raw_from:
        print("Error: No date range specified. Use a CLI flag (--today, --yesterday, "
              "--this-week, --last-week, --days N) or set date_from in config.", file=sys.stderr)
        sys.exit(1)

    try:
        date_from = date.fromisoformat(str(raw_from))
        date_to   = date.fromisoformat(str(raw_to))
    except ValueError as e:
        print(f"Error parsing date from config: {e}", file=sys.stderr)
        sys.exit(1)

    return date_from, date_to


# ---------------------------------------------------------------------------
# Mattermost API client
# ---------------------------------------------------------------------------

class MattermostClient:
    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.base_url   = self.server_url + "/api/v4"
        self.session    = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        self._user_cache: dict[str, str] = {}

    def _get(self, path: str, params: dict | None = None):
        resp = self.session.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_me(self) -> dict:
        return self._get("/users/me")

    def find_team(self, team_name: str) -> dict:
        teams = self._get("/teams")
        for t in teams:
            if t["name"] == team_name or t["display_name"] == team_name:
                return t
        names = [t["name"] for t in teams]
        raise ValueError(f"Team '{team_name}' not found. Available teams: {names}")

    def find_channel(self, team_id: str, channel_name: str) -> dict | None:
        try:
            return self._get(f"/teams/{team_id}/channels/name/{channel_name}")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def _fetch_member_channels(self, user_id: str, team_id: str | None) -> list[dict]:
        """Return all channels the user is a member of (any type)."""
        if team_id:
            return self._get(f"/users/{user_id}/teams/{team_id}/channels")
        teams = self._get("/teams")
        if not teams:
            return []
        return self._get(f"/users/{user_id}/teams/{teams[0]['id']}/channels")

    def get_direct_channels(self, user_id: str, team_id: str | None) -> list[dict]:
        """Return all DM (type D) and group DM (type G) channels, sorted by last activity."""
        channels = [ch for ch in self._fetch_member_channels(user_id, team_id)
                    if ch.get("type") in ("D", "G")]
        return sorted(channels, key=lambda ch: ch.get("last_post_at", 0), reverse=True)

    def get_all_channels(self, user_id: str, team_id: str | None) -> list[dict]:
        """Return all subscribed open (O) and private (P) channels, sorted by last activity."""
        channels = [ch for ch in self._fetch_member_channels(user_id, team_id)
                    if ch.get("type") in ("O", "P")]
        return sorted(channels, key=lambda ch: ch.get("last_post_at", 0), reverse=True)

    def dm_display_name(self, channel: dict, current_user_id: str) -> str:
        """Human-readable name for a DM or group-DM channel."""
        if channel.get("type") == "D":
            # channel name is  userId1__userId2
            parts    = channel["name"].split("__")
            other_id = next((p for p in parts if p != current_user_id), parts[0])
            return f"DM with {self.get_username(other_id)}"
        # Group DM: display_name is already populated by Mattermost
        return channel.get("display_name") or "Group DM"

    def get_username(self, user_id: str) -> str:
        if user_id not in self._user_cache:
            try:
                user = self._get(f"/users/{user_id}")
                self._user_cache[user_id] = user.get("username", user_id)
            except requests.HTTPError:
                self._user_cache[user_id] = user_id
        return self._user_cache[user_id]

    def get_posts_in_range(
        self,
        channel_id: str,
        after_ts: int,   # Unix ms, inclusive
        before_ts: int,  # Unix ms, inclusive
    ) -> list[dict]:
        """
        Fetch all posts in a channel within [after_ts, before_ts].
        Paginates backwards from newest using the `before` post-ID cursor.
        Returns posts sorted oldest-first.
        """
        posts = []
        before_id: str | None = None
        per_page = 200

        while True:
            params: dict = {"per_page": per_page}
            if before_id:
                params["before"] = before_id

            data = self._get(f"/channels/{channel_id}/posts", params=params)
            order     = data.get("order", [])      # newest → oldest
            posts_map = data.get("posts", {})

            if not order:
                break

            oldest_ts_in_batch = None

            for post_id in order:
                post = posts_map.get(post_id)
                if post is None:
                    continue
                ts = post["create_at"]
                if oldest_ts_in_batch is None or ts < oldest_ts_in_batch:
                    oldest_ts_in_batch = ts
                if after_ts <= ts <= before_ts:
                    posts.append(post)

            # Stop if the oldest post in this batch is before our window
            if oldest_ts_in_batch is not None and oldest_ts_in_batch < after_ts:
                break

            # Stop if we got a partial page (no more posts)
            if len(order) < per_page:
                break

            # Cursor: continue from the oldest post in this page
            before_id = order[-1]

        return sorted(posts, key=lambda p: p["create_at"])


# ---------------------------------------------------------------------------
# Markdown renderer (LLM-optimised)
# ---------------------------------------------------------------------------

def ts_to_datetime(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def format_day_header(d: date) -> str:
    return d.strftime("%A, %Y-%m-%d")


def render_post(post: dict, client: MattermostClient, indent: str = "") -> str:
    username = client.get_username(post["user_id"])
    dt       = ts_to_datetime(post["create_at"])
    message  = post.get("message", "").strip()

    # Collapse blank lines inside a single post to keep output tight
    message = "\n".join(line for line in message.splitlines() if line.strip())

    if not message:
        return ""

    prefix = f"{indent}**{username}** [{format_time(dt)}]"

    # Multi-line messages: indent continuation lines
    lines = message.splitlines()
    if len(lines) == 1:
        return f"{prefix}: {lines[0]}"
    else:
        body = f"\n{indent}  ".join(lines)
        return f"{prefix}:\n{indent}  {body}"


def render_channel_markdown(
    channel: dict,
    posts: list[dict],
    client: MattermostClient,
    date_from: date,
    date_to: date,
    display_name: str | None = None,
) -> str:
    channel_name    = channel.get("name", "unknown")
    channel_display = display_name or channel.get("display_name") or f"#{channel_name}"
    server_url      = client.server_url

    lines: list[str] = []

    is_dm = channel.get("type") in ("D", "G")
    title = f"Mattermost {'Direct Message' if is_dm else 'Channel'}: {channel_display}"

    # Document header — gives the LLM clear context
    lines += [
        f"# {title}",
        f"",
        f"**Display name:** {channel_display}  ",
        f"**Server:** {server_url}  ",
        f"**Period:** {date_from} to {date_to}  ",
        f"**Exported:** {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"",
        f"---",
        f"",
    ]

    if not posts:
        lines.append("*No messages in this period.*")
        return "\n".join(lines)

    # Group posts by day and organise threads
    posts_by_day: dict[date, list[dict]] = defaultdict(list)
    for post in posts:
        day = ts_to_datetime(post["create_at"]).date()
        posts_by_day[day].append(post)

    for day in sorted(posts_by_day):
        lines.append(f"## {format_day_header(day)}")
        lines.append("")

        day_posts = posts_by_day[day]

        # Separate top-level posts from replies
        top_level: list[dict]            = []
        replies:   dict[str, list[dict]] = defaultdict(list)

        for post in day_posts:
            root_id = post.get("root_id", "")
            if root_id:
                replies[root_id].append(post)
            else:
                top_level.append(post)

        for post in top_level:
            rendered = render_post(post, client)
            if rendered:
                lines.append(rendered)

            # Inline thread replies, indented
            for reply in replies.get(post["id"], []):
                rendered_reply = render_post(reply, client, indent="  ↳ ")
                if rendered_reply:
                    lines.append(rendered_reply)

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = Path.home() / ".config" / "mattermost-digest" / "config.yaml"


def load_config(path: Path) -> dict:
    if not path.exists():
        print(f"Error: Config file not found: {path}", file=sys.stderr)
        print(f"Copy config.example.yaml to {DEFAULT_CONFIG} and fill in your details.", file=sys.stderr)
        sys.exit(1)
    with path.open() as f:
        return yaml.safe_load(f) or {}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export Mattermost channel messages to LLM-ready markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Date range (CLI flags override config file):
  --today         Export today's messages
  --yesterday     Export yesterday's messages
  --this-week     Export from Monday of the current week to today
  --last-week     Export last Monday–Sunday
  --days N        Export the last N days (including today)

Channel selection:
  --all-channels  Export all channels you are subscribed to (ignores channels list in config)
                  (also enabled by setting  all_channels: true  in config)
  --direct        Also export direct/group messages
                  (also enabled by setting  direct_messages: true  in config)

If no date flag is given, date_from / date_to from the config file are used.
        """,
    )
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG), metavar="FILE",
        help=f"Path to YAML config file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--all-channels", action="store_true",
        help="Export all subscribed channels (ignores channels list in config)",
    )
    parser.add_argument(
        "--direct", action="store_true",
        help="Also export direct/group messages",
    )

    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--today",     action="store_true", help="Export today")
    date_group.add_argument("--yesterday", action="store_true", help="Export yesterday")
    date_group.add_argument("--this-week", action="store_true", help="Export Mon–today")
    date_group.add_argument("--last-week", action="store_true", help="Export last Mon–Sun")
    date_group.add_argument("--days", type=int, metavar="N", help="Export last N days")

    return parser


def main():
    parser = build_arg_parser()
    args   = parser.parse_args()

    config = load_config(Path(args.config))

    server_url = config.get("server_url", "").rstrip("/")
    token      = os.environ.get("MATTERMOST_TOKEN") or config.get("token", "")
    team_name  = config.get("team", "")
    channels   = config.get("channels", [])
    output_dir = Path(config.get("output_dir", "./exports"))

    if not server_url:
        print("Error: server_url is required in config.", file=sys.stderr)
        sys.exit(1)
    if not token or token == "your_personal_access_token_here":
        print("Error: Set your token in config.yaml or via MATTERMOST_TOKEN env var.", file=sys.stderr)
        sys.exit(1)
    use_all    = args.all_channels or config.get("all_channels", False)
    use_direct = args.direct or config.get("direct_messages", False)

    if not use_all and not use_direct and not channels:
        print("Error: No channels specified in config and neither all_channels nor "
              "direct_messages is enabled. Add channels to config, or use --all-channels "
              "and/or --direct.", file=sys.stderr)
        sys.exit(1)

    date_from, date_to = date_range_from_args(args, config)

    if date_to < date_from:
        print(f"Error: date_to ({date_to}) is before date_from ({date_from}).", file=sys.stderr)
        sys.exit(1)

    # Convert dates to Unix ms timestamps (start of day / end of day, UTC)
    after_ts  = int(datetime(date_from.year, date_from.month, date_from.day,
                             tzinfo=timezone.utc).timestamp() * 1000)
    before_ts = int(datetime(date_to.year, date_to.month, date_to.day,
                             23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    print(f"Period  : {date_from} → {date_to}")
    print(f"Server  : {server_url}")

    client = MattermostClient(server_url, token)

    # Verify credentials
    try:
        me = client.get_me()
        print(f"Logged in as: {me['username']}")
    except requests.HTTPError as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve team
    try:
        team    = client.find_team(team_name) if team_name else None
        team_id = team["id"] if team else None
        if team:
            print(f"Team    : {team['display_name']} ({team['name']})")
    except (ValueError, requests.HTTPError) as e:
        print(f"Error resolving team: {e}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    period_label = f"{date_from}_to_{date_to}" if date_from != date_to else str(date_from)

    # Build the list of (channel_dict, display_name, filename_stem) to export
    export_targets: list[tuple[dict, str, str]] = []

    if use_all:
        print("Fetching all subscribed channels ...", end=" ", flush=True)
        all_chans = client.get_all_channels(me["id"], team_id)
        in_range = sum(1 for ch in all_chans if ch.get("last_post_at", 0) >= after_ts)
        print(f"{len(all_chans)} found, {in_range} active in period.")
        for ch in all_chans:
            if ch.get("last_post_at", 0) < after_ts:
                break
            label = ch.get("display_name") or ch["name"]
            export_targets.append((ch, label, ch["name"]))
    else:
        for channel_name in channels:
            channel = None
            if team_id:
                channel = client.find_channel(team_id, channel_name)
            if channel is None:
                try:
                    channel = client._get("/channels/search", params={"term": channel_name})
                except Exception:
                    pass
            if channel is None:
                print(f"\n  #{channel_name} ... not found, skipping.")
                continue
            label = channel.get("display_name") or f"#{channel_name}"
            export_targets.append((channel, label, channel_name))

    if use_direct:
        print("Fetching direct message channels ...", end=" ", flush=True)
        dm_channels = client.get_direct_channels(me["id"], team_id)
        if not dm_channels:
            print("none found.")
        else:
            in_range = sum(1 for ch in dm_channels if ch.get("last_post_at", 0) >= after_ts)
            print(f"{len(dm_channels)} found, {in_range} active in period.")
            print("Resolving channel names ...", flush=True)
            for ch in dm_channels:
                if ch.get("last_post_at", 0) < after_ts:
                    break
                label = client.dm_display_name(ch, me["id"])
                # Safe filename: strip spaces and slashes
                safe  = label.replace("DM with ", "dm_").replace(" ", "_").replace("/", "_")
                export_targets.append((ch, label, safe))

    all_markdowns: list[str] = []

    for channel, display_name, filename_stem in export_targets:
        print(f"\n  {display_name} ...", end=" ", flush=True)

        try:
            posts = client.get_posts_in_range(channel["id"], after_ts, before_ts)
        except requests.HTTPError as e:
            print(f"error fetching posts: {e}")
            continue

        print(f"{len(posts)} messages")

        if not posts:
            continue

        markdown = render_channel_markdown(
            channel, posts, client, date_from, date_to, display_name=display_name
        )
        all_markdowns.append(markdown)

    if all_markdowns:
        filename    = f"digest_{period_label}.md"
        output_path = output_dir / filename
        output_path.write_text("\n\n---\n\n".join(all_markdowns), encoding="utf-8")
        print(f"\n→ Written to {output_path}")
    else:
        print("\nNo messages found for the given period.")

    print("\nDone.")
