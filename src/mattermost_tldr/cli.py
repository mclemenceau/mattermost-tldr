#!/usr/bin/env python3
"""
mattermost-tldr — Export Mattermost messages to markdown and summarize with AI.

Usage:
    mattermost-tldr --today           # digest + AI summary (default)
    mattermost-tldr --today --digest-only         # export digest only, no AI
    mattermost-tldr --digest path/to/digest.md  # summarize an existing digest
    mattermost-tldr --backend claude --today    # use Claude instead of Copilot
    mattermost-tldr --yesterday
    mattermost-tldr --this-week
    mattermost-tldr --last-week
    mattermost-tldr --days 3
    mattermost-tldr --hours 4
    mattermost-tldr --all-channels
    mattermost-tldr --direct
"""

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import requests
import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AI backend configuration
# ---------------------------------------------------------------------------

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

DEFAULT_PROMPT = """\
You are my personal Mattermost assistant. Analyze the digest below and give me a
concise, actionable summary. Focus on:

## What I need to follow up on
List any open questions, requests, or action items directed at me or
left unanswered.

## What is most important
Highlight decisions made, critical updates, or anything that needs my
attention soon.

## People
Pay special attention to messages from or about the following people:
- (add names here)

## Keywords to watch for
Flag any messages containing:
- (add keywords here, e.g. "urgent", "deadline", "blocker")

---
Keep the summary structured and brief. Skip channels or threads with
no meaningful activity.
"""

CONFIG_DIR = Path.home() / ".config" / "mattermost-tldr"
PROMPT_FILE = CONFIG_DIR / "prompt.md"


# ---------------------------------------------------------------------------
# Date range helpers
# ---------------------------------------------------------------------------


def date_range_from_args(
    args: argparse.Namespace, config: dict
) -> tuple[date, date]:
    """Resolve the effective (date_from, date_to) from CLI flags and config."""
    today = date.today()

    if args.today:
        return today, today
    if args.yesterday:
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if args.this_week:
        monday = today - timedelta(days=today.weekday())
        return monday, today
    if args.last_week:
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_sunday = last_monday + timedelta(days=6)
        return last_monday, last_sunday
    if args.days is not None:
        start = today - timedelta(days=args.days - 1)
        return start, today

    # Fall back to config file values
    raw_from = config.get("date_from")
    raw_to = config.get("date_to", str(today))

    if not raw_from:
        log.error(
            "Error: No date range specified. Use a CLI flag"
            " (--today, --yesterday, --this-week, --last-week,"
            " --days N, --hours H) or set date_from in config."
        )
        sys.exit(1)

    try:
        date_from = date.fromisoformat(str(raw_from))
        date_to = date.fromisoformat(str(raw_to))
    except ValueError as e:
        log.error("Error parsing date from config: %s", e)
        sys.exit(1)

    return date_from, date_to


# ---------------------------------------------------------------------------
# Mattermost API client
# ---------------------------------------------------------------------------


class MattermostClient:
    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.base_url = self.server_url + "/api/v4"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )
        self._user_cache: dict[str, str] = {}

    def _get(self, path: str, params: dict | None = None):
        resp = self.session.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_me(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._get("/users/me"))

    def find_team(self, team_name: str) -> dict[str, Any]:
        teams = cast(list[dict[str, Any]], self._get("/teams"))
        for t in teams:
            if t["name"] == team_name or t["display_name"] == team_name:
                return t
        names = [t["name"] for t in teams]
        raise ValueError(
            f"Team '{team_name}' not found. Available teams: {names}"
        )

    def find_channel(
        self, team_id: str, channel_name: str
    ) -> dict[str, Any] | None:
        try:
            return cast(
                dict[str, Any],
                self._get(f"/teams/{team_id}/channels/name/{channel_name}"),
            )
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def _fetch_member_channels(
        self, user_id: str, team_id: str | None
    ) -> list[dict[str, Any]]:
        """Return all channels the user is a member of (any type)."""
        if team_id:
            return cast(
                list[dict[str, Any]],
                self._get(f"/users/{user_id}/teams/{team_id}/channels"),
            )
        teams = cast(list[dict[str, Any]], self._get("/teams"))
        if not teams:
            return []
        return cast(
            list[dict[str, Any]],
            self._get(f"/users/{user_id}/teams/{teams[0]['id']}/channels"),
        )

    def get_direct_channels(
        self, user_id: str, team_id: str | None
    ) -> list[dict]:
        """Return all DM (type D) and group DM (type G) channels,
        sorted by last activity."""
        channels = [
            ch
            for ch in self._fetch_member_channels(user_id, team_id)
            if ch.get("type") in ("D", "G")
        ]
        return sorted(
            channels, key=lambda ch: ch.get("last_post_at", 0), reverse=True
        )

    def get_all_channels(self, user_id: str, team_id: str | None) -> list[dict]:
        """Return all subscribed open (O) and private (P) channels,
        sorted by last activity."""
        channels = [
            ch
            for ch in self._fetch_member_channels(user_id, team_id)
            if ch.get("type") in ("O", "P")
        ]
        return sorted(
            channels, key=lambda ch: ch.get("last_post_at", 0), reverse=True
        )

    def dm_display_name(self, channel: dict, current_user_id: str) -> str:
        """Human-readable name for a DM or group-DM channel."""
        if channel.get("type") == "D":
            parts = channel["name"].split("__")
            other_id = next(
                (p for p in parts if p != current_user_id), parts[0]
            )
            return f"DM with {self.get_username(other_id)}"
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
        after_ts: int,  # Unix ms, inclusive
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
            order = data.get("order", [])
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

            if oldest_ts_in_batch is not None and oldest_ts_in_batch < after_ts:
                break

            if len(order) < per_page:
                break

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
    dt = ts_to_datetime(post["create_at"])
    message = post.get("message", "").strip()

    message = "\n".join(line for line in message.splitlines() if line.strip())

    if not message:
        return ""

    prefix = f"{indent}**{username}** [{format_time(dt)}]"

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
    channel_name = channel.get("name", "unknown")
    channel_display = (
        display_name or channel.get("display_name") or f"#{channel_name}"
    )
    server_url = client.server_url

    lines: list[str] = []
    exported_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    is_dm = channel.get("type") in ("D", "G")
    channel_type = "Direct Message" if is_dm else "Channel"
    title = f"Mattermost {channel_type}: {channel_display}"

    lines += [
        f"# {title}",
        "",
        f"**Display name:** {channel_display}  ",
        f"**Server:** {server_url}  ",
        f"**Period:** {date_from} to {date_to}  ",
        f"**Exported:** {exported_at}  ",
        "",
        "---",
        "",
    ]

    if not posts:
        lines.append("*No messages in this period.*")
        return "\n".join(lines)

    posts_by_day: dict[date, list[dict]] = defaultdict(list)
    for post in posts:
        day = ts_to_datetime(post["create_at"]).date()
        posts_by_day[day].append(post)

    for day in sorted(posts_by_day):
        lines.append(f"## {format_day_header(day)}")
        lines.append("")

        day_posts = posts_by_day[day]

        top_level: list[dict] = []
        replies: dict[str, list[dict]] = defaultdict(list)

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

            for reply in replies.get(post["id"], []):
                rendered_reply = render_post(reply, client, indent="  ↳ ")
                if rendered_reply:
                    lines.append(rendered_reply)

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AI summarization
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = CONFIG_DIR / "config.yaml"


def ensure_prompt_file() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not PROMPT_FILE.exists():
        PROMPT_FILE.write_text(DEFAULT_PROMPT, encoding="utf-8")
        log.info(
            "Created default prompt at %s"
            " — edit it to personalise your summaries.",
            PROMPT_FILE,
        )
    return PROMPT_FILE.read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_config(path: Path) -> dict:
    if not path.exists():
        log.error("Error: Config file not found: %s", path)
        log.error(
            "Copy examples/config.example.yaml to %s and fill in your details.",
            DEFAULT_CONFIG,
        )
        sys.exit(1)
    with path.open() as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mattermost-tldr",
        description=(
            "Export Mattermost messages to markdown and summarize with AI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Date range (CLI flags override config file):
  --today         Export today's messages
  --yesterday     Export yesterday's messages
  --this-week     Export from Monday of the current week to today
  --last-week     Export last Monday–Sunday
  --days N        Export the last N days (including today)
  --hours H       Export the last H hours (sub-day precision)

Channel selection:
  --all-channels  Export all channels you are subscribed to
                  (ignores channels list in config)
                  (also enabled by setting  all_channels: true  in config)
  --direct        Also export direct/group messages
                  (also enabled by setting  direct_messages: true  in config)

AI summarization:
  --digest-only   Generate digest only, skip AI summarization
  --digest FILE   Use an existing digest file, skip generation
  --backend B     AI backend: copilot (default) or claude

If no date flag is given, date_from / date_to from the config file are used.
        """,
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        metavar="FILE",
        help=f"Path to YAML config file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--all-channels",
        action="store_true",
        help="Export all subscribed channels (ignores channels list in config)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Also export direct/group messages",
    )
    parser.add_argument(
        "--digest-only",
        action="store_true",
        help="Generate digest only, skip AI summarization",
    )
    parser.add_argument(
        "--digest",
        metavar="FILE",
        help="Path to an existing digest file (skips digest generation)",
    )
    parser.add_argument(
        "--backend",
        choices=list(BACKENDS),
        default="copilot",
        metavar="BACKEND",
        help="AI backend: copilot (default) or claude",
    )

    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--today", action="store_true", help="Export today")
    date_group.add_argument(
        "--yesterday", action="store_true", help="Export yesterday"
    )
    date_group.add_argument(
        "--this-week", action="store_true", help="Export Mon–today"
    )
    date_group.add_argument(
        "--last-week", action="store_true", help="Export last Mon–Sun"
    )
    date_group.add_argument(
        "--days", type=int, metavar="N", help="Export last N days"
    )
    date_group.add_argument(
        "--hours", type=int, metavar="H", help="Export last H hours"
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_arg_parser()
    args = parser.parse_args()

    # --digest FILE: skip generation, go straight to summarization
    if args.digest:
        digest_path = Path(args.digest)
        if not digest_path.exists():
            log.error("Error: digest file not found: %s", digest_path)
            sys.exit(1)
        if args.digest_only:
            log.info(
                "Note: --digest-only has no effect when --digest FILE is given."
            )
        run_ai_summary(digest_path, args.backend)
        log.info("Done.")
        return

    # --- Digest generation ---
    config = load_config(Path(args.config))

    server_url = config.get("server_url", "").rstrip("/")
    token = os.environ.get("MATTERMOST_TOKEN") or config.get("token", "")
    team_name = config.get("team", "")
    channels = config.get("channels", [])
    output_dir = Path(config.get("output_dir", "./exports"))

    if not server_url:
        log.error("Error: server_url is required in config.")
        sys.exit(1)
    if not token or token == "your_personal_access_token_here":
        log.error(
            "Error: Set your token in config.yaml"
            " or via MATTERMOST_TOKEN env var."
        )
        sys.exit(1)

    use_all = args.all_channels or config.get("all_channels", False)
    use_direct = args.direct or config.get("direct_messages", False)

    if not use_all and not use_direct and not channels:
        log.error(
            "Error: No channels specified in config and neither"
            " all_channels nor direct_messages is enabled."
            " Add channels to config, or use --all-channels"
            " and/or --direct."
        )
        sys.exit(1)

    if args.hours is not None:
        now_dt = datetime.now(tz=timezone.utc)
        start_dt = now_dt - timedelta(hours=args.hours)
        after_ts = int(start_dt.timestamp() * 1000)
        before_ts = int(now_dt.timestamp() * 1000)
        date_from = start_dt.date()
        date_to = now_dt.date()
        period_label = f"last_{args.hours}h"
        since = start_dt.strftime("%Y-%m-%d %H:%M UTC")
        log.info("Period  : last %s hour(s) (since %s)", args.hours, since)
    else:
        date_from, date_to = date_range_from_args(args, config)

        if date_to < date_from:
            log.error(
                "Error: date_to (%s) is before date_from (%s).",
                date_to,
                date_from,
            )
            sys.exit(1)

        after_ts = int(
            datetime(
                date_from.year,
                date_from.month,
                date_from.day,
                tzinfo=timezone.utc,
            ).timestamp()
            * 1000
        )
        before_ts = int(
            datetime(
                date_to.year,
                date_to.month,
                date_to.day,
                23,
                59,
                59,
                tzinfo=timezone.utc,
            ).timestamp()
            * 1000
        )
        period_label = (
            f"{date_from}_to_{date_to}"
            if date_from != date_to
            else str(date_from)
        )
        log.info("Period  : %s → %s", date_from, date_to)

    log.info("Server  : %s", server_url)

    client = MattermostClient(server_url, token)

    try:
        me = client.get_me()
        log.info("Logged in as: %s", me["username"])
    except requests.HTTPError as e:
        log.error("Authentication failed: %s", e)
        sys.exit(1)

    try:
        team = client.find_team(team_name) if team_name else None
        team_id = team["id"] if team else None
        if team:
            log.info("Team    : %s (%s)", team["display_name"], team["name"])
    except (ValueError, requests.HTTPError) as e:
        log.error("Error resolving team: %s", e)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    export_targets: list[tuple[dict, str, str]] = []

    if use_all:
        log.info("Fetching all subscribed channels ...")
        all_chans = client.get_all_channels(me["id"], team_id)
        in_range = sum(
            1 for ch in all_chans if ch.get("last_post_at", 0) >= after_ts
        )
        log.info("%d found, %d active in period.", len(all_chans), in_range)
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
                    channel = client._get(
                        "/channels/search",
                        params={"term": channel_name},
                    )
                except requests.HTTPError:
                    # Channel search is best-effort; failure is handled
                    # below by the `channel is None` check.
                    pass
            if channel is None:
                log.info("  #%s ... not found, skipping.", channel_name)
                continue
            label = channel.get("display_name") or f"#{channel_name}"
            export_targets.append((channel, label, channel_name))

    if use_direct:
        log.info("Fetching direct message channels ...")
        dm_channels = client.get_direct_channels(me["id"], team_id)
        if not dm_channels:
            log.info("none found.")
        else:
            in_range = sum(
                1 for ch in dm_channels if ch.get("last_post_at", 0) >= after_ts
            )
            log.info(
                "%d found, %d active in period.", len(dm_channels), in_range
            )
            log.info("Resolving channel names ...")
            for ch in dm_channels:
                if ch.get("last_post_at", 0) < after_ts:
                    break
                label = client.dm_display_name(ch, me["id"])
                safe = (
                    label.replace("DM with ", "dm_")
                    .replace(" ", "_")
                    .replace("/", "_")
                )
                export_targets.append((ch, label, safe))

    all_markdowns: list[str] = []

    for channel, display_name, _filename_stem in export_targets:
        log.info("  %s ...", display_name)

        try:
            posts = client.get_posts_in_range(
                channel["id"], after_ts, before_ts
            )
        except requests.HTTPError as e:
            log.error("error fetching posts: %s", e)
            continue

        log.info("  %d messages", len(posts))

        if not posts:
            continue

        markdown = render_channel_markdown(
            channel,
            posts,
            client,
            date_from,
            date_to,
            display_name=display_name,
        )
        all_markdowns.append(markdown)

    digest_path: Path | None = None
    if all_markdowns:
        filename = f"digest_{period_label}.md"
        digest_path = output_dir / filename
        digest_path.write_text(
            "\n\n---\n\n".join(all_markdowns), encoding="utf-8"
        )
        log.info("→ Written to %s", digest_path)
    else:
        log.info("No messages found for the given period.")

    if not args.digest_only and digest_path is not None:
        run_ai_summary(digest_path, args.backend)

    log.info("Done.")
