"""Tests for the Reddit content parser."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from distill.intake.config import IntakeConfig, RedditIntakeConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.reddit import RedditParser


@pytest.fixture(autouse=True)
def _enable_praw():
    """Ensure _HAS_PRAW is True for all tests (lib not installed in dev)."""
    with patch("distill.intake.parsers.reddit._HAS_PRAW", True):
        yield


# ── Helpers ──────────────────────────────────────────────────────────


def _make_config(
    client_id: str = "test_id",
    client_secret: str = "test_secret",
    username: str = "testuser",
    password: str = "testpass",
    max_items: int = 50,
) -> IntakeConfig:
    return IntakeConfig(
        reddit=RedditIntakeConfig(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
        ),
        max_items_per_source=max_items,
    )


def _make_submission(
    *,
    id: str = "abc123",
    title: str = "Test Post",
    selftext: str = "Post body text",
    url: str = "",
    permalink: str = "/r/python/comments/abc123/test_post/",
    author: str = "testuser",
    subreddit: str = "python",
    score: int = 42,
    created_utc: float = 1700000000.0,
    is_self: bool = True,
) -> MagicMock:
    """Create a mock praw Submission."""
    mock = MagicMock()
    mock.id = id
    mock.title = title
    mock.selftext = selftext
    mock.url = url if url else f"https://reddit.com{permalink}"
    mock.permalink = permalink
    mock.author = MagicMock(__str__=lambda self: author)
    mock.subreddit = MagicMock(__str__=lambda self: subreddit)
    mock.score = score
    mock.created_utc = created_utc
    mock.is_self = is_self
    # Submissions do NOT have 'body' attribute (only comments do)
    if hasattr(mock, "body"):
        del mock.body
    # Use spec to control hasattr
    mock.configure_mock(**{"body": AttributeError})
    # Remove 'body' so hasattr returns False
    type(mock).body = PropertyMock(side_effect=AttributeError)
    return mock


def _make_comment(
    *,
    id: str = "com456",
    body: str = "Great comment!",
    permalink: str = "/r/python/comments/abc123/test_post/com456/",
    author: str = "commenter",
    subreddit: str = "python",
    score: int = 10,
    created_utc: float = 1700000000.0,
) -> MagicMock:
    """Create a mock praw Comment."""
    mock = MagicMock()
    mock.id = id
    mock.body = body
    mock.permalink = permalink
    mock.author = MagicMock(__str__=lambda self: author)
    mock.subreddit = MagicMock(__str__=lambda self: subreddit)
    mock.score = score
    mock.created_utc = created_utc
    # Comments do NOT have 'title' attribute
    del mock.title
    return mock


def _make_link_submission(
    *,
    id: str = "link789",
    title: str = "External Link",
    url: str = "https://example.com/article",
    selftext: str = "",
    permalink: str = "/r/programming/comments/link789/external_link/",
    author: str = "linkposter",
    subreddit: str = "programming",
    score: int = 100,
    created_utc: float = 1700000000.0,
) -> MagicMock:
    """Create a mock praw link Submission (not self-post)."""
    mock = _make_submission(
        id=id,
        title=title,
        selftext=selftext,
        url=url,
        permalink=permalink,
        author=author,
        subreddit=subreddit,
        score=score,
        created_utc=created_utc,
        is_self=False,
    )
    return mock


# ── Properties ───────────────────────────────────────────────────────


class TestRedditParserProperties:
    def test_source_returns_reddit(self) -> None:
        parser = RedditParser(config=_make_config())
        assert parser.source == ContentSource.REDDIT

    def test_is_configured_true(self) -> None:
        parser = RedditParser(config=_make_config())
        assert parser.is_configured is True

    def test_is_configured_false_no_client_id(self) -> None:
        parser = RedditParser(config=_make_config(client_id=""))
        assert parser.is_configured is False

    def test_is_configured_false_no_client_secret(self) -> None:
        parser = RedditParser(config=_make_config(client_secret=""))
        assert parser.is_configured is False

    def test_is_configured_false_both_empty(self) -> None:
        parser = RedditParser(config=_make_config(client_id="", client_secret=""))
        assert parser.is_configured is False


# ── praw not installed ───────────────────────────────────────────────


class TestRedditParserNoPraw:
    @patch("distill.intake.parsers.reddit._HAS_PRAW", False)
    def test_parse_returns_empty_when_praw_missing(self) -> None:
        parser = RedditParser(config=_make_config())
        result = parser.parse()
        assert result == []

    @patch("distill.intake.parsers.reddit._HAS_PRAW", False)
    def test_parse_logs_warning_when_praw_missing(self, caplog: pytest.LogCaptureFixture) -> None:
        parser = RedditParser(config=_make_config())
        with caplog.at_level("WARNING"):
            parser.parse()
        assert any("praw" in r.message.lower() for r in caplog.records)


# ── Saved submission parsing ─────────────────────────────────────────


class TestSavedSubmissions:
    @patch("distill.intake.parsers.reddit.praw")
    def test_saved_self_post(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="s1", title="My Self Post", selftext="Some text here")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        item = items[0]
        assert item.title == "My Self Post"
        assert item.body == "Some text here"
        assert item.source == ContentSource.REDDIT
        assert item.content_type == ContentType.POST
        assert item.is_starred is True

    @patch("distill.intake.parsers.reddit.praw")
    def test_saved_link_post(self, mock_praw: MagicMock) -> None:
        sub = _make_link_submission(
            id="l1",
            title="Cool Article",
            url="https://example.com/cool",
        )
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        item = items[0]
        assert item.content_type == ContentType.ARTICLE
        assert item.url == "https://example.com/cool"


# ── Upvoted submission parsing ───────────────────────────────────────


class TestUpvotedSubmissions:
    @patch("distill.intake.parsers.reddit.praw")
    def test_upvoted_items_not_starred(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="u1", title="Upvoted Post")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = []
        mock_reddit.user.me.return_value.upvoted.return_value = [sub]
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].is_starred is False


# ── Comment parsing ──────────────────────────────────────────────────


class TestCommentParsing:
    @patch("distill.intake.parsers.reddit.praw")
    def test_comment_content_type(self, mock_praw: MagicMock) -> None:
        comment = _make_comment(id="c1", body="Nice comment")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [comment]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].content_type == ContentType.COMMENT
        assert items[0].body == "Nice comment"

    @patch("distill.intake.parsers.reddit.praw")
    def test_comment_has_permalink_url(self, mock_praw: MagicMock) -> None:
        comment = _make_comment(
            id="c2",
            permalink="/r/python/comments/abc/test/c2/",
        )
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [comment]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert "reddit.com" in items[0].url


# ── Subreddit as tag ─────────────────────────────────────────────────


class TestSubredditTag:
    @patch("distill.intake.parsers.reddit.praw")
    def test_subreddit_included_as_tag(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="t1", subreddit="machinelearning")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert "machinelearning" in items[0].tags


# ── Deduplication ────────────────────────────────────────────────────


class TestDeduplication:
    @patch("distill.intake.parsers.reddit.praw")
    def test_dedup_across_saved_and_upvoted(self, mock_praw: MagicMock) -> None:
        # Same submission appears in both saved and upvoted
        sub = _make_submission(id="dup1", title="Duplicate Post")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = [sub]
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        # Should only appear once
        assert len(items) == 1

    @patch("distill.intake.parsers.reddit.praw")
    def test_saved_version_kept_over_upvoted(self, mock_praw: MagicMock) -> None:
        # Saved comes first, so it should be kept (is_starred=True)
        sub = _make_submission(id="dup2", title="Same Post")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = [sub]
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].is_starred is True


# ── Since-date filtering ─────────────────────────────────────────────


class TestSinceFiltering:
    @patch("distill.intake.parsers.reddit.praw")
    def test_filters_old_items(self, mock_praw: MagicMock) -> None:
        old_sub = _make_submission(id="old1", created_utc=1000000.0)  # 1970
        new_sub = _make_submission(id="new1", created_utc=1700000000.0)  # 2023
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [old_sub, new_sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2023, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].source_id == "new1"

    @patch("distill.intake.parsers.reddit.praw")
    def test_default_since_is_30_days(self, mock_praw: MagicMock) -> None:
        # Item from 1 day ago should be included
        recent_ts = (datetime.now(tz=timezone.utc) - timedelta(days=1)).timestamp()
        sub = _make_submission(id="r1", created_utc=recent_ts)
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=None)

        assert len(items) == 1

    @patch("distill.intake.parsers.reddit.praw")
    def test_naive_since_treated_as_utc(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="n1", created_utc=1700000000.0)
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        # Naive datetime (no tzinfo)
        items = parser.parse(since=datetime(2020, 1, 1))

        assert len(items) == 1


# ── created_utc conversion ───────────────────────────────────────────


class TestTimestampConversion:
    @patch("distill.intake.parsers.reddit.praw")
    def test_created_utc_to_datetime(self, mock_praw: MagicMock) -> None:
        ts = 1700000000.0  # 2023-11-14T22:13:20 UTC
        sub = _make_submission(id="ts1", created_utc=ts)
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].published_at is not None
        assert items[0].published_at.tzinfo == timezone.utc
        assert items[0].published_at.year == 2023


# ── max_items_per_source ─────────────────────────────────────────────


class TestMaxItems:
    @patch("distill.intake.parsers.reddit.praw")
    def test_limits_to_max_items(self, mock_praw: MagicMock) -> None:
        subs = [
            _make_submission(id=f"m{i}", created_utc=1700000000.0 + i)
            for i in range(10)
        ]
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = subs
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config(max_items=3))
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) <= 3

    @patch("distill.intake.parsers.reddit.praw")
    def test_limit_passed_to_praw(self, mock_praw: MagicMock) -> None:
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = []
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config(max_items=25))
        parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        mock_reddit.user.me.return_value.saved.assert_called_once_with(limit=25)
        mock_reddit.user.me.return_value.upvoted.assert_called_once_with(limit=25)


# ── Author extraction ────────────────────────────────────────────────


class TestAuthorExtraction:
    @patch("distill.intake.parsers.reddit.praw")
    def test_author_extracted(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="a1", author="cooldev")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].author == "cooldev"

    @patch("distill.intake.parsers.reddit.praw")
    def test_deleted_author_handled(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="a2")
        sub.author = None  # deleted user
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].author == ""


# ── Score in metadata ────────────────────────────────────────────────


class TestScoreMetadata:
    @patch("distill.intake.parsers.reddit.praw")
    def test_score_in_metadata(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="sc1", score=999)
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].metadata["score"] == 999


# ── Empty results ────────────────────────────────────────────────────


class TestEmptyResults:
    @patch("distill.intake.parsers.reddit.praw")
    def test_empty_saved_and_upvoted(self, mock_praw: MagicMock) -> None:
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = []
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items == []

    def test_unconfigured_returns_empty(self) -> None:
        parser = RedditParser(config=_make_config(client_id="", client_secret=""))
        # Even with praw available, unconfigured should skip
        items = parser.parse()
        assert items == []


# ── Stable ID generation ─────────────────────────────────────────────


class TestStableIds:
    @patch("distill.intake.parsers.reddit.praw")
    def test_id_is_sha256_prefix(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="idtest")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        expected = hashlib.sha256(b"reddit-idtest").hexdigest()[:16]
        assert items[0].id == expected

    @patch("distill.intake.parsers.reddit.praw")
    def test_id_is_deterministic(self, mock_praw: MagicMock) -> None:
        sub = _make_submission(id="det1")
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = [sub]
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        items1 = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        mock_reddit.user.me.return_value.saved.return_value = [sub]
        items2 = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items1[0].id == items2[0].id


# ── Reddit client construction ───────────────────────────────────────


class TestRedditClientConstruction:
    @patch("distill.intake.parsers.reddit.praw")
    def test_user_agent(self, mock_praw: MagicMock) -> None:
        mock_reddit = MagicMock()
        mock_reddit.user.me.return_value.saved.return_value = []
        mock_reddit.user.me.return_value.upvoted.return_value = []
        mock_praw.Reddit.return_value = mock_reddit

        parser = RedditParser(config=_make_config())
        parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        mock_praw.Reddit.assert_called_once_with(
            client_id="test_id",
            client_secret="test_secret",
            username="testuser",
            password="testpass",
            user_agent="distill-intake/1.0",
        )
