"""mattermost-tldr — Export Mattermost messages and summarize with AI."""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .client import MattermostClient
from .config import DEFAULT_CONFIG, load_config
from .render import render_channel_markdown
from .summary import BACKENDS, run_ai_summary

log = logging.getLogger(__name__)


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
# Phase helpers (private)
# ---------------------------------------------------------------------------


@dataclass
class _TimeWindow:
    after_ts: int
    before_ts: int
    date_from: date
    date_to: date
    period_label: str


def _handle_existing_digest(args: argparse.Namespace) -> None:
    """Validate digest file and run AI summary; calls sys.exit on error."""
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


def _validate_credentials(config: dict) -> tuple[str, str]:
    """Validate server_url and token; return (server_url, token) or exit."""
    server_url = config.get("server_url", "").rstrip("/")
    token = os.environ.get("MATTERMOST_TOKEN") or config.get("token", "")

    if not server_url:
        log.error("Error: server_url is required in config.")
        sys.exit(1)
    if not token or token == "your_personal_access_token_here":
        log.error(
            "Error: Set your token in config.yaml"
            " or via MATTERMOST_TOKEN env var."
        )
        sys.exit(1)
    return server_url, str(token)


def _resolve_time_window(args: argparse.Namespace, config: dict) -> _TimeWindow:
    """Compute after_ts, before_ts, date range, and period label."""
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
        return _TimeWindow(
            after_ts, before_ts, date_from, date_to, period_label
        )

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
        f"{date_from}_to_{date_to}" if date_from != date_to else str(date_from)
    )
    log.info("Period  : %s → %s", date_from, date_to)
    return _TimeWindow(after_ts, before_ts, date_from, date_to, period_label)


def _authenticate(client: MattermostClient) -> dict[str, Any]:
    """Verify credentials; return the 'me' user dict or call sys.exit(1)."""
    try:
        me = client.get_me()
        log.info("Logged in as: %s", me["username"])
        return me
    except requests.HTTPError as e:
        log.error("Authentication failed: %s", e)
        sys.exit(1)


def _resolve_team(client: MattermostClient, team_name: str) -> str | None:
    """Resolve team_id by name; return None if unconfigured, or exit."""
    try:
        team = client.find_team(team_name) if team_name else None
        team_id: str | None = team["id"] if team else None
        if team:
            log.info("Team    : %s (%s)", team["display_name"], team["name"])
        return team_id
    except (ValueError, requests.HTTPError) as e:
        log.error("Error resolving team: %s", e)
        sys.exit(1)


def _collect_channel_targets(
    client: MattermostClient,
    me: dict[str, Any],
    team_id: str | None,
    channels: list,
    use_all: bool,
    use_direct: bool,
    after_ts: int,
) -> list[tuple[dict, str, str]]:
    """Resolve channels to export as (channel, label, stem) triples."""
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

    return export_targets


def _fetch_and_render_channels(
    client: MattermostClient,
    export_targets: list[tuple[dict, str, str]],
    after_ts: int,
    before_ts: int,
    date_from: date,
    date_to: date,
) -> list[str]:
    """Fetch posts and render markdown for each channel target."""
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

    return all_markdowns


def _write_digest(
    all_markdowns: list[str],
    output_dir: Path,
    period_label: str,
) -> Path | None:
    """Write markdowns to a single digest file; return path or None."""
    if not all_markdowns:
        log.info("No messages found for the given period.")
        return None
    filename = f"digest_{period_label}.md"
    digest_path = output_dir / filename
    digest_path.write_text("\n\n---\n\n".join(all_markdowns), encoding="utf-8")
    log.info("→ Written to %s", digest_path)
    return digest_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_arg_parser().parse_args()

    if args.digest:
        _handle_existing_digest(args)
        return

    config = load_config(Path(args.config))
    server_url, token = _validate_credentials(config)

    use_all: bool = args.all_channels or bool(config.get("all_channels", False))
    use_direct: bool = args.direct or bool(config.get("direct_messages", False))
    channels: list = config.get("channels", [])

    if not use_all and not use_direct and not channels:
        log.error(
            "Error: No channels specified in config and neither"
            " all_channels nor direct_messages is enabled."
            " Add channels to config, or use --all-channels"
            " and/or --direct."
        )
        sys.exit(1)

    window = _resolve_time_window(args, config)
    log.info("Server  : %s", server_url)

    client = MattermostClient(server_url, token)
    me = _authenticate(client)
    team_id = _resolve_team(client, config.get("team", ""))

    output_dir = Path(config.get("output_dir", "./exports"))
    output_dir.mkdir(parents=True, exist_ok=True)

    export_targets = _collect_channel_targets(
        client, me, team_id, channels, use_all, use_direct, window.after_ts
    )
    all_markdowns = _fetch_and_render_channels(
        client,
        export_targets,
        window.after_ts,
        window.before_ts,
        window.date_from,
        window.date_to,
    )
    digest_path = _write_digest(all_markdowns, output_dir, window.period_label)

    if not args.digest_only and digest_path is not None:
        run_ai_summary(digest_path, args.backend)

    log.info("Done.")
