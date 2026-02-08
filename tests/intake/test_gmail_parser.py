"""Tests for the Gmail intake parser."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.config import GmailIntakeConfig, IntakeConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.gmail import (
    GmailParser,
    _decode_body,
    _domain_from_email,
    _parse_email_date,
    _strip_html,
)


@pytest.fixture(autouse=True)
def _enable_gmail_api():
    """Ensure _HAS_GMAIL_API is True for all tests (lib not installed in dev)."""
    with patch("distill.intake.parsers.gmail._HAS_GMAIL_API", True):
        yield


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def gmail_config() -> IntakeConfig:
    return IntakeConfig(
        gmail=GmailIntakeConfig(
            credentials_file="/tmp/creds.json",
            token_file="/tmp/token.json",
        ),
    )


@pytest.fixture()
def unconfigured_config() -> IntakeConfig:
    return IntakeConfig()


@pytest.fixture()
def parser(gmail_config: IntakeConfig) -> GmailParser:
    return GmailParser(config=gmail_config)


def _encode_body(text: str) -> str:
    """Encode text as base64url for Gmail API mock."""
    return base64.urlsafe_b64encode(text.encode()).decode()


def _make_message(
    msg_id: str = "msg001",
    subject: str = "Test Subject",
    from_header: str = "Sender Name <sender@example.com>",
    date_header: str = "Fri, 07 Feb 2026 12:00:00 +0000",
    body_text: str = "Plain text body",
    body_html: str = "",
    list_unsubscribe: str = "",
    multipart: bool = False,
) -> dict:
    """Build a mock Gmail message response."""
    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": from_header},
        {"name": "Date", "value": date_header},
    ]
    if list_unsubscribe:
        headers.append({"name": "List-Unsubscribe", "value": list_unsubscribe})

    if multipart or body_html:
        parts = []
        if body_text:
            parts.append({
                "mimeType": "text/plain",
                "body": {"data": _encode_body(body_text)},
            })
        if body_html:
            parts.append({
                "mimeType": "text/html",
                "body": {"data": _encode_body(body_html)},
            })
        payload = {
            "mimeType": "multipart/alternative",
            "headers": headers,
            "parts": parts,
        }
    else:
        payload = {
            "mimeType": "text/plain",
            "headers": headers,
            "body": {"data": _encode_body(body_text)},
        }

    return {"id": msg_id, "payload": payload}


def _mock_service(messages: list[dict]) -> MagicMock:
    """Build a mock Gmail service."""
    service = MagicMock()

    # messages().list()
    msg_stubs = [{"id": m["id"]} for m in messages]
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": msg_stubs,
    }

    # messages().get() - return the full message by ID
    def get_message(**kwargs):
        msg_id = kwargs.get("id", "")
        for m in messages:
            if m["id"] == msg_id:
                result = MagicMock()
                result.execute.return_value = m
                return result
        result = MagicMock()
        result.execute.side_effect = Exception(f"Message {msg_id} not found")
        return result

    service.users.return_value.messages.return_value.get.side_effect = get_message

    return service


# ── Basic properties ─────────────────────────────────────────────────


class TestGmailParserProperties:
    def test_source_is_gmail(self, parser: GmailParser) -> None:
        assert parser.source == ContentSource.GMAIL

    def test_is_configured_with_creds(self, gmail_config: IntakeConfig) -> None:
        p = GmailParser(config=gmail_config)
        assert p.is_configured is True

    def test_not_configured_by_default(self, unconfigured_config: IntakeConfig) -> None:
        p = GmailParser(config=unconfigured_config)
        assert p.is_configured is False


# ── Missing dependency ───────────────────────────────────────────────


class TestGmailMissingDependency:
    @patch("distill.intake.parsers.gmail._HAS_GMAIL_API", False)
    def test_parse_returns_empty_when_api_not_installed(
        self, parser: GmailParser
    ) -> None:
        result = parser.parse()
        assert result == []


# ── Message listing and query ────────────────────────────────────────


class TestGmailMessageListing:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_query_includes_date_filter(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        service = _mock_service([])
        mock_build.return_value = service

        since = datetime(2026, 2, 1, tzinfo=timezone.utc)
        GmailParser(config=gmail_config).parse(since=since)

        call_kwargs = (
            service.users.return_value.messages.return_value.list.call_args
        )
        query = call_kwargs[1]["q"]
        assert "after:" in query
        assert str(int(since.timestamp())) in query

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_default_query_used(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        service = _mock_service([])
        mock_build.return_value = service

        GmailParser(config=gmail_config).parse()

        call_kwargs = (
            service.users.return_value.messages.return_value.list.call_args
        )
        query = call_kwargs[1]["q"]
        assert "category:promotions OR label:newsletters" in query


# ── Header extraction ────────────────────────────────────────────────


class TestGmailHeaderExtraction:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_subject_extracted(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(subject="Weekly Newsletter")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].title == "Weekly Newsletter"

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_from_header_parsed_to_author(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(from_header="John Doe <john@example.com>")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].author == "John Doe"

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_from_email_only_as_author(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(from_header="plain@example.com")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].author == "plain@example.com"

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_site_name_from_email_domain(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(from_header="News <news@techblog.io>")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].site_name == "techblog.io"

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_date_header_parsed(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(date_header="Sat, 01 Feb 2026 10:30:00 +0000")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].published_at is not None
        assert items[0].published_at.year == 2026
        assert items[0].published_at.month == 2


# ── MIME body extraction ─────────────────────────────────────────────


class TestGmailBodyExtraction:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_plain_text_body(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(body_text="Hello from the newsletter")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].body == "Hello from the newsletter"

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_html_body_stripped(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(
            body_text="",
            body_html="<h1>Title</h1><p>Content here</p>",
            multipart=True,
        )]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert "Content here" in items[0].body
        assert "<" not in items[0].body

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_plain_text_preferred_over_html(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(
            body_text="Plain version",
            body_html="<p>HTML version</p>",
            multipart=True,
        )]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].body == "Plain version"


# ── Newsletter detection ─────────────────────────────────────────────


class TestGmailNewsletterDetection:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_newsletter_detected_via_list_unsubscribe(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(
            list_unsubscribe="<https://example.com/unsub>",
        )]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].content_type == ContentType.NEWSLETTER

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_article_type_without_unsubscribe(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(list_unsubscribe="")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].content_type == ContentType.ARTICLE


# ── ID generation ────────────────────────────────────────────────────


class TestGmailIdGeneration:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_stable_id_from_message_id(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(msg_id="stable_msg")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        expected_id = hashlib.sha256(b"gmail-stable_msg").hexdigest()[:16]
        assert items[0].id == expected_id

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_source_id_is_message_id(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(msg_id="src_id_123")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].source_id == "src_id_123"


# ── Max items and pagination ────────────────────────────────────────


class TestGmailMaxItems:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_max_items_per_source(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        config = IntakeConfig(
            gmail=GmailIntakeConfig(credentials_file="/tmp/c.json"),
            max_items_per_source=2,
        )
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(msg_id=f"m{i}") for i in range(5)]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert len(items) == 2


class TestGmailPagination:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_pagination_with_next_page_token(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()

        # Build a service that returns two pages
        service = MagicMock()
        list_mock = service.users.return_value.messages.return_value.list

        page1_response = MagicMock()
        page1_response.execute.return_value = {
            "messages": [{"id": "m1"}],
            "nextPageToken": "page2token",
        }
        page2_response = MagicMock()
        page2_response.execute.return_value = {
            "messages": [{"id": "m2"}],
        }
        list_mock.side_effect = [page1_response, page2_response]

        # Mock message fetches
        msg1 = _make_message(msg_id="m1", subject="First")
        msg2 = _make_message(msg_id="m2", subject="Second")

        def get_message(**kwargs):
            msg_id = kwargs.get("id", "")
            msg = msg1 if msg_id == "m1" else msg2
            result = MagicMock()
            result.execute.return_value = msg
            return result

        service.users.return_value.messages.return_value.get.side_effect = get_message
        mock_build.return_value = service

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert len(items) == 2
        assert {it.title for it in items} == {"First", "Second"}


# ── Edge cases ───────────────────────────────────────────────────────


class TestGmailEdgeCases:
    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_empty_results(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_service([])

        items = GmailParser(config=gmail_config).parse()
        assert items == []

    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_returns_empty_when_creds_unavailable(
        self, mock_creds: MagicMock, gmail_config: IntakeConfig
    ) -> None:
        mock_creds.return_value = None
        with patch("distill.intake.parsers.gmail._HAS_GMAIL_API", True):
            items = GmailParser(config=gmail_config).parse()
        assert items == []

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_api_error_in_message_fetch_skips_message(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()

        service = MagicMock()
        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "bad_msg"}],
        }
        get_mock = MagicMock()
        get_mock.execute.side_effect = Exception("API error")
        service.users.return_value.messages.return_value.get.return_value = get_mock
        mock_build.return_value = service

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert len(items) == 0

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_default_since_is_30_days(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        service = _mock_service([])
        mock_build.return_value = service

        GmailParser(config=gmail_config).parse(since=None)

        call_kwargs = (
            service.users.return_value.messages.return_value.list.call_args
        )
        query = call_kwargs[1]["q"]
        assert "after:" in query

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_naive_since_gets_utc(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message()]
        mock_build.return_value = _mock_service(msgs)

        # Naive datetime treated as UTC
        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 15)
        )
        assert len(items) == 1

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_word_count_calculated(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(body_text="one two three four")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].word_count == 4

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_source_is_gmail(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message()]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].source == ContentSource.GMAIL

    @patch("distill.intake.parsers.gmail.build_service")
    @patch("distill.intake.parsers._google_auth.get_credentials")
    def test_metadata_contains_message_id(
        self,
        mock_creds: MagicMock,
        mock_build: MagicMock,
        gmail_config: IntakeConfig,
    ) -> None:
        mock_creds.return_value = MagicMock()
        msgs = [_make_message(msg_id="meta_id")]
        mock_build.return_value = _mock_service(msgs)

        items = GmailParser(config=gmail_config).parse(
            since=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        assert items[0].metadata["message_id"] == "meta_id"


# ── Utility functions ────────────────────────────────────────────────


class TestGmailUtilities:
    def test_decode_body_valid(self) -> None:
        encoded = _encode_body("hello world")
        assert _decode_body(encoded) == "hello world"

    def test_decode_body_invalid(self) -> None:
        assert _decode_body("!!!invalid!!!") == ""

    def test_strip_html_removes_tags(self) -> None:
        result = _strip_html("<p>Hello</p><br><b>world</b>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_strip_html_empty(self) -> None:
        assert _strip_html("") == ""

    def test_domain_from_email(self) -> None:
        assert _domain_from_email("user@example.com") == "example.com"

    def test_domain_from_email_no_at(self) -> None:
        assert _domain_from_email("noatsign") == ""

    def test_parse_email_date_valid(self) -> None:
        result = _parse_email_date("Sat, 01 Feb 2026 10:30:00 +0000")
        assert result is not None
        assert result.year == 2026

    def test_parse_email_date_empty(self) -> None:
        assert _parse_email_date("") is None

    def test_parse_email_date_invalid(self) -> None:
        assert _parse_email_date("not a date") is None
