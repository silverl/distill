"""Gmail newsletters and promotions parser."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_DAYS = 30
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

try:
    from googleapiclient.discovery import build as build_service

    _HAS_GMAIL_API = True
except ImportError:
    build_service = None  # type: ignore[assignment]
    _HAS_GMAIL_API = False


class GmailParser(ContentParser):
    """Parses Gmail newsletters and promotions into ContentItem objects."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.GMAIL

    @property
    def is_configured(self) -> bool:
        return self._config.gmail.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        if not _HAS_GMAIL_API:
            logger.warning("google-api-python-client not installed, skipping Gmail")
            return []

        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=_DEFAULT_MAX_AGE_DAYS)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        service = self._build_service()
        if service is None:
            return []

        items = self._fetch_messages(service, since)

        max_items = self._config.max_items_per_source
        if len(items) > max_items:
            items = items[:max_items]

        return items

    def _build_service(self) -> object:
        """Build the Gmail API service via OAuth."""
        from distill.intake.parsers import _google_auth

        creds = _google_auth.get_credentials(
            credentials_file=self._config.gmail.credentials_file,
            token_file=self._config.gmail.token_file or "",
            scopes=_GMAIL_SCOPES,
        )
        if creds is None:
            logger.warning("Gmail OAuth credentials unavailable")
            return None

        return build_service("gmail", "v1", credentials=creds)

    def _fetch_messages(self, service: object, since: datetime) -> list[ContentItem]:
        since_epoch = int(since.timestamp())
        query = self._config.gmail.query
        query = f"{query} after:{since_epoch}"

        items: list[ContentItem] = []
        page_token: str | None = None

        while True:
            request = (
                service.users()
                .messages()
                .list(  # type: ignore[union-attr]
                    userId="me",
                    q=query,
                    maxResults=50,
                    pageToken=page_token,
                )
            )
            response = request.execute()

            for msg_stub in response.get("messages", []):
                msg_id = msg_stub.get("id", "")
                if not msg_id:
                    continue

                try:
                    item = self._fetch_and_parse_message(service, msg_id)
                    if item is not None:
                        items.append(item)
                except Exception:
                    logger.warning("Failed to parse Gmail message %s", msg_id, exc_info=True)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return items

    def _fetch_and_parse_message(self, service: object, msg_id: str) -> ContentItem | None:
        request = (
            service.users()
            .messages()
            .get(  # type: ignore[union-attr]
                userId="me", id=msg_id, format="full"
            )
        )
        msg = request.execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        subject = headers.get("Subject", "")
        from_header = headers.get("From", "")
        date_header = headers.get("Date", "")
        list_unsubscribe = headers.get("List-Unsubscribe", "")

        # Parse author and domain from From header
        author_name, author_email = parseaddr(from_header)
        author = author_name or author_email
        site_name = _domain_from_email(author_email)

        # Parse date
        published_at = _parse_email_date(date_header)

        # Determine content type
        content_type = ContentType.NEWSLETTER if list_unsubscribe else ContentType.ARTICLE

        # Extract body from MIME parts
        body = self._extract_body(msg.get("payload", {}))
        word_count = len(body.split()) if body else 0

        item_id = hashlib.sha256(f"gmail-{msg_id}".encode()).hexdigest()[:16]

        return ContentItem(
            id=item_id,
            url="",
            title=subject,
            body=body,
            excerpt=body[:500] if body else "",
            word_count=word_count,
            author=author,
            site_name=site_name,
            source=ContentSource.GMAIL,
            source_id=msg_id,
            content_type=content_type,
            published_at=published_at,
            metadata={"message_id": msg_id},
        )

    def _extract_body(self, payload: dict) -> str:
        """Walk MIME parts to extract body text, preferring text/plain."""
        parts = payload.get("parts", [])

        # Single-part message
        if not parts:
            mime_type = payload.get("mimeType", "")
            data = payload.get("body", {}).get("data", "")
            if data:
                decoded = _decode_body(data)
                if mime_type == "text/plain":
                    return decoded
                if mime_type == "text/html":
                    return _strip_html(decoded)
            return ""

        # Multipart: prefer text/plain, fall back to text/html
        plain_text = ""
        html_text = ""

        for part in parts:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    plain_text = _decode_body(data)
            elif mime_type == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    html_text = _decode_body(data)
            elif mime_type.startswith("multipart/"):
                # Recurse into nested multipart
                nested = self._extract_body(part)
                if nested and not plain_text:
                    plain_text = nested

        if plain_text:
            return plain_text
        if html_text:
            return _strip_html(html_text)

        return ""


def _decode_body(data: str) -> str:
    """Decode base64url-encoded body data."""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Simple HTML tag stripping."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _domain_from_email(email: str) -> str:
    """Extract domain from an email address."""
    if "@" in email:
        return email.split("@", 1)[1]
    return ""


def _parse_email_date(date_str: str) -> datetime | None:
    """Parse an email Date header to datetime."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        logger.debug("Failed to parse email date: %s", date_str)
        return None
