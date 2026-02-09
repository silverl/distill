"""Tests for embeddings module."""

from __future__ import annotations

import random
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from distill.embeddings import (
    DEFAULT_MODEL,
    EMBEDDING_DIM,
    _item_text,
    embed_items,
    embed_text,
    embed_texts,
    is_available,
)
from distill.intake.models import ContentItem, ContentSource, ContentType


class _FakeVector:
    """A fake numpy-like vector with .tolist() support."""

    def __init__(self, values: list[float]):
        self._values = values

    def tolist(self) -> list[float]:
        return self._values


class _FakeBatchVector:
    """A fake numpy-like batch result that iterates into _FakeVector rows."""

    def __init__(self, rows: list[list[float]]):
        self._rows = [_FakeVector(r) for r in rows]

    def __iter__(self):
        return iter(self._rows)


@pytest.fixture(autouse=True)
def _clear_model_cache():
    """Clear the module-level model cache between tests."""
    from distill.embeddings import _model_cache

    _model_cache.clear()
    yield
    _model_cache.clear()


def _rand_vec(dim: int = EMBEDDING_DIM, seed: int = 42) -> list[float]:
    rng = random.Random(seed)
    return [rng.random() for _ in range(dim)]


@pytest.fixture()
def mock_model():
    """Create a mock SentenceTransformer model."""
    model = MagicMock()
    model.encode.return_value = _FakeVector(_rand_vec())
    return model


@pytest.fixture()
def mock_model_batch():
    """Create a mock model that returns batch results."""
    model = MagicMock()

    def batch_encode(texts, convert_to_numpy=True):
        return _FakeBatchVector([_rand_vec(seed=i) for i in range(len(texts))])

    model.encode.side_effect = batch_encode
    return model


def _make_item(
    item_id: str = "item-1",
    title: str = "Test Article",
    body: str = "This is the article body.",
    excerpt: str = "",
    tags: list[str] | None = None,
) -> ContentItem:
    return ContentItem(
        id=item_id,
        title=title,
        body=body,
        excerpt=excerpt,
        source=ContentSource.RSS,
        content_type=ContentType.ARTICLE,
        tags=tags or [],
    )


class TestIsAvailable:
    def test_available_when_installed(self):
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True):
            assert is_available() is True

    def test_unavailable_when_not_installed(self):
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", False):
            assert is_available() is False


class TestEmbedText:
    def test_embed_text(self, mock_model):
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True), \
             patch("distill.embeddings.SentenceTransformer", return_value=mock_model):
            result = embed_text("Hello world")

        assert isinstance(result, list)
        assert len(result) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in result)
        mock_model.encode.assert_called_once_with("Hello world", convert_to_numpy=True)

    def test_embed_text_raises_when_unavailable(self):
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", False):
            with pytest.raises(RuntimeError, match="sentence-transformers not installed"):
                embed_text("Hello world")

    def test_embed_text_caches_model(self, mock_model):
        constructor = MagicMock(return_value=mock_model)
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True), \
             patch("distill.embeddings.SentenceTransformer", constructor):
            embed_text("First call")
            embed_text("Second call")

        # Model should only be created once
        constructor.assert_called_once_with(DEFAULT_MODEL)


class TestEmbedTexts:
    def test_embed_texts_batch(self, mock_model_batch):
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True), \
             patch("distill.embeddings.SentenceTransformer", return_value=mock_model_batch):
            result = embed_texts(["Hello", "World", "Test"])

        assert len(result) == 3
        assert all(len(v) == EMBEDDING_DIM for v in result)

    def test_embed_texts_empty(self, mock_model_batch):
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True), \
             patch("distill.embeddings.SentenceTransformer", return_value=mock_model_batch):
            result = embed_texts([])

        assert result == []


class TestItemText:
    def test_title_only(self):
        item = _make_item(title="My Title", body="", excerpt="")
        assert _item_text(item) == "My Title"

    def test_title_and_excerpt(self):
        item = _make_item(title="My Title", excerpt="Short summary")
        text = _item_text(item)
        assert "My Title" in text
        assert "Short summary" in text

    def test_title_and_body_fallback(self):
        item = _make_item(title="My Title", body="Body content here", excerpt="")
        text = _item_text(item)
        assert "My Title" in text
        assert "Body content here" in text

    def test_with_tags(self):
        item = _make_item(title="My Title", tags=["python", "AI"])
        text = _item_text(item)
        assert "python" in text
        assert "AI" in text

    def test_truncates_long_excerpt(self):
        long_excerpt = "x" * 1000
        item = _make_item(excerpt=long_excerpt)
        text = _item_text(item)
        # Excerpt should be truncated to 500 chars
        assert len(text) < 1000

    def test_empty_item(self):
        item = _make_item(title="", body="", excerpt="", tags=[])
        assert _item_text(item) == ""


class TestEmbedItems:
    def test_embed_items(self, mock_model_batch):
        items = [_make_item(f"id-{i}", f"Title {i}") for i in range(3)]
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True), \
             patch("distill.embeddings.SentenceTransformer", return_value=mock_model_batch):
            result = embed_items(items)

        assert len(result) == 3
        for item, embedding in result:
            assert isinstance(item, ContentItem)
            assert len(embedding) == EMBEDDING_DIM

    def test_embed_items_empty(self, mock_model_batch):
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True), \
             patch("distill.embeddings.SentenceTransformer", return_value=mock_model_batch):
            result = embed_items([])

        assert result == []

    def test_embed_items_preserves_order(self, mock_model_batch):
        items = [_make_item(f"id-{i}", f"Title {i}") for i in range(5)]
        with patch("distill.embeddings._HAS_SENTENCE_TRANSFORMERS", True), \
             patch("distill.embeddings.SentenceTransformer", return_value=mock_model_batch):
            result = embed_items(items)

        for i, (item, _) in enumerate(result):
            assert item.id == f"id-{i}"
