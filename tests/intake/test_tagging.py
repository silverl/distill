"""Tests for intake keyword extraction and tag enrichment."""

from __future__ import annotations

from distill.intake.models import ContentItem, ContentSource
from distill.intake.tagging import STOPWORDS, extract_tags, enrich_tags


def _item(
    title: str = "Untitled",
    body: str = "",
    tags: list[str] | None = None,
    **kw,
) -> ContentItem:
    """Helper to build a minimal ContentItem."""
    return ContentItem(
        id=title[:8],
        title=title,
        body=body,
        source=ContentSource.RSS,
        tags=tags if tags is not None else [],
        **kw,
    )


# ── extract_tags ──────────────────────────────────────────────────────


class TestExtractTagsBasic:
    """Core behavior of extract_tags."""

    def test_typical_tech_blog(self):
        title = "Building REST APIs with Python and FastAPI"
        body = (
            "FastAPI is a modern Python web framework for building APIs. "
            "It leverages Python type hints and async support to deliver "
            "high performance. FastAPI integrates well with Pydantic for "
            "data validation and SQLAlchemy for database access."
        )
        tags = extract_tags(title, body)
        assert len(tags) <= 5
        # "fastapi" and "python" should be top tags given title + body frequency
        assert "fastapi" in tags
        assert "python" in tags

    def test_returns_lowercase(self):
        tags = extract_tags("Kubernetes Deployment Strategies", "Kubernetes pods rollout.")
        for tag in tags:
            assert tag == tag.lower(), f"Tag {tag!r} is not lowercase"

    def test_strips_punctuation(self):
        tags = extract_tags("Hello, World!", "world; hello... world")
        for tag in tags:
            assert all(c not in tag for c in ",.;!?"), f"Tag {tag!r} has punctuation"

    def test_empty_input(self):
        assert extract_tags("", "") == []

    def test_empty_title_with_body(self):
        tags = extract_tags("", "python python python framework framework")
        assert len(tags) > 0
        assert tags[0] == "python"

    def test_empty_body_with_title(self):
        tags = extract_tags("Machine Learning Transformers", "")
        assert len(tags) > 0
        assert "machine" in tags or "learning" in tags or "transformers" in tags


class TestExtractTagsFiltering:
    """Stopword and noise filtering."""

    def test_no_stopwords_returned(self):
        body = (
            "The quick brown fox jumps over the lazy dog and then "
            "the fox jumps again over another lazy dog because the "
            "fox really likes jumping over lazy dogs very much."
        )
        tags = extract_tags("A Simple Story About Animals", body)
        for tag in tags:
            assert tag not in STOPWORDS, f"Stopword {tag!r} should not be a tag"

    def test_short_words_excluded(self):
        tags = extract_tags("AI ML NLP", "AI ML NLP tools")
        # "ai", "ml", "nlp" are all < 3 chars after lowercasing (2 chars)
        # Only "tools" should survive
        for tag in tags:
            assert len(tag) >= 3, f"Tag {tag!r} is too short"

    def test_pure_numbers_excluded(self):
        tags = extract_tags("2024 Predictions", "100 200 300 predictions trends")
        for tag in tags:
            assert not tag.isdigit(), f"Numeric tag {tag!r} should be excluded"


class TestExtractTagsMaxTags:
    """Tag count limits."""

    def test_max_tags_default(self):
        body = " ".join(f"word{i} " * (10 - i) for i in range(20))
        tags = extract_tags("Title Here", body)
        assert len(tags) <= 5

    def test_max_tags_custom(self):
        body = " ".join(f"keyword{i} " * (10 - i) for i in range(20))
        tags = extract_tags("Title Here", body, max_tags=3)
        assert len(tags) <= 3

    def test_max_tags_one(self):
        tags = extract_tags(
            "Python", "python python python django django", max_tags=1
        )
        assert len(tags) == 1
        assert tags[0] == "python"


class TestExtractTagsWeighting:
    """Title words should be weighted higher than body words."""

    def test_title_word_ranked_higher(self):
        # "rust" appears once in the title, "javascript" appears 3x in the body.
        # With title weight of 3, "rust" should score 3 (1*3) vs "javascript" 3 (3*1).
        # But to make the test reliable, put "rust" in the body once too: 3+1=4.
        tags = extract_tags(
            "Rust Programming Guide",
            "rust systems programming. javascript javascript javascript.",
        )
        # "rust" should appear before "javascript"
        assert "rust" in tags
        rust_idx = tags.index("rust")
        if "javascript" in tags:
            js_idx = tags.index("javascript")
            assert rust_idx < js_idx, (
                f"Title word 'rust' (idx={rust_idx}) should rank above "
                f"body-only word 'javascript' (idx={js_idx})"
            )


# ── enrich_tags ───────────────────────────────────────────────────────


class TestEnrichTags:
    """Enrichment of ContentItem lists."""

    def test_populates_empty_tags(self):
        items = [
            _item(
                title="Deep Learning with PyTorch",
                body="PyTorch is a deep learning framework for neural networks.",
            ),
        ]
        assert items[0].tags == []
        enrich_tags(items)
        assert len(items[0].tags) > 0
        assert "pytorch" in items[0].tags

    def test_skips_items_with_existing_tags(self):
        items = [
            _item(
                title="Deep Learning with PyTorch",
                body="PyTorch neural networks.",
                tags=["manual-tag"],
            ),
        ]
        enrich_tags(items)
        assert items[0].tags == ["manual-tag"]

    def test_mixed_items(self):
        items = [
            _item(title="Kubernetes Scaling", body="autoscaler pods", tags=["k8s"]),
            _item(title="Docker Containers", body="docker compose containers orchestration"),
        ]
        enrich_tags(items)
        # First item retains original tags
        assert items[0].tags == ["k8s"]
        # Second item gets auto-generated tags
        assert len(items[1].tags) > 0

    def test_returns_same_list(self):
        items = [_item(title="Test", body="testing framework")]
        result = enrich_tags(items)
        assert result is items

    def test_empty_list(self):
        result = enrich_tags([])
        assert result == []

    def test_item_with_no_title_or_body(self):
        items = [_item(title="", body="")]
        enrich_tags(items)
        assert items[0].tags == []


class TestExtractTagsEdgeCases:
    """Edge cases for extract_tags."""

    def test_all_stopwords_returns_empty(self):
        """Input with text that is entirely stopwords/short words."""
        tags = extract_tags("The And But", "is am are was the a an")
        assert tags == []

    def test_unicode_whitespace_handled(self):
        """Non-breaking spaces and other unicode whitespace are normalized."""
        tags = extract_tags("Python\u00a0Framework", "django\u2003framework")
        assert len(tags) > 0
        assert "python" in tags or "framework" in tags or "django" in tags
