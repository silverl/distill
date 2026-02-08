"""Tests for Ghost CMS intake publisher."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from distill.blog.config import GhostConfig
from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.ghost import GhostIntakePublisher


def _ctx(**overrides) -> DailyIntakeContext:
    defaults = dict(
        date=date(2026, 2, 7),
        total_items=5,
        total_word_count=1500,
        sources=["rss"],
        sites=["Blog A", "Blog B"],
        all_tags=["python", "ai", "llm", "tools", "rag"],
        combined_text="Combined text here.",
    )
    defaults.update(overrides)
    return DailyIntakeContext(**defaults)


def _configured_ghost() -> GhostConfig:
    return GhostConfig(
        url="https://ghost.example.com",
        admin_api_key="abc123:deadbeef",
        newsletter_slug="weekly-digest",
        auto_publish=True,
    )


def _unconfigured_ghost() -> GhostConfig:
    return GhostConfig(url="", admin_api_key="")


# ------------------------------------------------------------------
# Output path tests
# ------------------------------------------------------------------


class TestDailyOutputPath:
    def test_output_path_structure(self):
        pub = GhostIntakePublisher()
        path = pub.daily_output_path(Path("/out"), date(2026, 2, 7))
        assert path == Path("/out/intake/ghost/ghost-2026-02-07.md")

    def test_output_path_different_date(self):
        pub = GhostIntakePublisher()
        path = pub.daily_output_path(Path("/insights"), date(2025, 12, 31))
        assert path == Path("/insights/intake/ghost/ghost-2025-12-31.md")


# ------------------------------------------------------------------
# Ghost-meta comment generation
# ------------------------------------------------------------------


class TestFormatDailyMeta:
    def test_ghost_meta_comment_present(self):
        pub = GhostIntakePublisher()
        result = pub.format_daily(_ctx(), "Some prose.")
        assert "<!-- ghost-meta:" in result
        assert "-->" in result

    def test_ghost_meta_contains_title(self):
        pub = GhostIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        meta = _extract_meta(result)
        assert meta["title"] == "Daily Research Digest \u2014 February 7, 2026"

    def test_ghost_meta_contains_date(self):
        pub = GhostIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        meta = _extract_meta(result)
        assert meta["date"] == "2026-02-07"

    def test_ghost_meta_contains_tags(self):
        pub = GhostIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        meta = _extract_meta(result)
        assert meta["tags"] == ["python", "ai", "llm", "tools", "rag"]

    def test_ghost_meta_tags_limited_to_10(self):
        many_tags = [f"tag{i}" for i in range(20)]
        pub = GhostIntakePublisher()
        result = pub.format_daily(_ctx(all_tags=many_tags), "Prose.")
        meta = _extract_meta(result)
        assert len(meta["tags"]) == 10

    def test_ghost_meta_status_is_draft(self):
        pub = GhostIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        meta = _extract_meta(result)
        assert meta["status"] == "draft"

    def test_prose_included_after_meta(self):
        pub = GhostIntakePublisher()
        result = pub.format_daily(_ctx(), "The actual digest content.")
        # Prose appears after the meta comment
        meta_end = result.index("-->")
        prose_start = result.index("The actual digest content.")
        assert prose_start > meta_end


# ------------------------------------------------------------------
# File-only mode
# ------------------------------------------------------------------


class TestFileOnlyMode:
    def test_none_config_produces_content(self):
        """When ghost_config is None, format_daily still returns content."""
        pub = GhostIntakePublisher(ghost_config=None)
        result = pub.format_daily(_ctx(), "Digest prose.")
        assert "<!-- ghost-meta:" in result
        assert "Digest prose." in result

    def test_unconfigured_config_produces_content(self):
        """When ghost_config is present but not configured, still returns content."""
        pub = GhostIntakePublisher(ghost_config=_unconfigured_ghost())
        result = pub.format_daily(_ctx(), "Digest prose.")
        assert "<!-- ghost-meta:" in result
        assert "Digest prose." in result

    def test_none_config_no_api_client(self):
        pub = GhostIntakePublisher(ghost_config=None)
        assert pub._api is None

    def test_unconfigured_config_no_api_client(self):
        pub = GhostIntakePublisher(ghost_config=_unconfigured_ghost())
        assert pub._api is None


# ------------------------------------------------------------------
# API publishing (mocked)
# ------------------------------------------------------------------


class TestAPIPublishing:
    @patch("distill.intake.publishers.ghost.GhostIntakePublisher._publish_to_api")
    def test_publish_called_when_configured(self, mock_publish):
        """When configured, _publish_to_api is called during format_daily."""
        pub = GhostIntakePublisher.__new__(GhostIntakePublisher)
        pub._config = _configured_ghost()
        pub._api = MagicMock()
        mock_publish.return_value = {"id": "post-1"}

        pub.format_daily(_ctx(), "Prose.")
        mock_publish.assert_called_once()

    @patch("distill.blog.publishers.ghost.GhostAPIClient")
    def test_api_create_post_called(self, MockClient):
        """API client's create_post is invoked with correct arguments."""
        mock_client = MagicMock()
        mock_client.create_post.return_value = {"id": "abc"}
        mock_client.publish_with_newsletter.return_value = {"id": "abc", "status": "published"}
        MockClient.return_value = mock_client

        config = _configured_ghost()
        pub = GhostIntakePublisher(ghost_config=config)
        pub._api = mock_client

        pub.format_daily(_ctx(), "Prose content.")

        mock_client.create_post.assert_called_once()
        call_args = mock_client.create_post.call_args
        assert "Daily Research Digest" in call_args[0][0] or "Daily Research Digest" in str(call_args)

    @patch("distill.blog.publishers.ghost.GhostAPIClient")
    def test_newsletter_publish_flow(self, MockClient):
        """With newsletter_slug, uses the two-step draft -> publish flow."""
        mock_client = MagicMock()
        mock_client.create_post.return_value = {"id": "post-99"}
        mock_client.publish_with_newsletter.return_value = {"id": "post-99", "status": "published"}
        MockClient.return_value = mock_client

        config = _configured_ghost()
        pub = GhostIntakePublisher(ghost_config=config)
        pub._api = mock_client

        pub.format_daily(_ctx(), "Content.")

        mock_client.create_post.assert_called_once()
        mock_client.publish_with_newsletter.assert_called_once_with("post-99", "weekly-digest")

    @patch("distill.blog.publishers.ghost.GhostAPIClient")
    def test_auto_publish_without_newsletter(self, MockClient):
        """Without newsletter_slug, creates post directly with configured status."""
        mock_client = MagicMock()
        mock_client.create_post.return_value = {"id": "post-1"}
        MockClient.return_value = mock_client

        config = GhostConfig(
            url="https://ghost.example.com",
            admin_api_key="abc123:deadbeef",
            newsletter_slug="",
            auto_publish=True,
        )
        pub = GhostIntakePublisher(ghost_config=config)
        pub._api = mock_client

        pub.format_daily(_ctx(), "Content.")

        mock_client.create_post.assert_called_once()
        call_kwargs = mock_client.create_post.call_args
        # status should be "published" since auto_publish=True
        assert call_kwargs[1]["status"] == "published" or call_kwargs[0][3] == "published"


# ------------------------------------------------------------------
# Graceful API error handling
# ------------------------------------------------------------------


class TestAPIErrorHandling:
    @patch("distill.blog.publishers.ghost.GhostAPIClient")
    def test_api_error_caught_gracefully(self, MockClient):
        """API exceptions are caught and logged; content is still returned."""
        mock_client = MagicMock()
        mock_client.create_post.side_effect = ConnectionError("Ghost unreachable")
        MockClient.return_value = mock_client

        config = _configured_ghost()
        pub = GhostIntakePublisher(ghost_config=config)
        pub._api = mock_client

        # Should NOT raise
        result = pub.format_daily(_ctx(), "My digest.")
        assert "<!-- ghost-meta:" in result
        assert "My digest." in result

    @patch("distill.blog.publishers.ghost.GhostAPIClient")
    def test_api_error_returns_none(self, MockClient):
        """_publish_to_api returns None on error."""
        mock_client = MagicMock()
        mock_client.create_post.side_effect = RuntimeError("boom")
        MockClient.return_value = mock_client

        config = _configured_ghost()
        pub = GhostIntakePublisher(ghost_config=config)
        pub._api = mock_client

        content = pub.format_daily(_ctx(), "Prose.")
        # Manually call _publish_to_api to verify return
        api_result = pub._publish_to_api(content)
        assert api_result is None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_meta(content: str) -> dict:
    """Extract the ghost-meta JSON from formatted content."""
    meta_str = content.split("<!-- ghost-meta:")[1].split("-->")[0].strip()
    return json.loads(meta_str)
