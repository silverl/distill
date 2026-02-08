"""Tests for the YouTube intake parser."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.config import IntakeConfig, YouTubeIntakeConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.youtube import YouTubeParser


@pytest.fixture(autouse=True)
def _enable_youtube_api():
    """Ensure _HAS_YOUTUBE_API is True for all tests (lib not installed in dev)."""
    with patch("distill.intake.parsers.youtube._HAS_YOUTUBE_API", True):
        yield


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def api_key_config() -> IntakeConfig:
    return IntakeConfig(
        youtube=YouTubeIntakeConfig(api_key="test-api-key"),
    )


@pytest.fixture()
def oauth_config() -> IntakeConfig:
    return IntakeConfig(
        youtube=YouTubeIntakeConfig(
            credentials_file="/tmp/creds.json",
            token_file="/tmp/token.json",
        ),
    )


@pytest.fixture()
def unconfigured_config() -> IntakeConfig:
    return IntakeConfig()


@pytest.fixture()
def parser(api_key_config: IntakeConfig) -> YouTubeParser:
    return YouTubeParser(config=api_key_config)


def _make_video(
    video_id: str = "abc123",
    title: str = "Test Video",
    description: str = "A test video description",
    channel: str = "TestChannel",
    published: str = "2026-02-01T12:00:00Z",
    tags: list[str] | None = None,
) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": description,
            "channelTitle": channel,
            "publishedAt": published,
            "tags": tags or [],
        },
        "contentDetails": {"duration": "PT10M"},
    }


def _mock_service(videos: list[dict], pages: int = 1) -> MagicMock:
    """Build a mock YouTube service that returns videos across pages."""
    service = MagicMock()
    list_mock = service.videos.return_value.list

    responses = []
    per_page = max(1, len(videos) // pages) if pages > 0 else len(videos)
    for i in range(pages):
        start = i * per_page
        end = start + per_page if i < pages - 1 else len(videos)
        page_items = videos[start:end]
        next_token = f"page{i + 2}" if i < pages - 1 else None
        responses.append(
            MagicMock(
                execute=MagicMock(
                    return_value={"items": page_items, "nextPageToken": next_token}
                )
            )
        )

    list_mock.side_effect = responses
    return service


# ── Basic properties ─────────────────────────────────────────────────


class TestYouTubeParserProperties:
    def test_source_is_youtube(self, parser: YouTubeParser) -> None:
        assert parser.source == ContentSource.YOUTUBE

    def test_is_configured_with_api_key(self, api_key_config: IntakeConfig) -> None:
        p = YouTubeParser(config=api_key_config)
        assert p.is_configured is True

    def test_is_configured_with_credentials(self, oauth_config: IntakeConfig) -> None:
        p = YouTubeParser(config=oauth_config)
        assert p.is_configured is True

    def test_not_configured_by_default(self, unconfigured_config: IntakeConfig) -> None:
        p = YouTubeParser(config=unconfigured_config)
        assert p.is_configured is False


# ── Missing dependency ───────────────────────────────────────────────


class TestYouTubeMissingDependency:
    @patch("distill.intake.parsers.youtube._HAS_YOUTUBE_API", False)
    def test_parse_returns_empty_when_api_not_installed(
        self, parser: YouTubeParser
    ) -> None:
        result = parser.parse()
        assert result == []


# ── API key service ──────────────────────────────────────────────────


class TestYouTubeApiKeyService:
    @patch("distill.intake.parsers.youtube.build_service")
    def test_build_service_with_api_key(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        mock_build.return_value = _mock_service([])
        p = YouTubeParser(config=api_key_config)
        svc = p._build_service()
        mock_build.assert_called_once_with(
            "youtube", "v3", developerKey="test-api-key"
        )
        assert svc is not None


# ── OAuth service ────────────────────────────────────────────────────


class TestYouTubeOAuthService:
    @patch("distill.intake.parsers.youtube.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_build_service_with_oauth(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        oauth_config: IntakeConfig,
    ) -> None:
        fake_creds = MagicMock()
        mock_creds.return_value = fake_creds
        mock_build.return_value = MagicMock()

        p = YouTubeParser(config=oauth_config)
        svc = p._build_service()

        mock_creds.assert_called_once_with(
            credentials_file="/tmp/creds.json",
            token_file="/tmp/token.json",
            scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        )
        mock_build.assert_called_once_with("youtube", "v3", credentials=fake_creds)
        assert svc is not None

    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_build_service_returns_none_when_creds_unavailable(
        self, mock_creds: MagicMock, oauth_config: IntakeConfig
    ) -> None:
        mock_creds.return_value = None
        p = YouTubeParser(config=oauth_config)
        svc = p._build_service()
        assert svc is None


# ── Video parsing ────────────────────────────────────────────────────


class TestYouTubeVideoExtraction:
    @patch("distill.intake.parsers.youtube.build_service")
    def test_parse_returns_content_items(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video()]
        mock_build.return_value = _mock_service(videos)

        p = YouTubeParser(config=api_key_config)
        items = p.parse()
        assert len(items) == 1
        assert isinstance(items[0], ContentItem)

    @patch("distill.intake.parsers.youtube.build_service")
    def test_video_title_extracted(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(title="My Great Video")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].title == "My Great Video"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_video_url_constructed(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(video_id="xyz789")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].url == "https://www.youtube.com/watch?v=xyz789"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_channel_as_site_name(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(channel="CodeChannel")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].site_name == "CodeChannel"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_channel_as_author(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(channel="AuthorChan")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].author == "AuthorChan"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_video_tags_extracted(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(tags=["python", "tutorial"])]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].tags == ["python", "tutorial"]

    @patch("distill.intake.parsers.youtube.build_service")
    def test_content_type_is_video(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video()]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].content_type == ContentType.VIDEO

    @patch("distill.intake.parsers.youtube.build_service")
    def test_source_is_youtube(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video()]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].source == ContentSource.YOUTUBE

    @patch("distill.intake.parsers.youtube.build_service")
    def test_source_id_is_video_id(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(video_id="vid999")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].source_id == "vid999"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_stable_id_generation(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        import hashlib

        videos = [_make_video(video_id="stable1")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse()
        expected_id = hashlib.sha256(b"youtube-stable1").hexdigest()[:16]
        assert items[0].id == expected_id

    @patch("distill.intake.parsers.youtube.build_service")
    def test_description_as_body_when_no_transcript(
        self, mock_build: MagicMock
    ) -> None:
        config = IntakeConfig(
            youtube=YouTubeIntakeConfig(
                api_key="key", fetch_transcripts=False
            ),
        )
        videos = [_make_video(description="The description text")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=config).parse()
        assert items[0].body == "The description text"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_word_count_from_body(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(description="one two three four five")]
        mock_build.return_value = _mock_service(videos)

        # Disable transcripts so body = description
        api_key_config.youtube.fetch_transcripts = False
        items = YouTubeParser(config=api_key_config).parse()
        assert items[0].word_count == 5


# ── Date filtering ───────────────────────────────────────────────────


class TestYouTubeDateFiltering:
    @patch("distill.intake.parsers.youtube.build_service")
    def test_old_videos_filtered_out(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        old_date = "2020-01-01T00:00:00Z"
        videos = [_make_video(published=old_date)]
        mock_build.return_value = _mock_service(videos)

        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        items = YouTubeParser(config=api_key_config).parse(since=since)
        assert len(items) == 0

    @patch("distill.intake.parsers.youtube.build_service")
    def test_recent_videos_included(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        recent_date = "2026-02-01T00:00:00Z"
        videos = [_make_video(published=recent_date)]
        mock_build.return_value = _mock_service(videos)

        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        items = YouTubeParser(config=api_key_config).parse(since=since)
        assert len(items) == 1

    @patch("distill.intake.parsers.youtube.build_service")
    def test_default_since_is_30_days(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        # Published within last 30 days
        recent = datetime.now(tz=timezone.utc) - timedelta(days=5)
        recent_str = recent.strftime("%Y-%m-%dT%H:%M:%SZ")
        videos = [_make_video(published=recent_str)]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse(since=None)
        assert len(items) == 1

    @patch("distill.intake.parsers.youtube.build_service")
    def test_naive_since_gets_utc(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        recent = "2026-02-01T00:00:00Z"
        videos = [_make_video(published=recent)]
        mock_build.return_value = _mock_service(videos)

        # Naive datetime should be treated as UTC
        since = datetime(2026, 1, 15)
        items = YouTubeParser(config=api_key_config).parse(since=since)
        assert len(items) == 1

    @patch("distill.intake.parsers.youtube.build_service")
    def test_iso8601_date_parsing(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(published="2026-02-07T15:30:00Z")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].published_at == datetime(2026, 2, 7, 15, 30, tzinfo=timezone.utc)


# ── Pagination ───────────────────────────────────────────────────────


class TestYouTubePagination:
    @patch("distill.intake.parsers.youtube.build_service")
    def test_fetches_multiple_pages(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [
            _make_video(video_id=f"vid{i}", published="2026-02-01T00:00:00Z")
            for i in range(4)
        ]
        mock_build.return_value = _mock_service(videos, pages=2)

        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert len(items) == 4

    @patch("distill.intake.parsers.youtube.build_service")
    def test_stops_when_no_next_page(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(published="2026-02-01T00:00:00Z")]
        mock_build.return_value = _mock_service(videos, pages=1)

        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert len(items) == 1


# ── Transcript handling ──────────────────────────────────────────────


class TestYouTubeTranscripts:
    @patch("distill.intake.parsers.youtube.YouTubeTranscriptApi")
    @patch("distill.intake.parsers.youtube.build_service")
    @patch("distill.intake.parsers.youtube._HAS_TRANSCRIPT", True)
    def test_transcript_fetched_and_concatenated(
        self,
        mock_build: MagicMock,
        mock_transcript_api: MagicMock,
        api_key_config: IntakeConfig,
    ) -> None:
        api_key_config.youtube.fetch_transcripts = True
        videos = [_make_video(video_id="t1", description="desc")]
        mock_build.return_value = _mock_service(videos)
        mock_transcript_api.get_transcript.return_value = [
            {"text": "Hello"},
            {"text": "world"},
        ]

        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].body == "Hello world"
        mock_transcript_api.get_transcript.assert_called_once_with("t1")

    @patch("distill.intake.parsers.youtube.YouTubeTranscriptApi")
    @patch("distill.intake.parsers.youtube.build_service")
    @patch("distill.intake.parsers.youtube._HAS_TRANSCRIPT", True)
    def test_transcript_fallback_to_description(
        self,
        mock_build: MagicMock,
        mock_transcript_api: MagicMock,
        api_key_config: IntakeConfig,
    ) -> None:
        api_key_config.youtube.fetch_transcripts = True
        videos = [_make_video(video_id="t2", description="fallback desc")]
        mock_build.return_value = _mock_service(videos)
        mock_transcript_api.get_transcript.side_effect = Exception("Not available")

        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].body == "fallback desc"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_transcript_disabled(
        self, mock_build: MagicMock
    ) -> None:
        config = IntakeConfig(
            youtube=YouTubeIntakeConfig(
                api_key="key", fetch_transcripts=False
            ),
        )
        videos = [_make_video(description="just the desc")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].body == "just the desc"

    @patch("distill.intake.parsers.youtube.build_service")
    @patch("distill.intake.parsers.youtube._HAS_TRANSCRIPT", False)
    def test_transcript_lib_not_installed(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        api_key_config.youtube.fetch_transcripts = True
        videos = [_make_video(description="no transcript lib")]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].body == "no transcript lib"


# ── Max items limiting ───────────────────────────────────────────────


class TestYouTubeMaxItems:
    @patch("distill.intake.parsers.youtube.build_service")
    def test_max_items_per_source(
        self, mock_build: MagicMock
    ) -> None:
        config = IntakeConfig(
            youtube=YouTubeIntakeConfig(api_key="key"),
            max_items_per_source=2,
        )
        videos = [
            _make_video(video_id=f"v{i}", published="2026-02-01T00:00:00Z")
            for i in range(5)
        ]
        mock_build.return_value = _mock_service(videos)

        items = YouTubeParser(config=config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert len(items) == 2


# ── Edge cases ───────────────────────────────────────────────────────


class TestYouTubeEdgeCases:
    @patch("distill.intake.parsers.youtube.build_service")
    def test_empty_results(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        mock_build.return_value = _mock_service([])
        items = YouTubeParser(config=api_key_config).parse()
        assert items == []

    @patch("distill.intake.parsers.youtube.build_service")
    def test_video_with_no_id_skipped(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        video = _make_video()
        video["id"] = ""
        mock_build.return_value = _mock_service([video])
        items = YouTubeParser(config=api_key_config).parse()
        assert len(items) == 0

    @patch("distill.intake.parsers.youtube.build_service")
    def test_video_with_empty_tags(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(tags=[])]
        mock_build.return_value = _mock_service(videos)
        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].tags == []

    @patch("distill.intake.parsers.youtube.build_service")
    def test_video_with_none_tags(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        video = _make_video()
        video["snippet"]["tags"] = None
        mock_build.return_value = _mock_service([video])
        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].tags == []

    @patch("distill.intake.parsers.youtube.build_service")
    def test_excerpt_from_description(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        api_key_config.youtube.fetch_transcripts = False
        videos = [_make_video(description="Short desc")]
        mock_build.return_value = _mock_service(videos)
        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].excerpt == "Short desc"

    @patch("distill.intake.parsers.youtube.build_service")
    def test_metadata_contains_video_id(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        videos = [_make_video(video_id="meta1")]
        mock_build.return_value = _mock_service(videos)
        items = YouTubeParser(config=api_key_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].metadata["video_id"] == "meta1"

    def test_no_api_key_or_creds_returns_none(self) -> None:
        config = IntakeConfig(youtube=YouTubeIntakeConfig())
        p = YouTubeParser(config=config)
        with patch("distill.intake.parsers.youtube._HAS_YOUTUBE_API", True):
            svc = p._build_service()
            assert svc is None

    @patch("distill.intake.parsers.youtube.build_service")
    def test_api_error_propagates(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        service = MagicMock()
        service.videos.return_value.list.return_value.execute.side_effect = Exception(
            "API error"
        )
        mock_build.return_value = service

        with pytest.raises(Exception, match="API error"):
            YouTubeParser(config=api_key_config).parse()

    @patch("distill.intake.parsers.youtube.build_service")
    def test_published_at_none_for_invalid_date(
        self, mock_build: MagicMock, api_key_config: IntakeConfig
    ) -> None:
        video = _make_video()
        video["snippet"]["publishedAt"] = "not-a-date"
        mock_build.return_value = _mock_service([video])

        items = YouTubeParser(config=api_key_config).parse()
        assert len(items) == 1
        assert items[0].published_at is None
