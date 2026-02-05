"""Tests for Codex CLI session parser."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from session_insights.parsers.codex import CodexParser, CodexSession


class TestCodexSession:
    """Tests for CodexSession model."""

    def test_codex_session_source(self) -> None:
        """Test that CodexSession has correct source."""
        session = CodexSession(
            session_id="test-123",
            timestamp=datetime.now(),
        )
        assert session.source == "codex-cli"

    def test_codex_session_extra_fields(self) -> None:
        """Test CodexSession extra fields."""
        session = CodexSession(
            session_id="test-123",
            timestamp=datetime.now(),
            model="gpt-4",
            model_provider="openai",
            cwd="/home/user/project",
            version="1.0.0",
        )
        assert session.model == "gpt-4"
        assert session.model_provider == "openai"
        assert session.cwd == "/home/user/project"
        assert session.version == "1.0.0"

    def test_note_name_generation(self) -> None:
        """Test Obsidian note name generation."""
        ts = datetime(2024, 3, 15, 14, 30, 0)
        session = CodexSession(
            session_id="rollout-abc12345",
            timestamp=ts,
        )
        assert session.note_name == "codex-2024-03-15-1430-rollout-"


class TestCodexParserDiscoverSessions:
    """Tests for CodexParser session discovery."""

    @pytest.fixture
    def parser(self) -> CodexParser:
        """Create a parser instance."""
        return CodexParser()

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_discover_sessions_empty_directory(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test discovering sessions in an empty directory."""
        sessions = parser.discover_sessions(temp_dir)
        assert sessions == []

    def test_discover_sessions_codex_structure(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test discovering sessions in .codex/sessions structure."""
        codex_dir = temp_dir / ".codex"
        sessions_dir = codex_dir / "sessions" / "2024" / "01" / "15"
        sessions_dir.mkdir(parents=True)

        session_file = sessions_dir / "rollout-abc123.jsonl"
        session_file.write_text('{"type": "user", "content": "test"}')

        found = parser.discover_sessions(codex_dir)
        assert len(found) == 1
        assert found[0].name == "rollout-abc123.jsonl"

    def test_discover_sessions_direct_sessions_dir(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test discovering sessions directly from sessions directory."""
        sessions_dir = temp_dir / "sessions"
        date_dir = sessions_dir / "2024" / "01" / "15"
        date_dir.mkdir(parents=True)

        session_file = date_dir / "rollout-xyz789.jsonl"
        session_file.write_text('{"type": "user", "content": "test"}')

        found = parser.discover_sessions(sessions_dir)
        assert len(found) == 1

    def test_discover_multiple_sessions(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test discovering multiple session files across dates."""
        sessions_dir = temp_dir / "sessions"

        for date in ["2024/01/15", "2024/01/16"]:
            date_dir = sessions_dir / date
            date_dir.mkdir(parents=True)
            (date_dir / f"rollout-{date.replace('/', '')}.jsonl").write_text(
                '{"type": "user", "content": "test"}'
            )

        found = parser.discover_sessions(temp_dir)
        assert len(found) == 2


class TestCodexParserJsonParsing:
    """Tests for CodexParser JSON parsing."""

    @pytest.fixture
    def parser(self) -> CodexParser:
        """Create a parser instance."""
        return CodexParser()

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_parse_simple_session(self, parser: CodexParser, temp_dir: Path) -> None:
        """Test parsing a simple session file."""
        session_file = temp_dir / "rollout-test.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Hello Codex",
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-15T10:30:05Z",
                "content": "Hello! How can I help you?",
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        session = sessions[0]
        assert session.session_id == "rollout-test"
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[0].content == "Hello Codex"
        assert session.messages[1].role == "assistant"

    def test_parse_session_with_metadata_header(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing a session with metadata header."""
        session_file = temp_dir / "rollout-meta.jsonl"
        entries = [
            {
                "session_id": "custom-session-id",
                "model": "gpt-4",
                "model_provider": "openai",
                "cwd": "/home/user/project",
                "version": "0.5.0",
                "timestamp": "2024-01-15T10:30:00Z",
            },
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Hello",
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        session = sessions[0]
        assert session.session_id == "custom-session-id"
        assert session.model == "gpt-4"
        assert session.model_provider == "openai"
        assert session.cwd == "/home/user/project"
        assert session.version == "0.5.0"

    def test_parse_session_with_message_format(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing session with message field format."""
        session_file = temp_dir / "msg-format.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "message": {"content": "Message format content"},
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert sessions[0].messages[0].content == "Message format content"

    def test_parse_json_array_format(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing a .json file with array of entries."""
        session_file = temp_dir / "session.json"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Hello from JSON array",
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-15T10:30:05Z",
                "content": "Hi there!",
            },
        ]
        session_file.write_text(json.dumps(entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].messages) == 2
        assert sessions[0].messages[0].content == "Hello from JSON array"
        assert sessions[0].messages[1].content == "Hi there!"

    def test_parse_json_object_with_messages(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing a .json file with wrapper object containing messages."""
        session_file = temp_dir / "session.json"
        data = {
            "session_id": "wrapped-session",
            "messages": [
                {
                    "type": "user",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "content": "Hello from wrapped JSON",
                },
                {
                    "type": "assistant",
                    "timestamp": "2024-01-15T10:30:05Z",
                    "content": "Response here",
                },
            ],
        }
        session_file.write_text(json.dumps(data))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].messages) == 2
        assert sessions[0].messages[0].content == "Hello from wrapped JSON"

    def test_parse_json_single_object(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing a .json file with single entry object."""
        session_file = temp_dir / "single.json"
        data = {
            "type": "user",
            "timestamp": "2024-01-15T10:30:00Z",
            "content": "Single object entry",
        }
        session_file.write_text(json.dumps(data))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].messages) == 1
        assert sessions[0].messages[0].content == "Single object entry"

    def test_parse_json_with_conversation_wrapper(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing a .json file with conversation wrapper."""
        session_file = temp_dir / "conversation.json"
        data = {
            "conversation": [
                {
                    "type": "user",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "content": "Conversation wrapper test",
                },
            ],
        }
        session_file.write_text(json.dumps(data))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert sessions[0].messages[0].content == "Conversation wrapper test"


class TestCodexParserTimestampExtraction:
    """Tests for timestamp extraction."""

    @pytest.fixture
    def parser(self) -> CodexParser:
        """Create a parser instance."""
        return CodexParser()

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_timestamp_z_suffix(self, parser: CodexParser, temp_dir: Path) -> None:
        """Test parsing timestamp with Z suffix."""
        session_file = temp_dir / "ts-z.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Test",
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert sessions[0].timestamp.year == 2024
        assert sessions[0].timestamp.month == 1
        assert sessions[0].timestamp.day == 15

    def test_timestamp_offset_format(self, parser: CodexParser, temp_dir: Path) -> None:
        """Test parsing timestamp with offset format."""
        session_file = temp_dir / "ts-offset.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00+00:00",
                "content": "Test",
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert sessions[0].timestamp is not None

    def test_missing_timestamp_fallback(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test fallback to file mtime when no timestamp."""
        session_file = temp_dir / "no-ts.jsonl"
        entries = [
            {"type": "user", "content": "No timestamp here"},
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert sessions[0].timestamp is not None


class TestCodexParserToolUsageTracking:
    """Tests for tool usage tracking."""

    @pytest.fixture
    def parser(self) -> CodexParser:
        """Create a parser instance."""
        return CodexParser()

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_tool_call_in_assistant_message(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing tool calls within assistant messages."""
        session_file = temp_dir / "tool-call.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "List files",
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-15T10:30:05Z",
                "content": [
                    {"type": "text", "text": "I'll list the files."},
                    {
                        "type": "tool_use",
                        "id": "tool-123",
                        "name": "shell",
                        "input": {"command": "ls -la"},
                    },
                ],
            },
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:10Z",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-123",
                        "content": "file1.txt\nfile2.txt",
                    }
                ],
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].tool_calls) == 1
        tool_call = sessions[0].tool_calls[0]
        assert tool_call.tool_name == "shell"
        assert tool_call.arguments == {"command": "ls -la"}
        assert tool_call.result == "file1.txt\nfile2.txt"

    def test_standalone_tool_call_entries(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing standalone tool_call and tool_result entries."""
        session_file = temp_dir / "standalone-tool.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Run a command",
            },
            {
                "type": "tool_call",
                "id": "tool-456",
                "name": "execute",
                "input": {"cmd": "echo hello"},
            },
            {
                "type": "tool_result",
                "tool_call_id": "tool-456",
                "result": "hello",
                "duration_ms": 50,
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].tool_calls) == 1
        tool_call = sessions[0].tool_calls[0]
        assert tool_call.tool_name == "execute"
        assert tool_call.result == "hello"
        assert tool_call.duration_ms == 50

    def test_tool_use_without_result(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test that tool uses without results are still captured."""
        session_file = temp_dir / "pending-tool.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Do something",
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-15T10:30:05Z",
                "content": [
                    {"type": "text", "text": "Running..."},
                    {
                        "type": "tool_use",
                        "id": "tool-789",
                        "name": "read_file",
                        "input": {"path": "/test"},
                    },
                ],
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].tool_calls) == 1
        assert sessions[0].tool_calls[0].tool_name == "read_file"
        assert sessions[0].tool_calls[0].result is None


class TestCodexParserErrorHandling:
    """Tests for error handling with malformed files."""

    @pytest.fixture
    def parser(self) -> CodexParser:
        """Create a parser instance."""
        return CodexParser()

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_handle_malformed_json(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test graceful handling of malformed JSON lines."""
        session_file = temp_dir / "bad-json.jsonl"
        content = """{\"type\": \"user\", \"content\": \"Valid\", \"timestamp\": \"2024-01-15T10:30:00Z\"}
{invalid json line}
{\"type\": \"assistant\", \"content\": \"Also valid\", \"timestamp\": \"2024-01-15T10:30:05Z\"}"""
        session_file.write_text(content)

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].messages) == 2
        assert len(parser.parse_errors) > 0

    def test_handle_empty_file(self, parser: CodexParser, temp_dir: Path) -> None:
        """Test handling of empty session files."""
        session_file = temp_dir / "empty.jsonl"
        session_file.write_text("")

        sessions = parser.parse_directory(temp_dir)
        assert sessions == []

    def test_handle_file_with_no_messages(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test handling of session file with no valid messages."""
        session_file = temp_dir / "no-messages.jsonl"
        entries = [
            {"type": "unknown", "data": "something"},
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        sessions = parser.parse_directory(temp_dir)
        assert sessions == []

    def test_handle_blank_lines(self, parser: CodexParser, temp_dir: Path) -> None:
        """Test handling of blank lines in JSONL."""
        session_file = temp_dir / "blanks.jsonl"
        content = """{\"type\": \"user\", \"content\": \"Hello\", \"timestamp\": \"2024-01-15T10:30:00Z\"}

{\"type\": \"assistant\", \"content\": \"Hi\", \"timestamp\": \"2024-01-15T10:30:05Z\"}

"""
        session_file.write_text(content)

        sessions = parser.parse_directory(temp_dir)
        assert len(sessions) == 1
        assert len(sessions[0].messages) == 2

    def test_parse_nonexistent_file(self, parser: CodexParser) -> None:
        """Test parsing a nonexistent file."""
        session = parser.parse_session_file(Path("/nonexistent/file.jsonl"))
        assert session is None
        assert len(parser.parse_errors) > 0

    def test_parse_errors_cleared_on_new_parse(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test that parse errors are cleared on each parse call."""
        # First parse with error
        bad_file = temp_dir / "bad.jsonl"
        bad_file.write_text("{invalid}")
        parser.parse_directory(temp_dir)
        assert len(parser.parse_errors) > 0

        # Second parse with good file
        bad_file.unlink()
        good_file = temp_dir / "good.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Valid",
            },
        ]
        good_file.write_text("\n".join(json.dumps(e) for e in entries))
        parser.parse_directory(temp_dir)
        assert len(parser.parse_errors) == 0


class TestCodexParserPublicAPI:
    """Tests for public API methods."""

    @pytest.fixture
    def parser(self) -> CodexParser:
        """Create a parser instance."""
        return CodexParser()

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_parse_session_file_method(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test the public parse_session_file method."""
        session_file = temp_dir / "single.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-15T10:30:00Z",
                "content": "Test message",
            },
        ]
        session_file.write_text("\n".join(json.dumps(e) for e in entries))

        session = parser.parse_session_file(session_file)
        assert session is not None
        assert session.session_id == "single"
        assert len(session.messages) == 1

    def test_parser_initialization(self, parser: CodexParser) -> None:
        """Test parser initialization."""
        assert parser.parse_errors == []

    def test_parse_empty_directory(
        self, parser: CodexParser, temp_dir: Path
    ) -> None:
        """Test parsing an empty directory."""
        sessions = parser.parse_directory(temp_dir)
        assert sessions == []
