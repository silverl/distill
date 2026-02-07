"""Topic clustering for content items using TF-IDF similarity.

Groups related content items by topic so the LLM receives better
thematic groupings during synthesis.  Uses only stdlib — no sklearn
or other heavy dependencies.
"""

from __future__ import annotations

import math
import string
from collections import Counter

from distill.intake.models import ContentItem
from pydantic import BaseModel, Field

# ── stopwords ────────────────────────────────────────────────────────

_STOPWORDS: set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can",
    "could", "d", "did", "didn", "do", "does", "doesn", "doing", "don",
    "down", "during", "each", "few", "for", "from", "further", "get",
    "got", "had", "has", "hasn", "have", "haven", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "isn", "it", "its", "itself", "just", "ll", "m",
    "me", "might", "more", "most", "my", "myself", "need", "no", "nor",
    "not", "now", "o", "of", "off", "on", "once", "only", "or", "other",
    "our", "ours", "ourselves", "out", "over", "own", "re", "s", "same",
    "she", "should", "shouldn", "so", "some", "such", "t", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "ve", "very", "was", "wasn", "we", "were", "weren",
    "what", "when", "where", "which", "while", "who", "whom", "why",
    "will", "with", "won", "would", "wouldn", "you", "your", "yours",
    "yourself", "yourselves", "also", "new", "one", "two", "use", "used",
    "using", "like", "make", "many", "much", "well", "way", "even",
    "still", "may", "take", "come", "see", "know", "want", "look",
    "first", "go", "back", "think", "say", "said",
}

# Characters to strip from tokens (everything that isn't a letter or digit).
_STRIP_TABLE = str.maketrans("", "", string.punctuation + "\u2019\u2018\u201c\u201d")


# ── models ───────────────────────────────────────────────────────────

class TopicCluster(BaseModel):
    """A group of content items sharing a common topic."""

    label: str
    items: list[ContentItem]
    keywords: list[str] = Field(default_factory=list)


# ── tokenisation helpers ─────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stopwords."""
    tokens: list[str] = []
    for raw in text.lower().split():
        word = raw.translate(_STRIP_TABLE)
        if len(word) >= 2 and word not in _STOPWORDS and not word.isdigit():
            tokens.append(word)
    return tokens


def _item_text(item: ContentItem) -> str:
    """Combine title and excerpt (or body snippet) into a single string."""
    parts: list[str] = []
    if item.title:
        parts.append(item.title)
    if item.excerpt:
        parts.append(item.excerpt)
    elif item.body:
        parts.append(item.body[:500])
    for tag in item.tags:
        parts.append(tag)
    return " ".join(parts)


# ── TF-IDF ───────────────────────────────────────────────────────────

def _build_tfidf(
    docs: list[list[str]],
) -> tuple[list[str], list[dict[str, float]]]:
    """Build TF-IDF vectors for a list of tokenised documents.

    Returns:
        vocab: ordered list of terms.
        vectors: list of dicts mapping term -> tfidf weight.
    """
    n_docs = len(docs)
    if n_docs == 0:
        return [], []

    # Document frequency
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(set(doc))

    vocab = sorted(df.keys())

    # IDF: log(N / df_t)  —  add-one smoothing to avoid division by zero
    idf: dict[str, float] = {}
    for term in vocab:
        idf[term] = math.log((n_docs + 1) / (df[term] + 1)) + 1.0

    vectors: list[dict[str, float]] = []
    for doc in docs:
        tf: Counter[str] = Counter(doc)
        total = len(doc) if doc else 1
        vec: dict[str, float] = {}
        for term, count in tf.items():
            if term in idf:
                vec[term] = (count / total) * idf[term]
        vectors.append(vec)

    return vocab, vectors


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors (dicts)."""
    # Only iterate over the smaller dict for efficiency
    if len(a) > len(b):
        a, b = b, a

    dot = 0.0
    for term, w in a.items():
        if term in b:
            dot += w * b[term]

    if dot == 0.0:
        return 0.0

    norm_a = math.sqrt(sum(w * w for w in a.values()))
    norm_b = math.sqrt(sum(w * w for w in b.values()))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


# ── clustering ───────────────────────────────────────────────────────

def _merge_vectors(
    va: dict[str, float], vb: dict[str, float]
) -> dict[str, float]:
    """Average two sparse vectors (used after merging clusters)."""
    merged: dict[str, float] = dict(va)
    for term, w in vb.items():
        merged[term] = (merged.get(term, 0.0) + w) / 2.0
    # Normalise values that were already in va but not vb
    for term in va:
        if term not in vb:
            merged[term] = va[term] / 2.0
    return merged


def _top_keywords(vector: dict[str, float], n: int = 5) -> list[str]:
    """Return the top-n terms by weight from a sparse vector."""
    return [
        term
        for term, _ in sorted(vector.items(), key=lambda kv: kv[1], reverse=True)[:n]
    ]


def _make_label(keywords: list[str]) -> str:
    """Generate a short human-readable label from keywords."""
    if not keywords:
        return "General"
    # Capitalise and join the top 3 keywords
    top = [kw.capitalize() for kw in keywords[:3]]
    return " / ".join(top)


def cluster_items(
    items: list[ContentItem],
    max_clusters: int = 8,
    min_cluster_size: int = 2,
    similarity_threshold: float = 0.15,
) -> list[TopicCluster]:
    """Group content items by topic similarity using TF-IDF.

    Uses a greedy agglomerative approach: repeatedly merge the most
    similar pair of clusters until the similarity drops below the
    threshold or only ``max_clusters`` remain.

    Items that end up in clusters smaller than ``min_cluster_size``
    are collected into an "Other" catch-all cluster.

    Args:
        items: Content items to cluster.
        max_clusters: Maximum number of topic clusters to produce.
        min_cluster_size: Minimum items per cluster (smaller ones
            get merged into "Other").
        similarity_threshold: Minimum cosine similarity for merging.

    Returns:
        List of ``TopicCluster`` instances, sorted by size descending.
    """
    if not items:
        return []

    # 1. Tokenise all items
    docs = [_tokenize(_item_text(item)) for item in items]

    # 2. Build TF-IDF vectors
    _vocab, vectors = _build_tfidf(docs)

    # 3. Initialise: each item is its own cluster
    #    cluster_indices[i] = list of original indices in that cluster
    cluster_indices: list[list[int]] = [[i] for i in range(len(items))]
    cluster_vectors: list[dict[str, float]] = [dict(v) for v in vectors]

    # 4. Greedy agglomerative merging
    while len(cluster_indices) > 1:
        best_sim = -1.0
        best_i = -1
        best_j = -1

        for i in range(len(cluster_indices)):
            for j in range(i + 1, len(cluster_indices)):
                sim = _cosine_similarity(cluster_vectors[i], cluster_vectors[j])
                if sim > best_sim:
                    best_sim = sim
                    best_i = i
                    best_j = j

        # Stop if the best pair isn't similar enough
        if best_sim < similarity_threshold:
            break

        # Stop if we've reached max_clusters and similarity is marginal
        if len(cluster_indices) <= max_clusters and best_sim < similarity_threshold:
            break

        # Merge j into i
        cluster_indices[best_i].extend(cluster_indices[best_j])
        cluster_vectors[best_i] = _merge_vectors(
            cluster_vectors[best_i], cluster_vectors[best_j]
        )

        # Remove j
        cluster_indices.pop(best_j)
        cluster_vectors.pop(best_j)

    # 5. Build TopicCluster objects; collect small clusters into "Other"
    result: list[TopicCluster] = []
    other_items: list[ContentItem] = []

    for idx_list, vec in zip(cluster_indices, cluster_vectors, strict=True):
        cluster_items_list = [items[i] for i in idx_list]
        if len(cluster_items_list) < min_cluster_size:
            other_items.extend(cluster_items_list)
        else:
            keywords = _top_keywords(vec)
            result.append(
                TopicCluster(
                    label=_make_label(keywords),
                    items=cluster_items_list,
                    keywords=keywords,
                )
            )

    # Add "Other" cluster if there are leftover items
    if other_items:
        result.append(
            TopicCluster(
                label="Other",
                items=other_items,
                keywords=[],
            )
        )

    # Sort by cluster size descending (Other goes last if tied)
    result.sort(key=lambda c: (-len(c.items), c.label == "Other"))

    return result


# ── rendering ────────────────────────────────────────────────────────

def render_clustered_context(
    clusters: list[TopicCluster],
    max_items_per_cluster: int = 8,
) -> str:
    """Render clusters into a formatted string for the LLM prompt.

    Each cluster is rendered as a section with a heading, followed by
    the items within it.  Items are capped at ``max_items_per_cluster``
    per cluster to keep the prompt within context limits.

    Args:
        clusters: Topic clusters to render.
        max_items_per_cluster: Maximum items to include per cluster.

    Returns:
        Formatted string organised by topic.
    """
    if not clusters:
        return ""

    sections: list[str] = []

    for cluster in clusters:
        lines: list[str] = []
        keyword_str = ", ".join(cluster.keywords) if cluster.keywords else "mixed topics"
        lines.append(f"## {cluster.label}")
        lines.append(f"*Keywords: {keyword_str}*")
        lines.append("")

        display_items = cluster.items[:max_items_per_cluster]
        for item in display_items:
            title = item.title or "(untitled)"
            lines.append(f"### {title}")

            meta_parts: list[str] = []
            if item.site_name:
                meta_parts.append(item.site_name)
            if item.author:
                meta_parts.append(f"by {item.author}")
            if item.url:
                meta_parts.append(item.url)
            if meta_parts:
                lines.append(f"*{' | '.join(meta_parts)}*")

            body = item.excerpt or item.body or ""
            if len(body) > 1500:
                body = body[:1500] + "\n\n[... truncated]"
            if body:
                lines.append("")
                lines.append(body)

            lines.append("")

        remaining = len(cluster.items) - len(display_items)
        if remaining > 0:
            lines.append(f"*... and {remaining} more item(s) in this topic.*")
            lines.append("")

        sections.append("\n".join(lines))

    return "\n---\n\n".join(sections)
