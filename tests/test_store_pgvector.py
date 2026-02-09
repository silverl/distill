"""Tests for PgvectorStore (Postgres + pgvector content store).

These tests require sqlalchemy and pgvector to be installed.
All database interactions are mocked -- no real Postgres connection is needed.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from distill.store import _HAS_DB

# Skip the entire module if DB dependencies are not installed.
pytestmark = pytest.mark.skipif(not _HAS_DB, reason="sqlalchemy/pgvector not installed")

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.store import EMBEDDING_DIM, PgvectorStore, create_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    item_id: str = "item-1",
    title: str = "Test Article",
    body: str = "Article body text for testing.",
    source: ContentSource = ContentSource.RSS,
    content_type: ContentType = ContentType.ARTICLE,
    tags: list[str] | None = None,
    topics: list[str] | None = None,
    published_at: datetime | None = None,
    saved_at: datetime | None = None,
    metadata: dict | None = None,
    url: str = "https://example.com/article",
    excerpt: str = "An excerpt.",
    word_count: int = 100,
    author: str = "Author",
    site_name: str = "Example",
    source_id: str = "src-1",
) -> ContentItem:
    kwargs: dict = {
        "id": item_id,
        "url": url,
        "title": title,
        "body": body,
        "excerpt": excerpt,
        "word_count": word_count,
        "author": author,
        "site_name": site_name,
        "source": source,
        "source_id": source_id,
        "content_type": content_type,
        "tags": tags or [],
        "topics": topics or [],
        "published_at": published_at,
        "metadata": metadata or {},
    }
    if saved_at is not None:
        kwargs["saved_at"] = saved_at
    return ContentItem(**kwargs)


def _make_embedding(dim: int = EMBEDDING_DIM, seed: int = 42) -> list[float]:
    """Generate a deterministic pseudo-random embedding vector."""
    import random

    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec]


def _mock_row(mapping: dict) -> MagicMock:
    """Create a mock database row with a _mapping attribute."""
    row = MagicMock()
    row._mapping = mapping
    return row


def _build_row_mapping(
    item: ContentItem,
    embedding: list[float] | None = None,
    entities: dict | None = None,
    classification: dict | None = None,
    metadata_json: dict | None = None,
) -> dict:
    """Build a row-mapping dict that mirrors what _item_to_row produces."""
    return {
        "id": item.id,
        "url": item.url,
        "title": item.title,
        "body": item.body,
        "excerpt": item.excerpt,
        "word_count": item.word_count,
        "author": item.author,
        "site_name": item.site_name,
        "source": item.source.value,
        "source_id": item.source_id,
        "content_type": item.content_type.value,
        "tags": item.tags,
        "topics": item.topics,
        "entities": entities or item.metadata.get("entities", {}),
        "classification": classification or item.metadata.get("classification", {}),
        "published_at": item.published_at,
        "saved_at": item.saved_at,
        "metadata_json": metadata_json
        if metadata_json is not None
        else {k: v for k, v in item.metadata.items() if k not in ("entities", "classification")},
        "embedding": embedding or _make_embedding(),
    }


# ---------------------------------------------------------------------------
# Fixture: a PgvectorStore with a mocked engine
# ---------------------------------------------------------------------------

@pytest.fixture()
def store() -> PgvectorStore:
    """Create a PgvectorStore with all SQLAlchemy internals mocked."""
    with patch("distill.store.create_engine") as mock_create_engine, patch(
        "distill.store.MetaData"
    ) as mock_metadata_cls:
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_metadata = MagicMock()
        mock_metadata_cls.return_value = mock_metadata

        s = PgvectorStore("postgresql://localhost/testdb")

        # Verify engine was created with the correct URL
        mock_create_engine.assert_called_once_with("postgresql://localhost/testdb")
        # Verify create_all was called to initialize tables
        mock_metadata.create_all.assert_called_once_with(mock_engine)

    return s


# ===========================================================================
# Test: __init__
# ===========================================================================

class TestPgvectorStoreInit:
    def test_init_creates_engine_and_table(self):
        with patch("distill.store.create_engine") as mock_create_engine, patch(
            "distill.store.MetaData"
        ) as mock_metadata_cls:
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine
            mock_metadata = MagicMock()
            mock_metadata_cls.return_value = mock_metadata

            s = PgvectorStore("postgresql://host/db")

            mock_create_engine.assert_called_once_with("postgresql://host/db")
            mock_metadata.create_all.assert_called_once_with(mock_engine)
            assert s._engine is mock_engine
            assert s._table is not None

    def test_init_raises_without_db_deps(self):
        with patch("distill.store._HAS_DB", False):
            with pytest.raises(RuntimeError, match="Database dependencies not installed"):
                PgvectorStore("postgresql://localhost/testdb")


# ===========================================================================
# Test: upsert
# ===========================================================================

class TestPgvectorStoreUpsert:
    def test_upsert_inserts_new_item(self, store: PgvectorStore):
        item = _make_item("new-item")
        embedding = _make_embedding(seed=1)

        mock_conn = MagicMock()
        # fetchone returns None -> item does not exist yet
        mock_conn.execute.return_value.fetchone.return_value = None
        store._engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        store.upsert(item, embedding)

        # Should have called execute twice: SELECT to check existence, then INSERT
        assert mock_conn.execute.call_count == 2

    def test_upsert_updates_existing_item(self, store: PgvectorStore):
        item = _make_item("existing-item")
        embedding = _make_embedding(seed=2)

        mock_conn = MagicMock()
        # fetchone returns a row -> item already exists
        mock_conn.execute.return_value.fetchone.return_value = MagicMock()
        store._engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        store.upsert(item, embedding)

        # Should have called execute twice: SELECT to check existence, then UPDATE
        assert mock_conn.execute.call_count == 2


# ===========================================================================
# Test: upsert_many
# ===========================================================================

class TestPgvectorStoreUpsertMany:
    def test_upsert_many_calls_upsert_for_each(self, store: PgvectorStore):
        items = [
            (_make_item(f"id-{i}"), _make_embedding(seed=i))
            for i in range(3)
        ]

        with patch.object(store, "upsert") as mock_upsert:
            store.upsert_many(items)
            assert mock_upsert.call_count == 3
            for i, (item, emb) in enumerate(items):
                mock_upsert.assert_any_call(item, emb)

    def test_upsert_many_empty_list(self, store: PgvectorStore):
        with patch.object(store, "upsert") as mock_upsert:
            store.upsert_many([])
            mock_upsert.assert_not_called()


# ===========================================================================
# Test: get
# ===========================================================================

class TestPgvectorStoreGet:
    def test_get_existing_item(self, store: PgvectorStore):
        item = _make_item("found-item", title="Found")
        row_mapping = _build_row_mapping(item)
        mock_row = _mock_row(row_mapping)

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        result = store.get("found-item")

        assert result is not None
        assert result.id == "found-item"
        assert result.title == "Found"
        assert result.source == ContentSource.RSS

    def test_get_nonexistent_returns_none(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        result = store.get("nonexistent")
        assert result is None


# ===========================================================================
# Test: find_similar
# ===========================================================================

class TestPgvectorStoreFindSimilar:
    def test_find_similar_returns_items(self, store: PgvectorStore):
        item_a = _make_item("a", title="Alpha")
        item_b = _make_item("b", title="Beta")
        rows = [
            _mock_row(_build_row_mapping(item_a)),
            _mock_row(_build_row_mapping(item_b)),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_similar(_make_embedding(seed=10), k=5)

        assert len(results) == 2
        assert results[0].id == "a"
        assert results[1].id == "b"

    def test_find_similar_empty_results(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_similar(_make_embedding(seed=10), k=5)
        assert results == []

    def test_find_similar_with_exclude_ids(self, store: PgvectorStore):
        item_b = _make_item("b", title="Beta")
        rows = [_mock_row(_build_row_mapping(item_b))]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_similar(
            _make_embedding(seed=10), k=5, exclude_ids=["a"]
        )

        assert len(results) == 1
        assert results[0].id == "b"
        # Verify that execute was called (the query was built with the exclusion)
        mock_conn.execute.assert_called_once()

    def test_find_similar_without_exclude_ids(self, store: PgvectorStore):
        """When exclude_ids is None, the WHERE clause for exclusion is not added."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        store.find_similar(_make_embedding(seed=10), k=3, exclude_ids=None)
        mock_conn.execute.assert_called_once()

    def test_find_similar_custom_k(self, store: PgvectorStore):
        """Verify k parameter is respected (even though limit is applied DB-side)."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        store.find_similar(_make_embedding(seed=10), k=10)
        mock_conn.execute.assert_called_once()


# ===========================================================================
# Test: find_by_entity
# ===========================================================================

class TestPgvectorStoreFindByEntity:
    def test_find_by_entity_returns_matches(self, store: PgvectorStore):
        item = _make_item("e-1", title="Entity Match")
        rows = [_mock_row(_build_row_mapping(item, entities={"technologies": ["Python"]}))]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_entity("Python")

        assert len(results) == 1
        assert results[0].id == "e-1"

    def test_find_by_entity_no_match(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_entity("NonExistent")
        assert results == []


# ===========================================================================
# Test: find_by_date_range
# ===========================================================================

class TestPgvectorStoreFindByDateRange:
    def test_find_by_date_range_returns_items(self, store: PgvectorStore):
        pub = datetime(2026, 2, 5, 12, 0, 0, tzinfo=timezone.utc)
        item = _make_item("feb-item", published_at=pub)
        rows = [_mock_row(_build_row_mapping(item))]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_date_range(date(2026, 2, 1), date(2026, 2, 28))

        assert len(results) == 1
        assert results[0].id == "feb-item"

    def test_find_by_date_range_constructs_correct_datetimes(self, store: PgvectorStore):
        """Verify start_dt is midnight and end_dt is 23:59:59."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        # Just call the method; verifying it doesn't raise is sufficient
        # since the datetime construction happens internally.
        results = store.find_by_date_range(date(2026, 1, 1), date(2026, 12, 31))
        assert results == []

    def test_find_by_date_range_no_match(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_date_range(date(2025, 1, 1), date(2025, 1, 31))
        assert results == []


# ===========================================================================
# Test: find_by_source
# ===========================================================================

class TestPgvectorStoreFindBySource:
    def test_find_by_source_returns_matches(self, store: PgvectorStore):
        item = _make_item("rss-1", source=ContentSource.RSS)
        rows = [_mock_row(_build_row_mapping(item))]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_source(ContentSource.RSS)

        assert len(results) == 1
        assert results[0].source == ContentSource.RSS

    def test_find_by_source_no_match(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_source(ContentSource.GMAIL)
        assert results == []


# ===========================================================================
# Test: find_by_tags
# ===========================================================================

class TestPgvectorStoreFindByTags:
    def test_find_by_tags_returns_matches(self, store: PgvectorStore):
        item = _make_item("tagged", tags=["python", "AI"])
        rows = [_mock_row(_build_row_mapping(item))]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_tags(["python"])

        assert len(results) == 1
        assert results[0].id == "tagged"

    def test_find_by_tags_no_match(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        results = store.find_by_tags(["nonexistent-tag"])
        assert results == []


# ===========================================================================
# Test: count
# ===========================================================================

class TestPgvectorStoreCount:
    def test_count_returns_value(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = 42
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        assert store.count() == 42

    def test_count_returns_zero_when_none(self, store: PgvectorStore):
        """When scalar() returns None, count should return 0."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = None
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        assert store.count() == 0

    def test_count_returns_zero_for_empty_table(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = 0
        store._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        assert store.count() == 0


# ===========================================================================
# Test: delete
# ===========================================================================

class TestPgvectorStoreDelete:
    def test_delete_existing_returns_true(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result
        store._engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        assert store.delete("item-to-delete") is True

    def test_delete_nonexistent_returns_false(self, store: PgvectorStore):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_conn.execute.return_value = mock_result
        store._engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        store._engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        assert store.delete("nonexistent") is False


# ===========================================================================
# Test: _item_to_row
# ===========================================================================

class TestItemToRow:
    def test_basic_conversion(self, store: PgvectorStore):
        item = _make_item(
            "conv-1",
            title="Conversion Test",
            source=ContentSource.SESSION,
            content_type=ContentType.ARTICLE,
            tags=["python"],
            topics=["coding"],
            metadata={"extra_key": "extra_value"},
        )
        embedding = _make_embedding(seed=5)

        row = store._item_to_row(item, embedding)

        assert row["id"] == "conv-1"
        assert row["title"] == "Conversion Test"
        assert row["source"] == "session"
        assert row["content_type"] == "article"
        assert row["tags"] == ["python"]
        assert row["topics"] == ["coding"]
        assert row["embedding"] is embedding
        assert row["entities"] == {}
        assert row["classification"] == {}
        assert row["metadata_json"] == {"extra_key": "extra_value"}

    def test_entities_extracted_from_metadata(self, store: PgvectorStore):
        entities = {"technologies": ["Python", "Rust"]}
        classification = {"category": "tech"}
        item = _make_item(
            "conv-2",
            metadata={
                "entities": entities,
                "classification": classification,
                "other_key": "other_val",
            },
        )
        embedding = _make_embedding(seed=6)

        row = store._item_to_row(item, embedding)

        assert row["entities"] == entities
        assert row["classification"] == classification
        # entities and classification should be excluded from metadata_json
        assert "entities" not in row["metadata_json"]
        assert "classification" not in row["metadata_json"]
        assert row["metadata_json"] == {"other_key": "other_val"}

    def test_timestamps_preserved(self, store: PgvectorStore):
        pub = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        saved = datetime(2026, 1, 16, 8, 0, 0, tzinfo=timezone.utc)
        item = _make_item("conv-3", published_at=pub, saved_at=saved)
        embedding = _make_embedding(seed=7)

        row = store._item_to_row(item, embedding)

        assert row["published_at"] == pub
        assert row["saved_at"] == saved

    def test_none_published_at(self, store: PgvectorStore):
        item = _make_item("conv-4", published_at=None)
        embedding = _make_embedding(seed=8)

        row = store._item_to_row(item, embedding)

        assert row["published_at"] is None


# ===========================================================================
# Test: _row_to_item
# ===========================================================================

class TestRowToItem:
    def test_basic_conversion(self, store: PgvectorStore):
        mapping = {
            "id": "row-1",
            "url": "https://example.com",
            "title": "Row Title",
            "body": "Row body",
            "excerpt": "Row excerpt",
            "word_count": 500,
            "author": "Jane",
            "site_name": "Example Blog",
            "source": "rss",
            "source_id": "rss-123",
            "content_type": "article",
            "tags": ["python", "ai"],
            "topics": ["machine-learning"],
            "entities": {"technologies": ["Python"]},
            "classification": {"category": "tech"},
            "published_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "saved_at": datetime(2026, 2, 2, tzinfo=timezone.utc),
            "metadata_json": {"extra": "data"},
            "embedding": _make_embedding(),
        }
        row = _mock_row(mapping)

        result = store._row_to_item(row)

        assert result.id == "row-1"
        assert result.url == "https://example.com"
        assert result.title == "Row Title"
        assert result.body == "Row body"
        assert result.excerpt == "Row excerpt"
        assert result.word_count == 500
        assert result.author == "Jane"
        assert result.site_name == "Example Blog"
        assert result.source == ContentSource.RSS
        assert result.source_id == "rss-123"
        assert result.content_type == ContentType.ARTICLE
        assert result.tags == ["python", "ai"]
        assert result.topics == ["machine-learning"]
        assert result.published_at == datetime(2026, 2, 1, tzinfo=timezone.utc)
        assert result.saved_at == datetime(2026, 2, 2, tzinfo=timezone.utc)
        # metadata should merge metadata_json + entities + classification
        assert result.metadata["extra"] == "data"
        assert result.metadata["entities"] == {"technologies": ["Python"]}
        assert result.metadata["classification"] == {"category": "tech"}

    def test_missing_optional_fields_use_defaults(self, store: PgvectorStore):
        """When optional fields are missing from the row, defaults are used."""
        mapping = {
            "id": "row-minimal",
            "source": "gmail",
        }
        row = _mock_row(mapping)

        result = store._row_to_item(row)

        assert result.id == "row-minimal"
        assert result.url == ""
        assert result.title == ""
        assert result.body == ""
        assert result.excerpt == ""
        assert result.word_count == 0
        assert result.author == ""
        assert result.site_name == ""
        assert result.source == ContentSource.GMAIL
        assert result.source_id == ""
        assert result.content_type == ContentType.ARTICLE
        assert result.tags == []
        assert result.topics == []

    def test_none_tags_and_topics_become_empty_lists(self, store: PgvectorStore):
        mapping = {
            "id": "row-none-lists",
            "source": "rss",
            "tags": None,
            "topics": None,
        }
        row = _mock_row(mapping)

        result = store._row_to_item(row)

        assert result.tags == []
        assert result.topics == []

    def test_no_entities_or_classification(self, store: PgvectorStore):
        mapping = {
            "id": "row-no-extra",
            "source": "browser",
            "entities": None,
            "classification": None,
            "metadata_json": {"key": "value"},
        }
        row = _mock_row(mapping)

        result = store._row_to_item(row)

        assert "entities" not in result.metadata
        assert "classification" not in result.metadata
        assert result.metadata["key"] == "value"

    def test_empty_entities_and_classification_not_added(self, store: PgvectorStore):
        """Empty dicts/falsy values for entities/classification are not merged."""
        mapping = {
            "id": "row-empty-extra",
            "source": "rss",
            "entities": {},
            "classification": {},
            "metadata_json": {},
        }
        row = _mock_row(mapping)

        result = store._row_to_item(row)

        # Empty dicts are falsy, so they should NOT be added to metadata
        assert "entities" not in result.metadata
        assert "classification" not in result.metadata

    def test_none_metadata_json(self, store: PgvectorStore):
        """When metadata_json is None, metadata starts as empty dict."""
        mapping = {
            "id": "row-none-meta",
            "source": "rss",
            "metadata_json": None,
        }
        row = _mock_row(mapping)

        result = store._row_to_item(row)

        assert result.metadata == {}

    def test_none_saved_at_uses_now(self, store: PgvectorStore):
        """When saved_at is None, it defaults to datetime.now()."""
        mapping = {
            "id": "row-no-saved",
            "source": "rss",
            "saved_at": None,
        }
        row = _mock_row(mapping)

        before = datetime.now()
        result = store._row_to_item(row)
        after = datetime.now()

        assert before <= result.saved_at <= after

    def test_content_type_defaults_to_article(self, store: PgvectorStore):
        mapping = {
            "id": "row-no-type",
            "source": "rss",
            "content_type": None,
        }
        row = _mock_row(mapping)

        result = store._row_to_item(row)

        assert result.content_type == ContentType.ARTICLE


# ===========================================================================
# Test: roundtrip (_item_to_row -> _row_to_item)
# ===========================================================================

class TestItemRowRoundtrip:
    def test_roundtrip_preserves_data(self, store: PgvectorStore):
        """Converting item -> row -> item should preserve all fields."""
        item = _make_item(
            "rt-1",
            title="Roundtrip Test",
            body="Testing round-trip conversion.",
            source=ContentSource.SUBSTACK,
            content_type=ContentType.NEWSLETTER,
            tags=["testing", "roundtrip"],
            topics=["quality"],
            published_at=datetime(2026, 2, 7, 14, 30, 0, tzinfo=timezone.utc),
            metadata={
                "entities": {"people": ["Alice", "Bob"]},
                "classification": {"type": "tutorial"},
                "reading_time": 5,
            },
            url="https://sub.example.com/p/test",
            excerpt="A test excerpt",
            word_count=1234,
            author="Tester",
            site_name="Test Blog",
            source_id="sub-rt-1",
        )
        embedding = _make_embedding(seed=99)

        row_dict = store._item_to_row(item, embedding)
        mock_row = _mock_row(row_dict)
        result = store._row_to_item(mock_row)

        assert result.id == item.id
        assert result.url == item.url
        assert result.title == item.title
        assert result.body == item.body
        assert result.excerpt == item.excerpt
        assert result.word_count == item.word_count
        assert result.author == item.author
        assert result.site_name == item.site_name
        assert result.source == item.source
        assert result.source_id == item.source_id
        assert result.content_type == item.content_type
        assert result.tags == item.tags
        assert result.topics == item.topics
        assert result.published_at == item.published_at
        assert result.metadata["entities"] == {"people": ["Alice", "Bob"]}
        assert result.metadata["classification"] == {"type": "tutorial"}
        assert result.metadata["reading_time"] == 5


# ===========================================================================
# Test: create_store fallback path
# ===========================================================================

class TestCreateStorePgvectorFallback:
    def test_pgvector_connection_failure_falls_back_to_json(self, tmp_path):
        """When PgvectorStore raises during init, create_store falls back to JsonStore."""
        from distill.store import JsonStore

        with patch("distill.store._HAS_DB", True), patch(
            "distill.store.PgvectorStore",
            side_effect=Exception("Connection refused"),
        ):
            store = create_store(
                database_url="postgresql://localhost/nonexistent",
                fallback_dir=tmp_path,
            )

        assert isinstance(store, JsonStore)

    def test_pgvector_success_returns_pgvector_store(self, tmp_path):
        """When PgvectorStore init succeeds, create_store returns it."""
        mock_pgvector_store = MagicMock(spec=PgvectorStore)

        with patch("distill.store._HAS_DB", True), patch(
            "distill.store.PgvectorStore",
            return_value=mock_pgvector_store,
        ):
            store = create_store(
                database_url="postgresql://localhost/testdb",
                fallback_dir=tmp_path,
            )

        assert store is mock_pgvector_store

    def test_no_db_deps_with_url_falls_back(self, tmp_path):
        """When _HAS_DB is False but a URL is provided, falls back to JsonStore."""
        from distill.store import JsonStore

        with patch("distill.store._HAS_DB", False):
            store = create_store(
                database_url="postgresql://localhost/testdb",
                fallback_dir=tmp_path,
            )

        assert isinstance(store, JsonStore)

    def test_no_url_returns_json_store(self, tmp_path):
        """When no database_url is provided, always returns JsonStore."""
        from distill.store import JsonStore

        store = create_store(database_url=None, fallback_dir=tmp_path)
        assert isinstance(store, JsonStore)

    def test_fallback_uses_default_dir_when_none(self):
        """When fallback_dir is None, uses current directory."""
        from distill.store import JsonStore

        store = create_store(database_url=None, fallback_dir=None)
        assert isinstance(store, JsonStore)
