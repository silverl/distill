"""Tests for intelligence module — entity extraction, classification, topic modeling."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from distill.intake.intelligence import (
    _build_classification_prompt,
    _build_entity_prompt,
    _build_topic_prompt,
    _parse_json_response,
    classify_items,
    extract_entities,
    extract_topics,
)
from distill.intake.models import ContentItem, ContentSource, ContentType


def _make_item(
    title: str = "Test Article",
    body: str = "This is about Python and AI agents.",
    source: ContentSource = ContentSource.RSS,
    tags: list[str] | None = None,
) -> ContentItem:
    return ContentItem(
        id=f"item-{hash(title) % 10000}",
        title=title,
        body=body,
        source=source,
        content_type=ContentType.ARTICLE,
        tags=tags or [],
    )


class TestParseJsonResponse:
    """Test JSON extraction from LLM responses."""

    def test_plain_json(self):
        result = _parse_json_response('[{"key": "value"}]')
        assert result == [{"key": "value"}]

    def test_json_in_code_fence(self):
        text = '```json\n[{"key": "value"}]\n```'
        result = _parse_json_response(text)
        assert result == [{"key": "value"}]

    def test_json_in_bare_fence(self):
        text = '```\n[{"key": "value"}]\n```'
        result = _parse_json_response(text)
        assert result == [{"key": "value"}]

    def test_invalid_json(self):
        result = _parse_json_response("not json at all")
        assert result is None

    def test_empty_string(self):
        result = _parse_json_response("")
        assert result is None

    def test_nested_json(self):
        data = [{"entities": {"projects": ["distill"]}}]
        result = _parse_json_response(json.dumps(data))
        assert result == data


class TestBuildPrompts:
    """Test prompt construction."""

    def test_entity_prompt_includes_items(self):
        items = [_make_item(title="Building AI Agents")]
        prompt = _build_entity_prompt(items)
        assert "Building AI Agents" in prompt
        assert "[ITEM 0]" in prompt
        assert "projects" in prompt

    def test_entity_prompt_truncates_body(self):
        long_body = "x" * 1000
        items = [_make_item(body=long_body)]
        prompt = _build_entity_prompt(items)
        # Body should be truncated to ~500 chars
        assert len(prompt) < 2000

    def test_classification_prompt_includes_items(self):
        items = [_make_item(title="Tutorial: Python Basics")]
        prompt = _build_classification_prompt(items)
        assert "Tutorial: Python Basics" in prompt
        assert "category" in prompt
        assert "sentiment" in prompt

    def test_topic_prompt_includes_titles(self):
        items = [_make_item(title="AI Agents"), _make_item(title="Testing Patterns")]
        prompt = _build_topic_prompt(items, ["AI"])
        assert "AI Agents" in prompt
        assert "Testing Patterns" in prompt
        assert "AI" in prompt  # existing topics


class TestExtractEntities:
    """Test entity extraction via mocked LLM."""

    @patch("distill.intake.intelligence._call_claude")
    def test_basic_extraction(self, mock_claude):
        mock_claude.return_value = json.dumps([
            {
                "projects": ["distill"],
                "technologies": ["python", "pgvector"],
                "people": ["Nik"],
                "concepts": ["content pipeline"],
                "organizations": ["Anthropic"],
            }
        ])

        items = [_make_item(title="Building Distill with Python")]
        result = extract_entities(items)

        assert len(result) == 1
        entities = result[0].metadata["entities"]
        assert "distill" in entities["projects"]
        assert "python" in entities["technologies"]
        assert "Anthropic" in entities["organizations"]

    @patch("distill.intake.intelligence._call_claude")
    def test_populates_topics(self, mock_claude):
        mock_claude.return_value = json.dumps([
            {
                "projects": [],
                "technologies": [],
                "people": [],
                "concepts": ["AI agents", "tool use"],
                "organizations": [],
            }
        ])

        items = [_make_item()]
        extract_entities(items)

        assert items[0].topics == ["AI agents", "tool use"]

    @patch("distill.intake.intelligence._call_claude")
    def test_preserves_existing_topics(self, mock_claude):
        mock_claude.return_value = json.dumps([
            {
                "projects": [],
                "technologies": [],
                "people": [],
                "concepts": ["new concept"],
                "organizations": [],
            }
        ])

        items = [_make_item()]
        items[0].topics = ["existing topic"]
        extract_entities(items)

        assert items[0].topics == ["existing topic"]

    @patch("distill.intake.intelligence._call_claude")
    def test_batch_processing(self, mock_claude):
        """Multiple items in a single batch."""
        mock_claude.return_value = json.dumps([
            {"projects": ["p1"], "technologies": [], "people": [], "concepts": [], "organizations": []},
            {"projects": ["p2"], "technologies": [], "people": [], "concepts": [], "organizations": []},
        ])

        items = [_make_item(title="Item 1"), _make_item(title="Item 2")]
        extract_entities(items)

        assert items[0].metadata["entities"]["projects"] == ["p1"]
        assert items[1].metadata["entities"]["projects"] == ["p2"]

    @patch("distill.intake.intelligence._call_claude")
    def test_llm_failure_graceful(self, mock_claude):
        """When LLM fails, items should not have entities but no crash."""
        mock_claude.return_value = ""

        items = [_make_item()]
        result = extract_entities(items)

        assert len(result) == 1
        assert "entities" not in result[0].metadata

    @patch("distill.intake.intelligence._call_claude")
    def test_invalid_json_graceful(self, mock_claude):
        mock_claude.return_value = "not json"

        items = [_make_item()]
        result = extract_entities(items)

        assert "entities" not in result[0].metadata

    @patch("distill.intake.intelligence._call_claude")
    def test_partial_response(self, mock_claude):
        """Response has fewer items than batch — only available items get entities."""
        mock_claude.return_value = json.dumps([
            {"projects": ["p1"], "technologies": [], "people": [], "concepts": [], "organizations": []},
        ])

        items = [_make_item(title="Item 1"), _make_item(title="Item 2")]
        extract_entities(items)

        assert "entities" in items[0].metadata
        assert "entities" not in items[1].metadata

    @patch("distill.intake.intelligence._call_claude")
    def test_large_batch_splits(self, mock_claude):
        """Items exceeding batch size are processed in multiple calls."""
        # Create 12 items (batch size is 8, so 2 calls)
        mock_claude.return_value = json.dumps([
            {"projects": [], "technologies": [], "people": [], "concepts": [], "organizations": []}
        ] * 8)

        items = [_make_item(title=f"Item {i}") for i in range(12)]
        extract_entities(items)

        assert mock_claude.call_count == 2

    @patch("distill.intake.intelligence._call_claude")
    def test_session_entities(self, mock_claude):
        """Session items get entity extraction too."""
        mock_claude.return_value = json.dumps([
            {
                "projects": ["distill"],
                "technologies": ["python"],
                "people": [],
                "concepts": ["session parsing"],
                "organizations": [],
            }
        ])

        items = [_make_item(source=ContentSource.SESSION, title="Session: Built session parser")]
        extract_entities(items)

        assert items[0].metadata["entities"]["projects"] == ["distill"]


class TestClassifyItems:
    """Test content classification via mocked LLM."""

    @patch("distill.intake.intelligence._call_claude")
    def test_basic_classification(self, mock_claude):
        mock_claude.return_value = json.dumps([
            {"category": "tutorial", "sentiment": "positive", "relevance": 4}
        ])

        items = [_make_item(title="Python Tutorial")]
        classify_items(items)

        cls = items[0].metadata["classification"]
        assert cls["category"] == "tutorial"
        assert cls["sentiment"] == "positive"
        assert cls["relevance"] == 4

    @patch("distill.intake.intelligence._call_claude")
    def test_multiple_items(self, mock_claude):
        mock_claude.return_value = json.dumps([
            {"category": "tutorial", "sentiment": "positive", "relevance": 4},
            {"category": "news", "sentiment": "neutral", "relevance": 3},
        ])

        items = [_make_item(title="Tutorial"), _make_item(title="News")]
        classify_items(items)

        assert items[0].metadata["classification"]["category"] == "tutorial"
        assert items[1].metadata["classification"]["category"] == "news"

    @patch("distill.intake.intelligence._call_claude")
    def test_llm_failure_graceful(self, mock_claude):
        mock_claude.return_value = ""
        items = [_make_item()]
        classify_items(items)
        assert "classification" not in items[0].metadata

    @patch("distill.intake.intelligence._call_claude")
    def test_session_classification(self, mock_claude):
        mock_claude.return_value = json.dumps([
            {"category": "session-log", "sentiment": "positive", "relevance": 5}
        ])

        items = [_make_item(source=ContentSource.SESSION)]
        classify_items(items)
        assert items[0].metadata["classification"]["category"] == "session-log"


class TestExtractTopics:
    """Test topic extraction across items."""

    @patch("distill.intake.intelligence._call_claude")
    def test_basic_topic_extraction(self, mock_claude):
        mock_claude.return_value = json.dumps(["AI agents", "testing", "deployment"])

        items = [_make_item(title="AI Agent Testing"), _make_item(title="Deployment Strategies")]
        topics = extract_topics(items)

        assert topics == ["AI agents", "testing", "deployment"]

    @patch("distill.intake.intelligence._call_claude")
    def test_preserves_existing_topics(self, mock_claude):
        mock_claude.return_value = json.dumps(["AI", "testing"])

        topics = extract_topics(
            [_make_item()], existing_topics=["old topic"]
        )
        assert topics == ["AI", "testing"]

    @patch("distill.intake.intelligence._call_claude")
    def test_fallback_on_failure(self, mock_claude):
        mock_claude.return_value = ""
        existing = ["topic1", "topic2"]
        topics = extract_topics([_make_item()], existing_topics=existing)
        assert topics == existing

    @patch("distill.intake.intelligence._call_claude")
    def test_fallback_on_invalid_json(self, mock_claude):
        mock_claude.return_value = "not json"
        topics = extract_topics([_make_item()], existing_topics=["existing"])
        assert topics == ["existing"]

    def test_empty_items(self):
        topics = extract_topics([], existing_topics=["existing"])
        assert topics == ["existing"]

    def test_empty_items_no_existing(self):
        topics = extract_topics([])
        assert topics == []

    @patch("distill.intake.intelligence._call_claude")
    def test_non_string_topics_rejected(self, mock_claude):
        """If LLM returns non-string items, fall back."""
        mock_claude.return_value = json.dumps([1, 2, 3])
        topics = extract_topics([_make_item()], existing_topics=["fallback"])
        assert topics == ["fallback"]
