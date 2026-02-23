"""Tests for MattermostClient."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from mattermost_tldr.client import MattermostClient


def make_response(json_data, status_code=200):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def client():
    """MattermostClient with a mocked requests session."""
    with patch("requests.Session"):
        c = MattermostClient("https://mattermost.example.com", "token123")
    c.session = MagicMock()
    return c


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_strips_trailing_slash(self):
        with patch("requests.Session"):
            c = MattermostClient("https://example.com/", "tok")
        assert c.server_url == "https://example.com"
        assert c.base_url == "https://example.com/api/v4"

    def test_no_trailing_slash_unchanged(self):
        with patch("requests.Session"):
            c = MattermostClient("https://example.com", "tok")
        assert c.server_url == "https://example.com"

    def test_sets_auth_header(self):
        with patch("requests.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            MattermostClient("https://example.com", "mytoken")
        mock_session.headers.update.assert_called_once_with(
            {
                "Authorization": "Bearer mytoken",
                "Content-Type": "application/json",
            }
        )

    def test_user_cache_starts_empty(self):
        with patch("requests.Session"):
            c = MattermostClient("https://example.com", "tok")
        assert c._user_cache == {}


# ---------------------------------------------------------------------------
# get_username
# ---------------------------------------------------------------------------


class TestGetUsername:
    def test_fetches_username(self, client):
        client.session.get.return_value = make_response({"username": "alice"})
        assert client.get_username("u1") == "alice"

    def test_caches_result(self, client):
        client.session.get.return_value = make_response({"username": "alice"})
        client.get_username("u1")
        client.get_username("u1")
        assert client.session.get.call_count == 1

    def test_returns_user_id_on_http_error(self, client):
        client.session.get.return_value = make_response({}, status_code=404)
        assert client.get_username("unknown_id") == "unknown_id"

    def test_caches_fallback_id(self, client):
        client.session.get.return_value = make_response({}, status_code=404)
        client.get_username("bad_id")
        client.get_username("bad_id")
        assert client.session.get.call_count == 1


# ---------------------------------------------------------------------------
# find_team
# ---------------------------------------------------------------------------


class TestGetMe:
    def test_returns_user_dict(self, client):
        client.session.get.return_value = make_response(
            {"id": "u1", "username": "alice"}
        )
        result = client.get_me()
        assert result["username"] == "alice"


class TestFetchMemberChannelsNoTeam:
    def test_uses_first_team_when_no_team_id(self, client):
        """When team_id is None, fetches the team list and uses the
        first team's id."""
        teams = [{"id": "t1"}, {"id": "t2"}]
        channels = [{"id": "c1", "type": "O", "last_post_at": 100}]
        client.session.get.side_effect = [
            make_response(teams),  # /teams call
            make_response(channels),  # /users/{uid}/teams/{t1}/channels
        ]
        result = client.get_all_channels("user1", None)
        assert len(result) == 1

    def test_returns_empty_when_no_teams(self, client):
        """When team_id is None and no teams exist, returns empty list."""
        client.session.get.return_value = make_response([])
        result = client.get_all_channels("user1", None)
        assert result == []


class TestFindTeam:
    def test_finds_by_name(self, client):
        teams = [{"id": "t1", "name": "myteam", "display_name": "My Team"}]
        client.session.get.return_value = make_response(teams)
        result = client.find_team("myteam")
        assert result["id"] == "t1"

    def test_finds_by_display_name(self, client):
        teams = [{"id": "t1", "name": "myteam", "display_name": "My Team"}]
        client.session.get.return_value = make_response(teams)
        result = client.find_team("My Team")
        assert result["id"] == "t1"

    def test_raises_value_error_if_not_found(self, client):
        teams = [{"id": "t1", "name": "other", "display_name": "Other"}]
        client.session.get.return_value = make_response(teams)
        with pytest.raises(ValueError, match="not found"):
            client.find_team("missing")

    def test_error_message_lists_available_teams(self, client):
        teams = [{"id": "t1", "name": "alpha", "display_name": "Alpha"}]
        client.session.get.return_value = make_response(teams)
        with pytest.raises(ValueError, match="alpha"):
            client.find_team("missing")


# ---------------------------------------------------------------------------
# find_channel
# ---------------------------------------------------------------------------


class TestFindChannel:
    def test_returns_channel_if_found(self, client):
        channel = {"id": "c1", "name": "general"}
        client.session.get.return_value = make_response(channel)
        result = client.find_channel("team1", "general")
        assert result["id"] == "c1"

    def test_returns_none_on_404(self, client):
        client.session.get.return_value = make_response({}, status_code=404)
        result = client.find_channel("team1", "notexist")
        assert result is None

    def test_re_raises_non_404_errors(self, client):
        client.session.get.return_value = make_response({}, status_code=500)
        with pytest.raises(requests.HTTPError):
            client.find_channel("team1", "general")


# ---------------------------------------------------------------------------
# get_direct_channels
# ---------------------------------------------------------------------------


class TestGetDirectChannels:
    def test_filters_to_dm_and_group_only(self, client):
        channels = [
            {"id": "c1", "type": "D", "last_post_at": 100},
            {"id": "c2", "type": "G", "last_post_at": 200},
            {"id": "c3", "type": "O", "last_post_at": 300},
        ]
        client.session.get.return_value = make_response(channels)
        result = client.get_direct_channels("user1", "team1")
        ids = {ch["id"] for ch in result}
        assert ids == {"c1", "c2"}

    def test_sorted_by_last_post_at_descending(self, client):
        channels = [
            {"id": "c1", "type": "D", "last_post_at": 100},
            {"id": "c2", "type": "D", "last_post_at": 300},
            {"id": "c3", "type": "D", "last_post_at": 200},
        ]
        client.session.get.return_value = make_response(channels)
        result = client.get_direct_channels("user1", "team1")
        assert [ch["id"] for ch in result] == ["c2", "c3", "c1"]


# ---------------------------------------------------------------------------
# get_all_channels
# ---------------------------------------------------------------------------


class TestGetAllChannels:
    def test_filters_to_open_and_private(self, client):
        channels = [
            {"id": "c1", "type": "O", "last_post_at": 100},
            {"id": "c2", "type": "P", "last_post_at": 200},
            {"id": "c3", "type": "D", "last_post_at": 300},
        ]
        client.session.get.return_value = make_response(channels)
        result = client.get_all_channels("user1", "team1")
        ids = {ch["id"] for ch in result}
        assert ids == {"c1", "c2"}

    def test_sorted_by_last_post_at_descending(self, client):
        channels = [
            {"id": "c1", "type": "O", "last_post_at": 50},
            {"id": "c2", "type": "O", "last_post_at": 200},
        ]
        client.session.get.return_value = make_response(channels)
        result = client.get_all_channels("user1", "team1")
        assert result[0]["id"] == "c2"


# ---------------------------------------------------------------------------
# dm_display_name
# ---------------------------------------------------------------------------


class TestDmDisplayName:
    def test_dm_with_other_user(self, client):
        client.session.get.return_value = make_response({"username": "alice"})
        channel = {
            "type": "D",
            "name": "currentuser__alice_id",
            "display_name": "",
        }
        result = client.dm_display_name(channel, "currentuser")
        assert result == "DM with alice"

    def test_dm_picks_other_user_when_first(self, client):
        client.session.get.return_value = make_response({"username": "bob"})
        channel = {
            "type": "D",
            "name": "bob_id__currentuser",
            "display_name": "",
        }
        result = client.dm_display_name(channel, "currentuser")
        assert result == "DM with bob"

    def test_group_dm_with_display_name(self, client):
        channel = {"type": "G", "name": "group123", "display_name": "My Group"}
        result = client.dm_display_name(channel, "currentuser")
        assert result == "My Group"

    def test_group_dm_no_display_name(self, client):
        channel = {"type": "G", "name": "group123", "display_name": ""}
        result = client.dm_display_name(channel, "currentuser")
        assert result == "Group DM"


# ---------------------------------------------------------------------------
# get_posts_in_range
# ---------------------------------------------------------------------------


class TestGetPostsInRange:
    def test_empty_page_returns_empty_list(self, client):
        client.session.get.return_value = make_response(
            {"order": [], "posts": {}}
        )
        result = client.get_posts_in_range(
            "chan1", after_ts=0, before_ts=9_999_999_999_999
        )
        assert result == []

    def test_filters_posts_outside_range(self, client):
        posts_map = {
            "p1": {
                "id": "p1",
                "create_at": 500,
                "user_id": "u1",
                "message": "in range",
            },
            "p2": {
                "id": "p2",
                "create_at": 50,
                "user_id": "u1",
                "message": "too old",
            },
            "p3": {
                "id": "p3",
                "create_at": 900,
                "user_id": "u1",
                "message": "too new",
            },
        }
        client.session.get.return_value = make_response(
            {
                "order": ["p3", "p1", "p2"],
                "posts": posts_map,
            }
        )
        result = client.get_posts_in_range("chan1", after_ts=100, before_ts=800)
        assert len(result) == 1
        assert result[0]["id"] == "p1"

    def test_returns_posts_sorted_oldest_first(self, client):
        posts_map = {
            "p1": {
                "id": "p1",
                "create_at": 200,
                "user_id": "u1",
                "message": "second",
            },
            "p2": {
                "id": "p2",
                "create_at": 100,
                "user_id": "u1",
                "message": "first",
            },
        }
        client.session.get.return_value = make_response(
            {
                "order": ["p1", "p2"],
                "posts": posts_map,
            }
        )
        result = client.get_posts_in_range("chan1", after_ts=0, before_ts=999)
        assert result[0]["create_at"] == 100
        assert result[1]["create_at"] == 200

    def test_stops_when_batch_oldest_older_than_after_ts(self, client):
        """When the oldest post in a batch predates after_ts,
        stop paginating."""
        posts_map = {
            "p1": {
                "id": "p1",
                "create_at": 500,
                "user_id": "u1",
                "message": "in range",
            },
            "p2": {
                "id": "p2",
                "create_at": 10,
                "user_id": "u1",
                "message": "triggers stop",
            },
        }
        client.session.get.return_value = make_response(
            {
                "order": ["p1", "p2"],
                "posts": posts_map,
            }
        )
        result = client.get_posts_in_range(
            "chan1", after_ts=100, before_ts=1000
        )
        # p1 is in range; p2 is older than after_ts so it triggers
        # stop (and is excluded)
        assert len(result) == 1
        assert result[0]["id"] == "p1"
        # Only one API call because the stop condition fired
        assert client.session.get.call_count == 1

    def test_all_posts_in_range(self, client):
        posts_map = {
            "p1": {
                "id": "p1",
                "create_at": 100,
                "user_id": "u1",
                "message": "a",
            },
            "p2": {
                "id": "p2",
                "create_at": 200,
                "user_id": "u1",
                "message": "b",
            },
        }
        client.session.get.return_value = make_response(
            {
                "order": ["p2", "p1"],
                "posts": posts_map,
            }
        )
        result = client.get_posts_in_range("chan1", after_ts=0, before_ts=9999)
        assert len(result) == 2

    def test_paginates_to_second_page_when_first_is_full(self, client):
        """When first page is full (200 posts), a second request is
        made with before= cursor."""
        per_page = 200
        first_posts = {
            f"p{i}": {
                "id": f"p{i}",
                "create_at": 1000 + i,
                "user_id": "u1",
                "message": f"m{i}",
            }
            for i in range(per_page)
        }
        # order is newest-first; last entry ("p0") becomes the before= cursor
        first_order = [f"p{i}" for i in range(per_page - 1, -1, -1)]

        second_posts = {
            "p_extra": {
                "id": "p_extra",
                "create_at": 999,
                "user_id": "u1",
                "message": "extra",
            }
        }
        second_order = ["p_extra"]

        client.session.get.side_effect = [
            make_response({"order": first_order, "posts": first_posts}),
            make_response({"order": second_order, "posts": second_posts}),
        ]

        result = client.get_posts_in_range(
            "chan1", after_ts=0, before_ts=9_999_999
        )
        assert client.session.get.call_count == 2
        assert len(result) == per_page + 1

    def test_skips_missing_post_ids(self, client):
        """order may reference IDs not present in posts map —
        should skip gracefully."""
        posts_map = {
            "p1": {
                "id": "p1",
                "create_at": 100,
                "user_id": "u1",
                "message": "present",
            },
        }
        client.session.get.return_value = make_response(
            {
                "order": ["ghost_id", "p1"],
                "posts": posts_map,
            }
        )
        result = client.get_posts_in_range("chan1", after_ts=0, before_ts=9999)
        assert len(result) == 1
        assert result[0]["id"] == "p1"
