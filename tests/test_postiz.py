"""Tests for Postiz client and mapping."""

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest
from distill.integrations.mapping import resolve_integration_ids
from distill.integrations.postiz import (
    PostizAPIError,
    PostizClient,
    PostizConfig,
    PostizIntegration,
)


class TestPostizConfig:
    def test_defaults(self):
        cfg = PostizConfig()
        assert cfg.url == ""
        assert cfg.api_key == ""
        assert cfg.default_type == "draft"
        assert cfg.is_configured is False

    def test_configured(self):
        cfg = PostizConfig(url="https://postiz.example", api_key="key123")
        assert cfg.is_configured is True

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("POSTIZ_URL", "https://postiz.test")
        monkeypatch.setenv("POSTIZ_API_KEY", "testkey")
        monkeypatch.setenv("POSTIZ_DEFAULT_TYPE", "now")
        cfg = PostizConfig.from_env()
        assert cfg.url == "https://postiz.test"
        assert cfg.api_key == "testkey"
        assert cfg.default_type == "now"

    def test_from_env_defaults(self, monkeypatch):
        monkeypatch.delenv("POSTIZ_URL", raising=False)
        monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
        monkeypatch.delenv("POSTIZ_DEFAULT_TYPE", raising=False)
        monkeypatch.delenv("POSTIZ_SCHEDULE_ENABLED", raising=False)
        monkeypatch.delenv("POSTIZ_TIMEZONE", raising=False)
        monkeypatch.delenv("POSTIZ_WEEKLY_TIME", raising=False)
        monkeypatch.delenv("POSTIZ_WEEKLY_DAY", raising=False)
        monkeypatch.delenv("POSTIZ_THEMATIC_TIME", raising=False)
        monkeypatch.delenv("POSTIZ_THEMATIC_DAYS", raising=False)
        monkeypatch.delenv("POSTIZ_INTAKE_TIME", raising=False)
        cfg = PostizConfig.from_env()
        assert cfg.url == ""
        assert cfg.default_type == "draft"
        assert cfg.schedule_enabled is False
        assert cfg.timezone == "America/New_York"

    def test_schedule_fields(self):
        cfg = PostizConfig(
            url="https://postiz.test",
            api_key="key",
            schedule_enabled=True,
            timezone="US/Pacific",
            weekly_day=2,
            thematic_days=[0, 4],
        )
        assert cfg.schedule_enabled is True
        assert cfg.timezone == "US/Pacific"
        assert cfg.weekly_day == 2
        assert cfg.thematic_days == [0, 4]

    def test_resolve_post_type_draft(self):
        cfg = PostizConfig(default_type="draft", schedule_enabled=False)
        assert cfg.resolve_post_type() == "draft"

    def test_resolve_post_type_schedule(self):
        cfg = PostizConfig(default_type="draft", schedule_enabled=True)
        assert cfg.resolve_post_type() == "schedule"

    def test_resolve_post_type_now(self):
        cfg = PostizConfig(default_type="now", schedule_enabled=False)
        assert cfg.resolve_post_type() == "now"

    def test_from_env_schedule_enabled(self, monkeypatch):
        monkeypatch.setenv("POSTIZ_URL", "https://postiz.test")
        monkeypatch.setenv("POSTIZ_API_KEY", "key")
        monkeypatch.setenv("POSTIZ_SCHEDULE_ENABLED", "true")
        monkeypatch.setenv("POSTIZ_TIMEZONE", "US/Pacific")
        monkeypatch.setenv("POSTIZ_WEEKLY_DAY", "3")
        monkeypatch.setenv("POSTIZ_THEMATIC_DAYS", "0,4")
        monkeypatch.setenv("POSTIZ_INTAKE_TIME", "20:00")
        cfg = PostizConfig.from_env()
        assert cfg.schedule_enabled is True
        assert cfg.timezone == "US/Pacific"
        assert cfg.weekly_day == 3
        assert cfg.thematic_days == [0, 4]
        assert cfg.intake_time == "20:00"


class TestPostizClient:
    def test_raises_if_not_configured(self):
        with pytest.raises(ValueError, match="not configured"):
            PostizClient(PostizConfig())

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_list_integrations(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([
            {"id": "int-1", "name": "My Twitter", "providerIdentifier": "x"},
            {"id": "int-2", "name": "My LinkedIn", "providerIdentifier": "linkedin"},
        ]).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        config = PostizConfig(url="https://postiz.test/public/v1", api_key="key")
        client = PostizClient(config)
        integrations = client.list_integrations()

        assert len(integrations) == 2
        assert integrations[0].id == "int-1"
        assert integrations[0].provider == "x"
        assert integrations[1].provider == "linkedin"

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_list_integrations_dict_format(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "integrations": [
                {"id": "int-1", "name": "Twitter", "provider": "x"},
            ]
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        config = PostizConfig(url="https://postiz.test", api_key="key")
        client = PostizClient(config)
        integrations = client.list_integrations()
        assert len(integrations) == 1

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_create_post_draft(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "post-1"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        config = PostizConfig(url="https://postiz.test", api_key="key")
        client = PostizClient(config)
        result = client.create_post("Hello world", ["int-1", "int-2"])

        assert result == {"id": "post-1"}
        # Verify the request
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        assert body["type"] == "draft"
        assert len(body["posts"]) == 2
        assert body["posts"][0]["value"][0]["content"] == "Hello world"

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_create_post_scheduled(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        config = PostizConfig(url="https://postiz.test", api_key="key")
        client = PostizClient(config)
        client.create_post(
            "Scheduled post",
            ["int-1"],
            post_type="schedule",
            scheduled_at="2026-02-10T09:00:00Z",
        )

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        assert body["type"] == "schedule"
        assert body["date"] == "2026-02-10T09:00:00Z"

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_auth_header(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        config = PostizConfig(url="https://postiz.test", api_key="mykey123")
        client = PostizClient(config)
        client._request("GET", "/test")

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "mykey123"

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_http_error_raises(self, mock_urlopen):
        error = HTTPError("https://postiz.test/posts", 429, "Too Many Requests", {}, None)
        mock_urlopen.side_effect = error

        config = PostizConfig(url="https://postiz.test", api_key="key")
        client = PostizClient(config)

        with pytest.raises(PostizAPIError) as exc_info:
            client.create_post("test", ["int-1"])
        assert exc_info.value.status == 429

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_connection_error_raises(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("connection refused")

        config = PostizConfig(url="https://postiz.test", api_key="key")
        client = PostizClient(config)

        with pytest.raises(PostizAPIError) as exc_info:
            client._request("GET", "/test")
        assert exc_info.value.status == 0

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_url_construction(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"[]"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        # URL with trailing slash
        config = PostizConfig(url="https://postiz.test/public/v1/", api_key="key")
        client = PostizClient(config)
        client.list_integrations()

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://postiz.test/public/v1/integrations"

    @patch("distill.integrations.postiz.urllib.request.urlopen")
    def test_empty_response(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        config = PostizConfig(url="https://postiz.test", api_key="key")
        client = PostizClient(config)
        result = client._request("POST", "/posts", body={"type": "draft", "posts": []})
        assert result == {}


class TestPostizAPIError:
    def test_error_attributes(self):
        err = PostizAPIError(status=429, message="Rate limited", body='{"error":"too fast"}')
        assert err.status == 429
        assert err.body == '{"error":"too fast"}'
        assert "Rate limited" in str(err)


class TestResolveIntegrationIds:
    def test_maps_twitter(self):
        client = MagicMock()
        client.list_integrations.return_value = [
            PostizIntegration(id="int-1", name="Twitter", provider="x"),
        ]
        result = resolve_integration_ids(client, ["twitter"])
        assert result == {"twitter": ["int-1"]}

    def test_maps_linkedin(self):
        client = MagicMock()
        client.list_integrations.return_value = [
            PostizIntegration(id="int-2", name="LinkedIn", provider="linkedin"),
        ]
        result = resolve_integration_ids(client, ["linkedin"])
        assert result == {"linkedin": ["int-2"]}

    def test_multiple_platforms(self):
        client = MagicMock()
        client.list_integrations.return_value = [
            PostizIntegration(id="int-1", name="Twitter", provider="x"),
            PostizIntegration(id="int-2", name="LinkedIn", provider="linkedin"),
            PostizIntegration(id="int-3", name="Reddit", provider="reddit"),
        ]
        result = resolve_integration_ids(client, ["twitter", "linkedin", "reddit"])
        assert "twitter" in result
        assert "linkedin" in result
        assert "reddit" in result

    def test_omits_missing_platforms(self):
        client = MagicMock()
        client.list_integrations.return_value = [
            PostizIntegration(id="int-1", name="Twitter", provider="x"),
        ]
        result = resolve_integration_ids(client, ["twitter", "mastodon"])
        assert "twitter" in result
        assert "mastodon" not in result

    def test_multiple_accounts_same_platform(self):
        client = MagicMock()
        client.list_integrations.return_value = [
            PostizIntegration(id="int-1", name="Personal", provider="x"),
            PostizIntegration(id="int-2", name="Business", provider="x"),
        ]
        result = resolve_integration_ids(client, ["twitter"])
        assert len(result["twitter"]) == 2

    def test_empty_integrations(self):
        client = MagicMock()
        client.list_integrations.return_value = []
        result = resolve_integration_ids(client, ["twitter"])
        assert result == {}

    def test_case_insensitive_provider(self):
        client = MagicMock()
        client.list_integrations.return_value = [
            PostizIntegration(id="int-1", name="My X", provider="X"),
        ]
        result = resolve_integration_ids(client, ["twitter"])
        assert "twitter" in result

    def test_linkedin_page_variant(self):
        client = MagicMock()
        client.list_integrations.return_value = [
            PostizIntegration(id="int-1", name="Page", provider="linkedin-page"),
        ]
        result = resolve_integration_ids(client, ["linkedin"])
        assert "linkedin" in result
