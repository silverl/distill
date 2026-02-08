"""Content store with pgvector similarity search.

Provides persistent storage for ContentItems with vector embeddings,
enabling similarity search across all ingested content. Falls back to
a JSON-based store when Postgres is not available.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from distill.intake.models import ContentItem, ContentSource, ContentType
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Optional dependency
try:
    import sqlalchemy as sa
    from pgvector.sqlalchemy import Vector
    from sqlalchemy import (
        Column,
        DateTime,
        Integer,
        MetaData,
        String,
        Table,
        Text,
        create_engine,
    )
    from sqlalchemy.dialects.postgresql import ARRAY, JSONB

    _HAS_DB = True
except ImportError:
    sa = None  # type: ignore[assignment]
    Vector = None  # type: ignore[assignment, misc]
    _HAS_DB = False

EMBEDDING_DIM = 384
JSON_STORE_FILENAME = ".distill-content-store.json"


class StoredItem(BaseModel):
    """A content item with its embedding, for JSON fallback."""

    item: ContentItem
    embedding: list[float] = Field(default_factory=list)


class JsonStore:
    """Simple JSON-based content store (fallback when Postgres unavailable)."""

    def __init__(self, path: Path) -> None:
        self._path = path / JSON_STORE_FILENAME
        self._items: dict[str, StoredItem] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for item_data in data.get("items", []):
                    stored = StoredItem.model_validate(item_data)
                    self._items[stored.item.id] = stored
            except (json.JSONDecodeError, ValueError):
                logger.warning("Corrupt JSON store at %s, starting fresh", self._path)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"items": [s.model_dump(mode="json") for s in self._items.values()]}
        self._path.write_text(json.dumps(data, default=str), encoding="utf-8")

    def upsert(self, item: ContentItem, embedding: list[float]) -> None:
        """Insert or update a content item with its embedding."""
        self._items[item.id] = StoredItem(item=item, embedding=embedding)
        self._save()

    def upsert_many(self, items: list[tuple[ContentItem, list[float]]]) -> None:
        """Batch insert/update multiple items."""
        for item, embedding in items:
            self._items[item.id] = StoredItem(item=item, embedding=embedding)
        self._save()

    def get(self, item_id: str) -> ContentItem | None:
        """Get an item by ID."""
        stored = self._items.get(item_id)
        return stored.item if stored else None

    def find_similar(
        self,
        embedding: list[float],
        k: int = 5,
        exclude_ids: list[str] | None = None,
    ) -> list[ContentItem]:
        """Find k most similar items by cosine similarity."""
        if not self._items:
            return []

        exclude = set(exclude_ids or [])
        scored: list[tuple[float, ContentItem]] = []

        for stored in self._items.values():
            if stored.item.id in exclude:
                continue
            if not stored.embedding:
                continue
            sim = _cosine_similarity(embedding, stored.embedding)
            scored.append((sim, stored.item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:k]]

    def find_by_entity(self, entity: str) -> list[ContentItem]:
        """Find items mentioning a specific entity."""
        entity_lower = entity.lower()
        results: list[ContentItem] = []
        for stored in self._items.values():
            entities = stored.item.metadata.get("entities", {})
            if isinstance(entities, dict):
                for entity_list in entities.values():
                    if isinstance(entity_list, list) and any(
                        entity_lower in e.lower() for e in entity_list if isinstance(e, str)
                    ):
                        results.append(stored.item)
                        break
        return results

    def find_by_date_range(self, start: date, end: date) -> list[ContentItem]:
        """Find items published within a date range."""
        results: list[ContentItem] = []
        for stored in self._items.values():
            pub = stored.item.published_at
            if pub is not None:
                pub_date = pub.date() if isinstance(pub, datetime) else pub
                if start <= pub_date <= end:
                    results.append(stored.item)
        return results

    def find_by_source(self, source: ContentSource) -> list[ContentItem]:
        """Find items from a specific source."""
        return [s.item for s in self._items.values() if s.item.source == source]

    def find_by_tags(self, tags: list[str]) -> list[ContentItem]:
        """Find items matching any of the given tags."""
        tag_set = {t.lower() for t in tags}
        return [s.item for s in self._items.values() if tag_set & {t.lower() for t in s.item.tags}]

    def count(self) -> int:
        """Return total number of stored items."""
        return len(self._items)

    def all_items(self) -> list[ContentItem]:
        """Return all stored items."""
        return [s.item for s in self._items.values()]

    def delete(self, item_id: str) -> bool:
        """Delete an item by ID. Returns True if found and deleted."""
        if item_id in self._items:
            del self._items[item_id]
            self._save()
            return True
        return False


class PgvectorStore:
    """Postgres + pgvector content store."""

    def __init__(self, database_url: str) -> None:
        if not _HAS_DB:
            raise RuntimeError(
                "Database dependencies not installed. Install with: pip install 'distill[db]'"
            )
        self._engine = create_engine(database_url)
        self._metadata = MetaData()
        self._table = Table(
            "content_items",
            self._metadata,
            Column("id", String, primary_key=True),
            Column("url", Text, default=""),
            Column("title", Text, default=""),
            Column("body", Text, default=""),
            Column("excerpt", Text, default=""),
            Column("word_count", Integer, default=0),
            Column("author", String, default=""),
            Column("site_name", String, default=""),
            Column("source", String, nullable=False),
            Column("source_id", String, default=""),
            Column("content_type", String, default="article"),
            Column("tags", ARRAY(String), default=[]),
            Column("topics", ARRAY(String), default=[]),
            Column("entities", JSONB, default={}),
            Column("classification", JSONB, default={}),
            Column("published_at", DateTime(timezone=True)),
            Column("saved_at", DateTime(timezone=True)),
            Column("metadata_json", JSONB, default={}),
            Column("embedding", Vector(EMBEDDING_DIM)),
        )
        self._metadata.create_all(self._engine)

    def upsert(self, item: ContentItem, embedding: list[float]) -> None:
        """Insert or update a content item with its embedding."""
        row = self._item_to_row(item, embedding)
        with self._engine.begin() as conn:
            # Try update first, then insert
            existing = conn.execute(
                sa.select(self._table.c.id).where(self._table.c.id == item.id)
            ).fetchone()
            if existing:
                conn.execute(self._table.update().where(self._table.c.id == item.id).values(**row))
            else:
                conn.execute(self._table.insert().values(**row))

    def upsert_many(self, items: list[tuple[ContentItem, list[float]]]) -> None:
        """Batch insert/update multiple items."""
        for item, embedding in items:
            self.upsert(item, embedding)

    def get(self, item_id: str) -> ContentItem | None:
        """Get an item by ID."""
        with self._engine.connect() as conn:
            row = conn.execute(sa.select(self._table).where(self._table.c.id == item_id)).fetchone()
            if row:
                return self._row_to_item(row)
        return None

    def find_similar(
        self,
        embedding: list[float],
        k: int = 5,
        exclude_ids: list[str] | None = None,
    ) -> list[ContentItem]:
        """Find k most similar items using pgvector cosine distance."""
        query = (
            sa.select(self._table)
            .order_by(self._table.c.embedding.cosine_distance(embedding))
            .limit(k)
        )
        if exclude_ids:
            query = query.where(~self._table.c.id.in_(exclude_ids))

        with self._engine.connect() as conn:
            rows = conn.execute(query).fetchall()
            return [self._row_to_item(row) for row in rows]

    def find_by_entity(self, entity: str) -> list[ContentItem]:
        """Find items mentioning a specific entity."""
        # Use JSONB containment for entity search
        with self._engine.connect() as conn:
            # Search across all entity type arrays
            rows = conn.execute(
                sa.select(self._table).where(
                    sa.text("entities::text ILIKE :pattern").bindparams(pattern=f"%{entity}%")
                )
            ).fetchall()
            return [self._row_to_item(row) for row in rows]

    def find_by_date_range(self, start: date, end: date) -> list[ContentItem]:
        """Find items published within a date range."""
        start_dt = datetime(start.year, start.month, start.day)
        end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(self._table).where(self._table.c.published_at.between(start_dt, end_dt))
            ).fetchall()
            return [self._row_to_item(row) for row in rows]

    def find_by_source(self, source: ContentSource) -> list[ContentItem]:
        """Find items from a specific source."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(self._table).where(self._table.c.source == source.value)
            ).fetchall()
            return [self._row_to_item(row) for row in rows]

    def find_by_tags(self, tags: list[str]) -> list[ContentItem]:
        """Find items matching any of the given tags."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(self._table).where(self._table.c.tags.overlap(tags))
            ).fetchall()
            return [self._row_to_item(row) for row in rows]

    def count(self) -> int:
        """Return total number of stored items."""
        with self._engine.connect() as conn:
            result = conn.execute(sa.select(sa.func.count()).select_from(self._table))
            return result.scalar() or 0

    def delete(self, item_id: str) -> bool:
        """Delete an item by ID."""
        with self._engine.begin() as conn:
            result = conn.execute(self._table.delete().where(self._table.c.id == item_id))
            return result.rowcount > 0

    def _item_to_row(self, item: ContentItem, embedding: list[float]) -> dict:
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
            "entities": item.metadata.get("entities", {}),
            "classification": item.metadata.get("classification", {}),
            "published_at": item.published_at,
            "saved_at": item.saved_at,
            "metadata_json": {
                k: v for k, v in item.metadata.items() if k not in ("entities", "classification")
            },
            "embedding": embedding,
        }

    def _row_to_item(self, row: object) -> ContentItem:
        """Convert a database row to a ContentItem."""
        # Row is a NamedTuple-like from SQLAlchemy
        r = row._mapping  # type: ignore[union-attr]
        metadata: dict[str, object] = dict(r.get("metadata_json", {}) or {})
        if r.get("entities"):
            metadata["entities"] = r["entities"]
        if r.get("classification"):
            metadata["classification"] = r["classification"]

        return ContentItem(
            id=r["id"],
            url=r.get("url", ""),
            title=r.get("title", ""),
            body=r.get("body", ""),
            excerpt=r.get("excerpt", ""),
            word_count=r.get("word_count", 0),
            author=r.get("author", ""),
            site_name=r.get("site_name", ""),
            source=ContentSource(r["source"]),
            source_id=r.get("source_id", ""),
            content_type=ContentType(r.get("content_type", "article")),
            tags=list(r.get("tags", []) or []),
            topics=list(r.get("topics", []) or []),
            published_at=r.get("published_at"),
            saved_at=r.get("saved_at") or datetime.now(),
            metadata=metadata,
        )


def create_store(
    database_url: str | None = None,
    fallback_dir: Path | None = None,
) -> JsonStore | PgvectorStore:
    """Create the appropriate content store.

    Tries Postgres first if database_url is provided and deps are installed.
    Falls back to JSON store.

    Args:
        database_url: Postgres connection URL (e.g. postgresql://localhost/distill).
        fallback_dir: Directory for JSON fallback store.

    Returns:
        A content store instance.
    """
    if database_url and _HAS_DB:
        try:
            store = PgvectorStore(database_url)
            logger.info("Using pgvector store at %s", database_url.split("@")[-1])
            return store
        except Exception:
            logger.warning("Could not connect to Postgres, falling back to JSON store")

    if fallback_dir is None:
        fallback_dir = Path(".")
    logger.info("Using JSON content store at %s", fallback_dir)
    return JsonStore(fallback_dir)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
