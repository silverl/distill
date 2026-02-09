"""Tests for src/retrieval.py — similarity search at synthesis time."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from distill.retrieval import (
    _build_query_text,
    _format_related_context,
    get_related_context,
    get_related_context_for_topic,
)


@pytest.fixture
def mock_item():
    """Create a mock ContentItem."""
    item = MagicMock()
    item.id = "item-1"
    item.title = "Test Article"
    item.excerpt = "This is a test article about AI agents"
    item.body = "Full body text"
    item.url = "https://example.com/test"
    item.published_at = datetime(2026, 1, 15)
    item.tags = ["ai", "agents"]
    return item


@pytest.fixture
def mock_store():
    """Create a mock content store."""
    store = MagicMock()
    return store


class TestBuildQueryText:
    def test_builds_from_titles(self, mock_item):
        text = _build_query_text([mock_item])
        assert "Test Article" in text

    def test_includes_excerpts(self, mock_item):
        text = _build_query_text([mock_item])
        assert "AI agents" in text

    def test_empty_items(self):
        text = _build_query_text([])
        assert text == ""

    def test_truncates_long_text(self):
        items = []
        for i in range(20):
            item = MagicMock()
            item.title = f"Title {i} " + "x" * 100
            item.excerpt = "y" * 200
            items.append(item)
        text = _build_query_text(items)
        assert len(text) <= 1000


class TestFormatRelatedContext:
    def test_formats_items(self, mock_item):
        text = _format_related_context([mock_item])
        assert "## Related Past Content" in text
        assert "Test Article" in text
        assert "2026-01-15" in text

    def test_empty_items(self):
        text = _format_related_context([])
        assert "## Related Past Content" in text

    def test_item_without_date(self):
        item = MagicMock()
        item.title = "Undated"
        item.published_at = None
        item.excerpt = "excerpt"
        item.body = ""
        text = _format_related_context([item])
        assert "Undated" in text

    def test_item_with_body_fallback(self):
        item = MagicMock()
        item.title = "Body Only"
        item.published_at = None
        item.excerpt = ""
        item.body = "This is the body content"
        text = _format_related_context([item])
        assert "body content" in text


class TestGetRelatedContext:
    @patch("distill.retrieval._embeddings_available", return_value=False)
    def test_returns_empty_when_embeddings_unavailable(self, mock_avail, mock_item, mock_store):
        result = get_related_context([mock_item], mock_store)
        assert result == ""

    @patch("distill.retrieval._embeddings_available", return_value=True)
    def test_returns_empty_with_no_items_and_no_query(self, mock_avail, mock_store):
        result = get_related_context([], mock_store)
        assert result == ""

    @patch("distill.retrieval._embeddings_available", return_value=True)
    @patch("distill.retrieval._embed_text", return_value=[0.1] * 384)
    def test_returns_formatted_results(self, mock_embed, mock_avail, mock_item, mock_store):
        similar_item = MagicMock()
        similar_item.title = "Related Article"
        similar_item.published_at = datetime(2026, 1, 10)
        similar_item.excerpt = "Related content"
        similar_item.body = ""
        mock_store.find_similar.return_value = [similar_item]

        result = get_related_context([mock_item], mock_store, k=3)
        assert "Related Article" in result
        assert "## Related Past Content" in result
        mock_store.find_similar.assert_called_once()

    @patch("distill.retrieval._embeddings_available", return_value=True)
    @patch("distill.retrieval._embed_text", side_effect=RuntimeError("model not loaded"))
    def test_handles_embed_error(self, mock_embed, mock_avail, mock_item, mock_store):
        result = get_related_context([mock_item], mock_store)
        assert result == ""

    @patch("distill.retrieval._embeddings_available", return_value=True)
    @patch("distill.retrieval._embed_text", return_value=[0.1] * 384)
    def test_excludes_current_items(self, mock_embed, mock_avail, mock_item, mock_store):
        mock_store.find_similar.return_value = []
        get_related_context([mock_item], mock_store)
        call_kwargs = mock_store.find_similar.call_args
        assert mock_item.id in call_kwargs.kwargs.get("exclude_ids", [])

    @patch("distill.retrieval._embeddings_available", return_value=True)
    @patch("distill.retrieval._embed_text", return_value=[0.1] * 384)
    def test_custom_query_text(self, mock_embed, mock_avail, mock_store):
        mock_store.find_similar.return_value = []
        get_related_context([], mock_store, query_text="custom topic")
        mock_embed.assert_called_once_with("custom topic")


class TestGetRelatedContextForTopic:
    @patch("distill.retrieval.get_related_context", return_value="mocked")
    def test_delegates_with_query_text(self, mock_get, mock_store):
        result = get_related_context_for_topic("AI agents", mock_store, k=3)
        assert result == "mocked"
