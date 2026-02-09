"""Tests for content store (JSON fallback)."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.store import (
    JSON_STORE_FILENAME,
    JsonStore,
    _cosine_similarity,
    create_store,
)


def _make_item(
    item_id: str = "item-1",
    title: str = "Test Article",
    body: str = "Article body text for testing.",
    source: ContentSource = ContentSource.RSS,
    tags: list[str] | None = None,
    published_at: datetime | None = None,
    metadata: dict | None = None,
) -> ContentItem:
    return ContentItem(
        id=item_id,
        title=title,
        body=body,
        source=source,
        content_type=ContentType.ARTICLE,
        tags=tags or [],
        published_at=published_at,
        metadata=metadata or {},
    )


def _make_embedding(dim: int = 384, seed: int = 42) -> list[float]:
    """Generate a deterministic pseudo-random embedding vector."""
    import random

    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec]  # unit normalize


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_different_lengths(self):
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_empty_vectors(self):
        assert _cosine_similarity([], []) == 0.0


class TestJsonStoreUpsert:
    def test_upsert_new_item(self, tmp_path):
        store = JsonStore(tmp_path)
        item = _make_item("id-1")
        embedding = _make_embedding(seed=1)

        store.upsert(item, embedding)

        assert store.count() == 1
        retrieved = store.get("id-1")
        assert retrieved is not None
        assert retrieved.title == "Test Article"

    def test_upsert_replaces_existing(self, tmp_path):
        store = JsonStore(tmp_path)
        item1 = _make_item("id-1", title="Original")
        item2 = _make_item("id-1", title="Updated")
        emb = _make_embedding(seed=1)

        store.upsert(item1, emb)
        store.upsert(item2, emb)

        assert store.count() == 1
        assert store.get("id-1").title == "Updated"

    def test_upsert_many(self, tmp_path):
        store = JsonStore(tmp_path)
        items = [
            (_make_item(f"id-{i}", f"Title {i}"), _make_embedding(seed=i))
            for i in range(5)
        ]
        store.upsert_many(items)

        assert store.count() == 5
        for i in range(5):
            assert store.get(f"id-{i}") is not None

    def test_get_nonexistent(self, tmp_path):
        store = JsonStore(tmp_path)
        assert store.get("nonexistent") is None


class TestJsonStorePersistence:
    def test_save_and_load(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(_make_item("id-1", "Test"), _make_embedding(seed=1))

        # Create new store from same path
        store2 = JsonStore(tmp_path)
        assert store2.count() == 1
        assert store2.get("id-1").title == "Test"

    def test_load_empty(self, tmp_path):
        store = JsonStore(tmp_path)
        assert store.count() == 0

    def test_load_corrupt(self, tmp_path):
        (tmp_path / JSON_STORE_FILENAME).write_text("not json!", encoding="utf-8")
        store = JsonStore(tmp_path)
        assert store.count() == 0

    def test_file_created(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(_make_item("id-1"), _make_embedding(seed=1))
        assert (tmp_path / JSON_STORE_FILENAME).exists()


class TestJsonStoreSimilarity:
    def test_find_similar_returns_ordered(self, tmp_path):
        store = JsonStore(tmp_path)

        # Create items with known embeddings
        target_emb = _make_embedding(seed=100)
        similar_emb = _make_embedding(seed=100)  # identical = most similar
        different_emb = _make_embedding(seed=999)

        store.upsert(_make_item("similar", "Similar"), similar_emb)
        store.upsert(_make_item("different", "Different"), different_emb)

        results = store.find_similar(target_emb, k=2)
        assert len(results) == 2
        # Most similar should be first
        assert results[0].id == "similar"

    def test_find_similar_respects_k(self, tmp_path):
        store = JsonStore(tmp_path)
        for i in range(10):
            store.upsert(_make_item(f"id-{i}"), _make_embedding(seed=i))

        results = store.find_similar(_make_embedding(seed=0), k=3)
        assert len(results) == 3

    def test_find_similar_excludes_ids(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(_make_item("id-1"), _make_embedding(seed=1))
        store.upsert(_make_item("id-2"), _make_embedding(seed=2))
        store.upsert(_make_item("id-3"), _make_embedding(seed=3))

        results = store.find_similar(
            _make_embedding(seed=1), k=5, exclude_ids=["id-1"]
        )
        assert all(r.id != "id-1" for r in results)

    def test_find_similar_empty_store(self, tmp_path):
        store = JsonStore(tmp_path)
        results = store.find_similar(_make_embedding(seed=1), k=5)
        assert results == []

    def test_find_similar_skips_no_embedding(self, tmp_path):
        store = JsonStore(tmp_path)
        # Manually insert item with empty embedding
        from distill.store import StoredItem

        store._items["no-emb"] = StoredItem(item=_make_item("no-emb"), embedding=[])
        store._items["has-emb"] = StoredItem(
            item=_make_item("has-emb"), embedding=_make_embedding(seed=1)
        )

        results = store.find_similar(_make_embedding(seed=1), k=5)
        assert len(results) == 1
        assert results[0].id == "has-emb"


class TestJsonStoreEntitySearch:
    def test_find_by_entity(self, tmp_path):
        store = JsonStore(tmp_path)
        item = _make_item(
            "id-1",
            metadata={"entities": {"technologies": ["Python", "Rust"]}},
        )
        store.upsert(item, _make_embedding(seed=1))
        store.upsert(_make_item("id-2"), _make_embedding(seed=2))

        results = store.find_by_entity("Python")
        assert len(results) == 1
        assert results[0].id == "id-1"

    def test_find_by_entity_case_insensitive(self, tmp_path):
        store = JsonStore(tmp_path)
        item = _make_item(
            "id-1",
            metadata={"entities": {"technologies": ["Python"]}},
        )
        store.upsert(item, _make_embedding(seed=1))

        results = store.find_by_entity("python")
        assert len(results) == 1

    def test_find_by_entity_no_match(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(_make_item("id-1"), _make_embedding(seed=1))
        results = store.find_by_entity("NonExistent")
        assert results == []

    def test_find_by_entity_multiple_types(self, tmp_path):
        store = JsonStore(tmp_path)
        item = _make_item(
            "id-1",
            metadata={
                "entities": {
                    "technologies": ["Python"],
                    "projects": ["Distill"],
                    "people": ["Alice"],
                }
            },
        )
        store.upsert(item, _make_embedding(seed=1))

        assert len(store.find_by_entity("Python")) == 1
        assert len(store.find_by_entity("Distill")) == 1
        assert len(store.find_by_entity("Alice")) == 1


class TestJsonStoreDateRange:
    def test_find_by_date_range(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(
            _make_item("jan", published_at=datetime(2026, 1, 15, tzinfo=timezone.utc)),
            _make_embedding(seed=1),
        )
        store.upsert(
            _make_item("feb", published_at=datetime(2026, 2, 5, tzinfo=timezone.utc)),
            _make_embedding(seed=2),
        )
        store.upsert(
            _make_item("mar", published_at=datetime(2026, 3, 10, tzinfo=timezone.utc)),
            _make_embedding(seed=3),
        )

        results = store.find_by_date_range(date(2026, 2, 1), date(2026, 2, 28))
        assert len(results) == 1
        assert results[0].id == "feb"

    def test_find_by_date_range_inclusive(self, tmp_path):
        store = JsonStore(tmp_path)
        dt = datetime(2026, 2, 7, 12, 0, 0, tzinfo=timezone.utc)
        store.upsert(_make_item("exact", published_at=dt), _make_embedding(seed=1))

        results = store.find_by_date_range(date(2026, 2, 7), date(2026, 2, 7))
        assert len(results) == 1

    def test_find_by_date_range_no_match(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(
            _make_item("jan", published_at=datetime(2026, 1, 15, tzinfo=timezone.utc)),
            _make_embedding(seed=1),
        )
        results = store.find_by_date_range(date(2026, 6, 1), date(2026, 6, 30))
        assert results == []

    def test_find_by_date_range_skips_null_dates(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(_make_item("no-date"), _make_embedding(seed=1))
        results = store.find_by_date_range(date(2026, 1, 1), date(2026, 12, 31))
        assert results == []


class TestJsonStoreSourceSearch:
    def test_find_by_source(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(
            _make_item("rss-1", source=ContentSource.RSS), _make_embedding(seed=1)
        )
        store.upsert(
            _make_item("session-1", source=ContentSource.SESSION),
            _make_embedding(seed=2),
        )

        results = store.find_by_source(ContentSource.RSS)
        assert len(results) == 1
        assert results[0].id == "rss-1"

    def test_find_by_source_no_match(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(
            _make_item("rss-1", source=ContentSource.RSS), _make_embedding(seed=1)
        )
        results = store.find_by_source(ContentSource.GMAIL)
        assert results == []


class TestJsonStoreTagSearch:
    def test_find_by_tags(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(
            _make_item("id-1", tags=["python", "AI"]), _make_embedding(seed=1)
        )
        store.upsert(
            _make_item("id-2", tags=["rust", "systems"]), _make_embedding(seed=2)
        )

        results = store.find_by_tags(["python"])
        assert len(results) == 1
        assert results[0].id == "id-1"

    def test_find_by_tags_case_insensitive(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(
            _make_item("id-1", tags=["Python"]), _make_embedding(seed=1)
        )
        results = store.find_by_tags(["python"])
        assert len(results) == 1

    def test_find_by_tags_any_match(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(
            _make_item("id-1", tags=["python", "AI"]), _make_embedding(seed=1)
        )
        store.upsert(
            _make_item("id-2", tags=["rust"]), _make_embedding(seed=2)
        )

        results = store.find_by_tags(["AI", "rust"])
        assert len(results) == 2


class TestJsonStoreDelete:
    def test_delete_existing(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(_make_item("id-1"), _make_embedding(seed=1))

        assert store.delete("id-1") is True
        assert store.count() == 0
        assert store.get("id-1") is None

    def test_delete_nonexistent(self, tmp_path):
        store = JsonStore(tmp_path)
        assert store.delete("nonexistent") is False

    def test_delete_persists(self, tmp_path):
        store = JsonStore(tmp_path)
        store.upsert(_make_item("id-1"), _make_embedding(seed=1))
        store.delete("id-1")

        store2 = JsonStore(tmp_path)
        assert store2.count() == 0


class TestJsonStoreAllItems:
    def test_all_items(self, tmp_path):
        store = JsonStore(tmp_path)
        for i in range(3):
            store.upsert(_make_item(f"id-{i}"), _make_embedding(seed=i))

        items = store.all_items()
        assert len(items) == 3
        ids = {i.id for i in items}
        assert ids == {"id-0", "id-1", "id-2"}


class TestCreateStore:
    def test_creates_json_store_no_url(self, tmp_path):
        store = create_store(fallback_dir=tmp_path)
        assert isinstance(store, JsonStore)

    def test_creates_json_store_no_db_deps(self, tmp_path):
        from unittest.mock import patch

        with patch("distill.store._HAS_DB", False):
            store = create_store(database_url="postgresql://localhost/test", fallback_dir=tmp_path)
        assert isinstance(store, JsonStore)

    def test_creates_json_store_default_dir(self):
        store = create_store()
        assert isinstance(store, JsonStore)
