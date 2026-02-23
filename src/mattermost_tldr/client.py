"""Mattermost HTTP API client."""

import logging
from typing import Any, cast

import requests

log = logging.getLogger(__name__)

__all__ = ["MattermostClient"]


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
