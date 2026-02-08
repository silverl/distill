"""Google OAuth2 shared authentication utility."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional dependency -- graceful skip if not installed
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    _HAS_GOOGLE_AUTH = True
except ImportError:
    _HAS_GOOGLE_AUTH = False
    Request = None  # type: ignore[assignment, misc]
    Credentials = None  # type: ignore[assignment, misc]
    InstalledAppFlow = None  # type: ignore[assignment, misc]


def is_available() -> bool:
    """Check if Google auth libraries are installed."""
    return _HAS_GOOGLE_AUTH


def get_credentials(
    credentials_file: str,
    token_file: str,
    scopes: list[str],
) -> Credentials | None:
    """Get valid Google OAuth2 credentials.

    Loads cached token from token_file if it exists and is valid.
    If expired, refreshes. If no token, runs OAuth consent flow.

    Args:
        credentials_file: Path to OAuth client credentials JSON (from Google Cloud Console).
        token_file: Path to store/load the cached token.
        scopes: List of OAuth scopes needed.

    Returns:
        Valid Credentials object, or None if auth fails.
    """
    if not _HAS_GOOGLE_AUTH:
        logger.warning("Google auth libraries not installed. pip install google-auth-oauthlib")
        return None

    creds: Credentials | None = None
    token_path = Path(token_file)

    # Load cached token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except Exception:
            logger.warning("Failed to load cached token from %s", token_file)
            creds = None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            logger.warning("Token refresh failed, re-authenticating")
            creds = None

    # Run OAuth flow if no valid creds
    if not creds or not creds.valid:
        cred_path = Path(credentials_file)
        if not cred_path.exists():
            logger.error("Credentials file not found: %s", credentials_file)
            return None
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), scopes)
            creds = flow.run_local_server(port=0)
        except Exception:
            logger.error("OAuth flow failed", exc_info=True)
            return None

        # Cache token
        if creds:
            try:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(creds.to_json(), encoding="utf-8")
            except Exception:
                logger.warning("Failed to cache token to %s", token_file)

    return creds
