"""Tests for src/notifications.py — Slack + ntfy notification channels."""

from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest
from distill.config import NotificationConfig
from distill.errors import PipelineReport
from distill.notifications import _send_ntfy, _send_slack, send_notification


@pytest.fixture
def report():
    r = PipelineReport()
    r.mark_stage_complete("journal")
    r.items_processed = {"journal": 2}
    r.finish()
    return r


class TestSendNotification:
    def test_skips_when_not_configured(self, report):
        config = NotificationConfig()
        # Should not raise, just return silently
        send_notification(config, report)

    @patch("distill.notifications._send_slack")
    def test_sends_slack_when_configured(self, mock_slack, report):
        config = NotificationConfig(slack_webhook="https://hooks.slack.com/test")
        send_notification(config, report)
        mock_slack.assert_called_once_with("https://hooks.slack.com/test", report)

    @patch("distill.notifications._send_ntfy")
    def test_sends_ntfy_when_configured(self, mock_ntfy, report):
        config = NotificationConfig(ntfy_url="https://ntfy.sh", ntfy_topic="distill")
        send_notification(config, report)
        mock_ntfy.assert_called_once_with("https://ntfy.sh", "distill", report)

    @patch("distill.notifications._send_slack")
    @patch("distill.notifications._send_ntfy")
    def test_sends_both_when_both_configured(self, mock_ntfy, mock_slack, report):
        config = NotificationConfig(
            slack_webhook="https://hooks.slack.com/test",
            ntfy_url="https://ntfy.sh",
            ntfy_topic="mytopic",
        )
        send_notification(config, report)
        mock_slack.assert_called_once()
        mock_ntfy.assert_called_once()


class TestSlack:
    @patch("distill.notifications.urllib.request.urlopen")
    def test_sends_json_payload(self, mock_urlopen, report):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        _send_slack("https://hooks.slack.com/test", report)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://hooks.slack.com/test"
        assert req.get_header("Content-type") == "application/json"

    @patch("distill.notifications.urllib.request.urlopen")
    def test_handles_network_error(self, mock_urlopen, report):
        mock_urlopen.side_effect = URLError("connection failed")
        # Should not raise
        _send_slack("https://hooks.slack.com/test", report)


class TestNtfy:
    @patch("distill.notifications.urllib.request.urlopen")
    def test_sends_to_topic_url(self, mock_urlopen, report):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        _send_ntfy("https://ntfy.sh", "distill", report)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://ntfy.sh/distill"
        assert "Title" in req.headers

    @patch("distill.notifications.urllib.request.urlopen")
    def test_handles_network_error(self, mock_urlopen, report):
        mock_urlopen.side_effect = URLError("connection failed")
        _send_ntfy("https://ntfy.sh", "distill", report)

    @patch("distill.notifications.urllib.request.urlopen")
    def test_high_priority_on_failure(self, mock_urlopen):
        report = PipelineReport()
        report.add_error("blog", "crash", recoverable=False)
        report.finish()

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        _send_ntfy("https://ntfy.sh", "distill", report)

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Priority") == "high"
