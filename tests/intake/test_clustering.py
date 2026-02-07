"""Tests for intake topic clustering."""

from __future__ import annotations

from distill.intake.clustering import (
    TopicCluster,
    _cosine_similarity,
    _item_text,
    _tokenize,
    cluster_items,
    render_clustered_context,
)
from distill.intake.models import ContentItem, ContentSource

# ── helpers ──────────────────────────────────────────────────────────


def _item(
    title: str,
    excerpt: str = "",
    body: str = "",
    tags: list[str] | None = None,
    **kw,
) -> ContentItem:
    """Shorthand factory for test ContentItems."""
    return ContentItem(
        id=title[:8],
        title=title,
        excerpt=excerpt,
        body=body,
        word_count=len((excerpt or body).split()),
        source=ContentSource.RSS,
        tags=tags or [],
        **kw,
    )


# ── TopicCluster model ──────────────────────────────────────────────


class TestTopicClusterModel:
    def test_basic_construction(self):
        item = _item("Test")
        cluster = TopicCluster(label="AI", items=[item], keywords=["ai", "model"])
        assert cluster.label == "AI"
        assert len(cluster.items) == 1
        assert cluster.keywords == ["ai", "model"]

    def test_defaults(self):
        cluster = TopicCluster(label="X", items=[])
        assert cluster.keywords == []
        assert cluster.items == []


# ── tokenisation ────────────────────────────────────────────────────


class TestTokenize:
    def test_lowercases_and_strips_punctuation(self):
        tokens = _tokenize("Hello, World! Python's great.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "pythons" in tokens

    def test_removes_stopwords(self):
        tokens = _tokenize("the quick brown fox and the lazy dog")
        assert "the" not in tokens
        assert "and" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens

    def test_drops_short_tokens(self):
        tokens = _tokenize("I a am an it by")
        # All are either stopwords or single-char
        assert tokens == []

    def test_keeps_two_char_non_stopwords(self):
        tokens = _tokenize("ox ml db")
        assert "ox" in tokens
        assert "ml" in tokens

    def test_drops_digits(self):
        tokens = _tokenize("python 3 version 42 release")
        assert "3" not in tokens
        assert "42" not in tokens
        assert "python" in tokens


# ── item_text ────────────────────────────────────────────────────────


class TestItemText:
    def test_title_and_excerpt(self):
        item = _item("ML Models", excerpt="Neural networks are powerful")
        text = _item_text(item)
        assert "ML Models" in text
        assert "Neural networks are powerful" in text

    def test_falls_back_to_body(self):
        item = _item("Title", body="This is the body text")
        text = _item_text(item)
        assert "body text" in text

    def test_includes_tags(self):
        item = _item("Post", tags=["python", "rust"])
        text = _item_text(item)
        assert "python" in text
        assert "rust" in text


# ── cosine similarity ───────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = {"a": 1.0, "b": 2.0}
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = {"x": 1.0}
        b = {"y": 1.0}
        assert _cosine_similarity(a, b) == 0.0

    def test_empty_vectors(self):
        assert _cosine_similarity({}, {}) == 0.0
        assert _cosine_similarity({"a": 1.0}, {}) == 0.0


# ── cluster_items ────────────────────────────────────────────────────


class TestClusterItems:
    def test_empty_input(self):
        result = cluster_items([])
        assert result == []

    def test_single_item_goes_to_other(self):
        items = [_item("Solo Article", excerpt="Only one article here")]
        result = cluster_items(items, min_cluster_size=2)
        assert len(result) == 1
        assert result[0].label == "Other"
        assert len(result[0].items) == 1

    def test_groups_related_articles(self):
        ai_items = [
            _item(
                "Deep Learning Advances",
                excerpt="Neural networks transformers deep learning models training",
            ),
            _item(
                "GPT-5 Released",
                excerpt="Language models neural network architecture transformers training",
            ),
            _item(
                "AI Safety Research",
                excerpt="Alignment neural network models safety deep learning training",
            ),
        ]
        web_items = [
            _item(
                "React 20 Features",
                excerpt="Frontend javascript components react hooks rendering browser",
            ),
            _item(
                "CSS Grid Tips",
                excerpt="Frontend web design css grid layout styling browser",
            ),
            _item(
                "Next.js Performance",
                excerpt="Frontend javascript server rendering react framework browser",
            ),
        ]
        result = cluster_items(
            ai_items + web_items,
            max_clusters=8,
            min_cluster_size=2,
            similarity_threshold=0.05,
        )

        # We expect at least 2 distinct clusters (AI + web dev)
        non_other = [c for c in result if c.label != "Other"]
        assert len(non_other) >= 2

        # Verify AI items are together and web items are together
        for cluster in non_other:
            titles = {item.title for item in cluster.items}
            ai_titles = {"Deep Learning Advances", "GPT-5 Released", "AI Safety Research"}
            web_titles = {"React 20 Features", "CSS Grid Tips", "Next.js Performance"}
            # A cluster should not mix AI and web topics
            has_ai = bool(titles & ai_titles)
            has_web = bool(titles & web_titles)
            assert not (has_ai and has_web), (
                f"Cluster '{cluster.label}' mixes AI and web items: {titles}"
            )

    def test_max_clusters_limit(self):
        # Create many distinct single-topic items that still merge
        items = [
            _item(f"Topic {i}", excerpt=f"keyword{i} content article text")
            for i in range(20)
        ]
        result = cluster_items(items, max_clusters=3, min_cluster_size=1)
        # Should not exceed max_clusters + possible Other
        assert len(result) <= 4  # 3 clusters + possibly "Other"

    def test_min_cluster_size_filtering(self):
        # Two related items + one unrelated
        items = [
            _item("Rust Memory", excerpt="rust borrow checker ownership memory safety"),
            _item("Rust Async", excerpt="rust async await tokio futures memory safety"),
            _item("Cooking Pasta", excerpt="italian pasta recipe tomato basil"),
        ]
        result = cluster_items(items, min_cluster_size=2, similarity_threshold=0.05)

        # The cooking item should end up in "Other"
        other = [c for c in result if c.label == "Other"]
        if other:
            other_titles = {item.title for item in other[0].items}
            assert "Cooking Pasta" in other_titles

    def test_all_identical_items_cluster_together(self):
        items = [
            _item(f"Python Tips {i}", excerpt="python programming language tips tricks")
            for i in range(4)
        ]
        result = cluster_items(items, min_cluster_size=2, similarity_threshold=0.05)
        non_other = [c for c in result if c.label != "Other"]
        # All should end up in one cluster
        assert len(non_other) == 1
        assert len(non_other[0].items) == 4

    def test_cluster_has_keywords(self):
        items = [
            _item("Python Guide", excerpt="python programming language tutorial"),
            _item("Python Tips", excerpt="python programming best practices tutorial"),
        ]
        result = cluster_items(items, min_cluster_size=2, similarity_threshold=0.05)
        non_other = [c for c in result if c.label != "Other"]
        assert len(non_other) >= 1
        cluster = non_other[0]
        assert len(cluster.keywords) > 0
        # "python" should be a top keyword
        assert "python" in cluster.keywords

    def test_cluster_has_label(self):
        items = [
            _item("ML Overview", excerpt="machine learning algorithms models training"),
            _item("ML Deep Dive", excerpt="machine learning neural networks training"),
        ]
        result = cluster_items(items, min_cluster_size=2, similarity_threshold=0.05)
        non_other = [c for c in result if c.label != "Other"]
        assert len(non_other) >= 1
        assert non_other[0].label != ""
        assert non_other[0].label != "Other"


# ── render_clustered_context ─────────────────────────────────────────


class TestRenderClusteredContext:
    def test_empty(self):
        assert render_clustered_context([]) == ""

    def test_basic_format(self):
        cluster = TopicCluster(
            label="AI Research",
            items=[
                _item("GPT Paper", excerpt="About large language models"),
                _item("RL Study", excerpt="Reinforcement learning advances"),
            ],
            keywords=["gpt", "language", "models"],
        )
        output = render_clustered_context([cluster])
        assert "## AI Research" in output
        assert "Keywords: gpt, language, models" in output
        assert "### GPT Paper" in output
        assert "### RL Study" in output

    def test_max_items_per_cluster(self):
        items = [_item(f"Item {i}", excerpt=f"Content {i}") for i in range(10)]
        cluster = TopicCluster(label="Big", items=items, keywords=["test"])
        output = render_clustered_context([cluster], max_items_per_cluster=3)
        assert "### Item 0" in output
        assert "### Item 2" in output
        assert "### Item 3" not in output
        assert "7 more item(s)" in output

    def test_multiple_clusters_separated(self):
        c1 = TopicCluster(
            label="Topic A",
            items=[_item("A1", excerpt="alpha")],
            keywords=["alpha"],
        )
        c2 = TopicCluster(
            label="Topic B",
            items=[_item("B1", excerpt="beta")],
            keywords=["beta"],
        )
        output = render_clustered_context([c1, c2])
        assert "## Topic A" in output
        assert "## Topic B" in output
        assert "---" in output  # separator between clusters

    def test_other_cluster_shows_mixed_topics(self):
        cluster = TopicCluster(label="Other", items=[_item("Misc")], keywords=[])
        output = render_clustered_context([cluster])
        assert "mixed topics" in output

    def test_truncates_long_body(self):
        long_text = "word " * 500  # 2500 chars
        item = _item("Long", excerpt=long_text)
        cluster = TopicCluster(label="Test", items=[item], keywords=["test"])
        output = render_clustered_context([cluster])
        assert "[... truncated]" in output

    def test_includes_metadata(self):
        item = _item(
            "Article",
            excerpt="content",
            site_name="TechBlog",
            author="Jane Doe",
            url="https://example.com/article",
        )
        cluster = TopicCluster(label="Test", items=[item], keywords=["test"])
        output = render_clustered_context([cluster])
        assert "TechBlog" in output
        assert "Jane Doe" in output
        assert "https://example.com/article" in output
