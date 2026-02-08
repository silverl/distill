"""Codex CLI session parser for .codex/ session history."""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import BaseSession, Message, ToolUsage

logger = logging.getLogger(__name__)


class CodexSession(BaseSession):
    """Represents a parsed Codex CLI session.

    Extends BaseSession with Codex-specific fields.
    """

    source: str = "codex-cli"
    model: str | None = None
    model_provider: str | None = None
    cwd: str | None = None
    version: str | None = None

    @property
    def note_name(self) -> str:
        """Generate Obsidian-compatible note name."""
        date_str = self.timestamp.strftime("%Y-%m-%d")
        time_str = self.timestamp.strftime("%H%M")
        return f"codex-{date_str}-{time_str}-{self.session_id[:8]}"


class CodexParser:
    """Parser for Codex CLI session history stored in .codex/ directory.

    Handles the JSONL format used by Codex CLI to store session transcripts.
    The parser traverses .codex/sessions/YYYY/MM/DD/rollout-*.jsonl files to extract
    conversation turns, tool usage, timestamps, and outcomes.
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self._parse_errors: list[str] = []

    @property
    def parse_errors(self) -> list[str]:
        """Return any errors encountered during parsing."""
        return self._parse_errors.copy()

    def discover_sessions(self, path: Path) -> list[Path]:
        """Discover all Codex session files in a directory.

        Args:
            path: Path to .codex directory or a sessions directory

        Returns:
            List of paths to session JSONL files
        """
        session_files: list[Path] = []

        # Handle different directory structures
        if path.name == ".codex":
            # Full .codex directory - look for sessions subdirectory
            sessions_dir = path / "sessions"
            if sessions_dir.exists():
                session_files.extend(self._find_session_files(sessions_dir))
        elif path.name == "sessions":
            # Direct sessions directory
            session_files.extend(self._find_session_files(path))
        elif (path / "sessions").exists():
            # Directory containing sessions subdirectory
            session_files.extend(self._find_session_files(path / "sessions"))
        else:
            # Assume it's a directory containing session files directly
            session_files.extend(self._find_session_files(path))

        return sorted(session_files, key=lambda p: p.stat().st_mtime, reverse=True)

    def _find_session_files(self, sessions_dir: Path) -> list[Path]:
        """Find all session JSONL files in a sessions directory.

        Handles the YYYY/MM/DD/rollout-*.jsonl structure.
        """
        session_files: list[Path] = []

        # Look for rollout-*.jsonl files in nested date directories
        session_files.extend(sessions_dir.glob("**/rollout-*.jsonl"))

        # Also look for any .jsonl files directly
        session_files.extend(sessions_dir.glob("*.jsonl"))

        # And .json files
        session_files.extend(sessions_dir.glob("**/*.json"))

        # Deduplicate while preserving order
        seen: set[Path] = set()
        unique_files: list[Path] = []
        for f in session_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)

        return unique_files

    def parse_directory(
        self,
        path: Path,
        *,
        since: date | None = None,
    ) -> list[CodexSession]:
        """Parse all Codex sessions from a directory.

        Args:
            path: Path to .codex directory or a specific sessions directory
            since: Only parse files modified on or after this date (uses mtime).

        Returns:
            List of parsed CodexSession objects
        """
        self._parse_errors = []
        sessions: list[CodexSession] = []

        session_files = self.discover_sessions(path)

        # Pre-filter by file modification time (much cheaper than parsing)
        if since is not None:
            since_ts = datetime.combine(since, datetime.min.time()).timestamp()
            session_files = [f for f in session_files if f.stat().st_mtime >= since_ts]

        for session_file in session_files:
            try:
                session = self._parse_session_file(session_file)
                if session is not None:
                    sessions.append(session)
            except Exception as e:
                error_msg = f"Error parsing {session_file}: {e}"
                logger.warning(error_msg)
                self._parse_errors.append(error_msg)

        return sessions

    def _parse_session_file(self, file_path: Path) -> CodexSession | None:
        """Parse a single session file (JSONL or JSON format).

        Args:
            file_path: Path to the .jsonl or .json session file

        Returns:
            Parsed CodexSession or None if parsing fails
        """
        messages: list[Message] = []
        tool_calls: list[ToolUsage] = []
        session_id = file_path.stem  # Use filename (without extension) as session ID
        first_timestamp: datetime | None = None
        model: str | None = None
        model_provider: str | None = None
        cwd: str | None = None
        version: str | None = None
        metadata: dict[str, Any] = {}

        # Track tool use IDs to match with results
        pending_tool_uses: dict[str, ToolUsage] = {}

        # Determine file format and get entries
        entries = self._load_entries(file_path)
        if entries is None:
            return None

        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue

            # Extract session metadata from header entry
            if idx == 0 and self._is_metadata_entry(entry):
                session_id, model, model_provider, cwd, version, first_timestamp = (
                    self._extract_metadata(entry, session_id)
                )
                continue

            # Extract timestamp from entry
            entry_timestamp = self._extract_timestamp(entry)
            if entry_timestamp and (first_timestamp is None or entry_timestamp < first_timestamp):
                first_timestamp = entry_timestamp

            # Process different entry types
            entry_type = entry.get("type")

            if entry_type == "user" or entry_type == "human":
                self._process_user_entry(entry, messages, pending_tool_uses, tool_calls)
            elif entry_type == "assistant" or entry_type == "ai":
                model = self._process_assistant_entry(entry, messages, pending_tool_uses, model)
            elif entry_type == "message":
                # Generic message type - determine role from content
                self._process_generic_message(entry, messages, pending_tool_uses, tool_calls)
            elif entry_type == "tool_call" or entry_type == "action":
                self._process_tool_call_entry(entry, pending_tool_uses)
            elif entry_type == "tool_result" or entry_type == "observation":
                self._process_tool_result_entry(entry, pending_tool_uses, tool_calls)

        # Skip sessions with no messages
        if not messages:
            return None

        # Use file modification time if no timestamp found
        if first_timestamp is None:
            first_timestamp = datetime.fromtimestamp(file_path.stat().st_mtime)

        # Add any remaining pending tool uses (without results)
        for tool_use in pending_tool_uses.values():
            tool_calls.append(tool_use)

        # Derive project from cwd
        project = ""
        if cwd:
            name = Path(cwd).name
            if name and name != "/":
                project = name

        session = CodexSession(
            session_id=session_id,
            timestamp=first_timestamp,
            messages=messages,
            tool_calls=tool_calls,
            model=model,
            model_provider=model_provider,
            cwd=cwd,
            version=version,
            metadata=metadata,
            project=project,
        )

        self._enrich_session(session)
        return session

    def _enrich_session(self, session: CodexSession) -> None:
        """Enrich a parsed session with summary and narrative."""
        if not session.summary:
            user_msgs = [m for m in session.messages if m.role == "user"]
            if user_msgs:
                session.summary = user_msgs[0].content[:200]

        if not session.narrative and session.summary:
            session.narrative = session.summary

    def _load_entries(self, file_path: Path) -> list[dict[str, Any]] | None:
        """Load entries from a file, handling both JSON and JSONL formats.

        Args:
            file_path: Path to the session file

        Returns:
            List of entry dictionaries, or None if file is empty/invalid
        """
        entries: list[dict[str, Any]] = []

        with open(file_path, encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return None

        # Try to detect format: JSON files typically start with [ or {
        # and contain the entire structure in one parse
        if file_path.suffix == ".json" or (content.startswith("[") or content.startswith("{")):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    # JSON array of entries
                    entries = [e for e in data if isinstance(e, dict)]
                elif isinstance(data, dict):
                    # Single object - could be wrapper or single entry
                    # Check for common wrapper patterns
                    if "messages" in data:
                        msgs = data["messages"]
                        if isinstance(msgs, list):
                            entries = [e for e in msgs if isinstance(e, dict)]
                    elif "entries" in data:
                        ents = data["entries"]
                        if isinstance(ents, list):
                            entries = [e for e in ents if isinstance(e, dict)]
                    elif "conversation" in data:
                        conv = data["conversation"]
                        if isinstance(conv, list):
                            entries = [e for e in conv if isinstance(e, dict)]
                    else:
                        # Treat as single entry
                        entries = [data]
                return entries if entries else None
            except json.JSONDecodeError:
                # Fall through to JSONL parsing
                pass

        # JSONL format: one JSON object per line
        for line_num, line in enumerate(content.split("\n"), 1):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
                if isinstance(entry, dict):
                    entries.append(entry)
            except json.JSONDecodeError as e:
                error_msg = f"JSON decode error in {file_path}:{line_num}: {e}"
                logger.debug(error_msg)
                self._parse_errors.append(error_msg)
                continue

        return entries if entries else None

    def _is_metadata_entry(self, entry: dict[str, Any]) -> bool:
        """Check if an entry is a metadata header."""
        # Metadata entries typically have session_id or id field with session info
        return (
            "session_id" in entry
            or "id" in entry
            or "metadata" in entry
            or ("type" not in entry and "model" in entry)
        )

    def _extract_metadata(
        self, entry: dict[str, Any], default_session_id: str
    ) -> tuple[str, str | None, str | None, str | None, str | None, datetime | None]:
        """Extract session metadata from header entry."""
        session_id = entry.get("session_id") or entry.get("id") or default_session_id
        model = entry.get("model")
        model_provider = entry.get("model_provider") or entry.get("provider")
        cwd = entry.get("cwd") or entry.get("working_directory")
        version = entry.get("version") or entry.get("codex_version")

        timestamp = None
        ts_str = entry.get("timestamp") or entry.get("created_at")
        if ts_str:
            timestamp = self._safe_parse_timestamp(ts_str)

        return session_id, model, model_provider, cwd, version, timestamp

    def _extract_timestamp(self, entry: dict[str, Any]) -> datetime | None:
        """Extract timestamp from an entry."""
        ts_str = entry.get("timestamp") or entry.get("created_at") or entry.get("ts")
        return self._safe_parse_timestamp(ts_str)

    def _process_user_entry(
        self,
        entry: dict[str, Any],
        messages: list[Message],
        pending_tool_uses: dict[str, ToolUsage],
        tool_calls: list[ToolUsage],
    ) -> None:
        """Process a user-type entry from the JSONL file."""
        timestamp = self._extract_timestamp(entry)
        content = self._extract_content(entry)

        if isinstance(content, str) and content:
            messages.append(Message(role="user", content=content, timestamp=timestamp))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "tool_result":
                        self._handle_tool_result(item, pending_tool_uses, tool_calls, entry)
                    elif item.get("type") == "text":
                        text = item.get("text", "")
                        if text:
                            messages.append(Message(role="user", content=text, timestamp=timestamp))

    def _process_assistant_entry(
        self,
        entry: dict[str, Any],
        messages: list[Message],
        pending_tool_uses: dict[str, ToolUsage],
        current_model: str | None,
    ) -> str | None:
        """Process an assistant-type entry from the JSONL file."""
        timestamp = self._extract_timestamp(entry)
        content = self._extract_content(entry)
        model = entry.get("model", current_model)

        if isinstance(content, str) and content:
            messages.append(Message(role="assistant", content=content, timestamp=timestamp))
        elif isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))
                    elif item_type == "tool_use":
                        tool_id = item.get("id", "")
                        tool_name = item.get("name", "unknown")
                        tool_input = item.get("input", {})
                        tool_use = ToolUsage(
                            tool_name=tool_name,
                            arguments=tool_input if isinstance(tool_input, dict) else {},
                        )
                        pending_tool_uses[tool_id] = tool_use

            if text_parts:
                messages.append(
                    Message(
                        role="assistant",
                        content="\n".join(text_parts),
                        timestamp=timestamp,
                    )
                )

        return model

    def _process_generic_message(
        self,
        entry: dict[str, Any],
        messages: list[Message],
        pending_tool_uses: dict[str, ToolUsage],
        tool_calls: list[ToolUsage],
    ) -> None:
        """Process a generic message entry."""
        role = entry.get("role", "user")
        timestamp = self._extract_timestamp(entry)
        content = self._extract_content(entry)

        if role in ("user", "human"):
            self._process_user_entry(entry, messages, pending_tool_uses, tool_calls)
        elif role in ("assistant", "ai"):
            self._process_assistant_entry(entry, messages, pending_tool_uses, None)
        elif isinstance(content, str) and content:
            messages.append(Message(role=role, content=content, timestamp=timestamp))

    def _process_tool_call_entry(
        self, entry: dict[str, Any], pending_tool_uses: dict[str, ToolUsage]
    ) -> None:
        """Process a standalone tool call entry."""
        tool_id = entry.get("id") or entry.get("tool_call_id") or ""
        tool_name = entry.get("name") or entry.get("tool_name") or "unknown"
        tool_input = entry.get("input") or entry.get("arguments") or {}

        tool_use = ToolUsage(
            tool_name=tool_name,
            arguments=tool_input if isinstance(tool_input, dict) else {},
        )
        pending_tool_uses[tool_id] = tool_use

    def _process_tool_result_entry(
        self,
        entry: dict[str, Any],
        pending_tool_uses: dict[str, ToolUsage],
        tool_calls: list[ToolUsage],
    ) -> None:
        """Process a standalone tool result entry."""
        tool_id = entry.get("tool_call_id") or entry.get("id") or ""
        result = entry.get("result") or entry.get("output") or entry.get("content") or ""

        if isinstance(result, (list, dict)):
            result = str(result)

        if tool_id in pending_tool_uses:
            tool_use = pending_tool_uses.pop(tool_id)
            tool_use.result = result
            if "duration_ms" in entry:
                tool_use.duration_ms = entry["duration_ms"]
            tool_calls.append(tool_use)

    def _handle_tool_result(
        self,
        item: dict[str, Any],
        pending_tool_uses: dict[str, ToolUsage],
        tool_calls: list[ToolUsage],
        entry: dict[str, Any],
    ) -> None:
        """Handle a tool result item within a message."""
        tool_use_id = item.get("tool_use_id")
        if tool_use_id and tool_use_id in pending_tool_uses:
            tool_use = pending_tool_uses.pop(tool_use_id)
            result_content = item.get("content", "")
            if isinstance(result_content, list):
                result_content = str(result_content)
            tool_use.result = result_content

            # Get duration from entry metadata if available
            tool_result_meta = entry.get("toolUseResult", {})
            if "durationMs" in tool_result_meta:
                tool_use.duration_ms = tool_result_meta["durationMs"]

            tool_calls.append(tool_use)

    def _extract_content(self, entry: dict[str, Any]) -> str | list[Any] | None:
        """Extract content from an entry, handling various formats."""
        # Try different content field names
        if "message" in entry:
            msg = entry["message"]
            if isinstance(msg, dict):
                return msg.get("content")
            return msg
        if "content" in entry:
            return entry["content"]
        if "text" in entry:
            return entry["text"]
        return None

    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse an ISO format timestamp string."""
        # Handle ISO format with Z suffix
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)

    def _safe_parse_timestamp(self, ts_str: str | None) -> datetime | None:
        """Safely parse a timestamp, returning None on failure."""
        if ts_str is None:
            return None
        try:
            return self._parse_timestamp(ts_str)
        except (ValueError, TypeError):
            return None

    def parse_session_file(self, file_path: Path) -> CodexSession | None:
        """Public method to parse a single session file.

        Args:
            file_path: Path to the .jsonl session file

        Returns:
            Parsed CodexSession or None if parsing fails
        """
        self._parse_errors = []
        try:
            return self._parse_session_file(file_path)
        except Exception as e:
            error_msg = f"Error parsing {file_path}: {e}"
            logger.error(error_msg)
            self._parse_errors.append(error_msg)
            return None
