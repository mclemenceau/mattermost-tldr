"""Markdown renderer for Mattermost post exports (LLM-optimised)."""

import logging
from collections import defaultdict
from datetime import date, datetime, timezone

from .client import MattermostClient

log = logging.getLogger(__name__)

__all__ = [
    "ts_to_datetime",
    "format_time",
    "format_day_header",
    "render_post",
    "render_channel_markdown",
]


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
