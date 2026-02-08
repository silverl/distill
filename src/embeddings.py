"""Text embeddings for content similarity search.

Uses sentence-transformers for local embedding generation (no external API).
Falls back gracefully when the optional dependency is not installed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distill.intake.models import ContentItem

logger = logging.getLogger(__name__)

# Optional dependency
try:
    from sentence_transformers import SentenceTransformer

    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment, misc]
    _HAS_SENTENCE_TRANSFORMERS = False

# Default model: small, fast, 384 dimensions
DEFAULT_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Module-level cache for the model
_model_cache: dict[str, object] = {}


def is_available() -> bool:
    """Check if embedding generation is available."""
    return _HAS_SENTENCE_TRANSFORMERS


def _get_model(model_name: str = DEFAULT_MODEL) -> object:
    """Get or create a cached SentenceTransformer model."""
    if not _HAS_SENTENCE_TRANSFORMERS:
        raise RuntimeError(
            "sentence-transformers not installed. Install with: pip install 'distill[embeddings]'"
        )
    if model_name not in _model_cache:
        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def embed_text(text: str, *, model_name: str = DEFAULT_MODEL) -> list[float]:
    """Embed a single text string.

    Args:
        text: Text to embed.
        model_name: SentenceTransformer model name.

    Returns:
        List of floats (embedding vector).

    Raises:
        RuntimeError: If sentence-transformers is not installed.
    """
    model = _get_model(model_name)
    vector = model.encode(text, convert_to_numpy=True)  # type: ignore[union-attr]
    return vector.tolist()


def embed_texts(texts: list[str], *, model_name: str = DEFAULT_MODEL) -> list[list[float]]:
    """Batch embed multiple texts.

    Args:
        texts: List of texts to embed.
        model_name: SentenceTransformer model name.

    Returns:
        List of embedding vectors.

    Raises:
        RuntimeError: If sentence-transformers is not installed.
    """
    if not texts:
        return []
    model = _get_model(model_name)
    vectors = model.encode(texts, convert_to_numpy=True)  # type: ignore[union-attr]
    return [v.tolist() for v in vectors]


def _item_text(item: ContentItem) -> str:
    """Build embeddable text from a ContentItem.

    Combines title, excerpt/body, and tags for richer representation.
    """
    parts: list[str] = []
    if item.title:
        parts.append(item.title)
    if item.excerpt:
        parts.append(item.excerpt[:500])
    elif item.body:
        parts.append(item.body[:500])
    if item.tags:
        parts.append(" ".join(item.tags[:10]))
    return " ".join(parts)


def embed_items(
    items: list[ContentItem],
    *,
    model_name: str = DEFAULT_MODEL,
) -> list[tuple[ContentItem, list[float]]]:
    """Embed a list of ContentItems.

    Args:
        items: Content items to embed.
        model_name: SentenceTransformer model name.

    Returns:
        List of (item, embedding) tuples.

    Raises:
        RuntimeError: If sentence-transformers is not installed.
    """
    if not items:
        return []
    texts = [_item_text(item) for item in items]
    vectors = embed_texts(texts, model_name=model_name)
    return list(zip(items, vectors, strict=True))
