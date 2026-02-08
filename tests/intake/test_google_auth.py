"""Tests for the Google OAuth2 shared authentication utility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# The module under test -- google auth libs may not be installed,
# so Request/InstalledAppFlow may not exist as module attrs.
# We use create=True on patches for those names.
_MOD = "distill.intake.parsers._google_auth"


# ── is_available ─────────────────────────────────────────────────────


class TestIsAvailable:
    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    def test_returns_true_when_libs_installed(self) -> None:
        from distill.intake.parsers._google_auth import is_available

        assert is_available() is True

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", False)
    def test_returns_false_when_libs_missing(self) -> None:
        from distill.intake.parsers._google_auth import is_available

        assert is_available() is False


# ── get_credentials ──────────────────────────────────────────────────


class TestGetCredentials:
    """All tests mock out Google auth objects. No real OAuth calls."""

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", False)
    def test_returns_none_when_libs_not_installed(self) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is None

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_loads_cached_valid_token(
        self, mock_creds_cls: MagicMock, mock_path_cls: MagicMock
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_path_cls.return_value = mock_token_path

        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is mock_creds
        mock_creds_cls.from_authorized_user_file.assert_called_once()

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.Request", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_refreshes_expired_token(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_request_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_path_cls.return_value = mock_token_path

        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_tok"
        mock_creds.valid = True  # valid after refresh
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is mock_creds
        mock_creds.refresh.assert_called_once_with(mock_request_cls.return_value)

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.InstalledAppFlow", create=True)
    @patch(f"{_MOD}.Request", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_failed_refresh_triggers_oauth_flow(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_request_cls: MagicMock,
        mock_flow_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = True
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_expired_creds = MagicMock()
        mock_expired_creds.expired = True
        mock_expired_creds.refresh_token = "refresh_tok"
        mock_expired_creds.valid = False
        mock_expired_creds.refresh.side_effect = Exception("refresh error")
        mock_creds_cls.from_authorized_user_file.return_value = mock_expired_creds

        mock_new_creds = MagicMock()
        mock_new_creds.valid = True
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is mock_new_creds
        mock_flow.run_local_server.assert_called_once_with(port=0)

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.InstalledAppFlow", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_no_token_file_triggers_oauth_flow(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_flow_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = True
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_new_creds = MagicMock()
        mock_new_creds.valid = True
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is mock_new_creds
        mock_flow_cls.from_client_secrets_file.assert_called_once()

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_missing_credentials_file_returns_none(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = False
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        result = get_credentials("missing.json", "token.json", ["scope1"])
        assert result is None

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.InstalledAppFlow", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_caches_token_after_successful_flow(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_flow_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_parent = MagicMock()
        mock_token_path.parent = mock_parent
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = True
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_new_creds = MagicMock()
        mock_new_creds.valid = True
        mock_new_creds.to_json.return_value = '{"token": "abc"}'
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        get_credentials("creds.json", "token.json", ["scope1"])

        mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_token_path.write_text.assert_called_once_with(
            '{"token": "abc"}', encoding="utf-8"
        )

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.InstalledAppFlow", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_token_cache_write_failure_still_returns_creds(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_flow_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_token_path.parent.mkdir.side_effect = OSError("permission denied")
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = True
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_new_creds = MagicMock()
        mock_new_creds.valid = True
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is mock_new_creds

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.InstalledAppFlow", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_oauth_flow_failure_returns_none(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_flow_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = True
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_flow_cls.from_client_secrets_file.side_effect = Exception("flow error")

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is None

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_corrupted_token_file_falls_through(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = False
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_creds_cls.from_authorized_user_file.side_effect = Exception("corrupt")

        result = get_credentials("creds.json", "token.json", ["scope1"])
        assert result is None

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.InstalledAppFlow", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_parent_directory_created_for_token(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_flow_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_parent = MagicMock()
        mock_token_path.parent = mock_parent
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = True
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_new_creds = MagicMock()
        mock_new_creds.valid = True
        mock_new_creds.to_json.return_value = "{}"
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        get_credentials("creds.json", "/nested/dir/token.json", ["scope1"])

        mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_scopes_passed_to_from_authorized_user_file(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_path_cls.return_value = mock_token_path

        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        get_credentials("creds.json", "token.json", scopes)

        mock_creds_cls.from_authorized_user_file.assert_called_once_with(
            str(mock_token_path), scopes
        )

    @patch(f"{_MOD}._HAS_GOOGLE_AUTH", True)
    @patch(f"{_MOD}.InstalledAppFlow", create=True)
    @patch(f"{_MOD}.Path")
    @patch(f"{_MOD}.Credentials")
    def test_scopes_passed_to_flow(
        self,
        mock_creds_cls: MagicMock,
        mock_path_cls: MagicMock,
        mock_flow_cls: MagicMock,
    ) -> None:
        from distill.intake.parsers._google_auth import get_credentials

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_cred_path = MagicMock()
        mock_cred_path.exists.return_value = True
        mock_path_cls.side_effect = [mock_token_path, mock_cred_path]

        mock_new_creds = MagicMock()
        mock_new_creds.valid = True
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
        get_credentials("creds.json", "token.json", scopes)

        mock_flow_cls.from_client_secrets_file.assert_called_once_with(
            str(mock_cred_path), scopes
        )
