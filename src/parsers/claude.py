"""Claude session parser for .claude/ session history."""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import BaseSession, Message, SessionOutcome, ToolUsage

logger = logging.getLogger(__name__)


class ClaudeSession(BaseSession):
    """Represents a parsed Claude Code session.

    Extends BaseSession with Claude-specific fields.
    """

    source: str = "claude-code"
    model: str | None = None
    git_branch: str | None = None
    cwd: str | None = None
    version: str | None = None

    @property
    def note_name(self) -> str:
        """Generate Obsidian-compatible note name."""
        date_str = self.timestamp.strftime("%Y-%m-%d")
        time_str = self.timestamp.strftime("%H%M")
        return f"session-{date_str}-{time_str}-{self.session_id[:8]}"


class ClaudeParser:
    """Parser for Claude Code session history stored in .claude/ directory.

    Handles the JSONL format used by Claude Code to store session transcripts.
    The parser traverses .claude/projects/*/[session-id].jsonl files to extract
    conversation turns, tool usage, timestamps, and outcomes.
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self._parse_errors: list[str] = []

    @property
    def parse_errors(self) -> list[str]:
        """Return any errors encountered during parsing."""
        return self._parse_errors.copy()

    def parse_directory(
        self,
        path: Path,
        *,
        since: date | None = None,
    ) -> list[ClaudeSession]:
        """Parse all Claude sessions from a directory.

        Args:
            path: Path to .claude directory or a specific project directory
            since: Only parse files modified on or after this date (uses mtime).

        Returns:
            List of parsed ClaudeSession objects
        """
        self._parse_errors = []
        sessions: list[ClaudeSession] = []

        # Handle different directory structures
        if path.name == ".claude":
            # Full .claude directory - look for projects subdirectory
            projects_dir = path / "projects"
            if projects_dir.exists():
                for project_dir in projects_dir.iterdir():
                    if project_dir.is_dir():
                        sessions.extend(self._parse_project_directory(project_dir, since=since))
        elif (path / "projects").exists():
            # .claude directory without the .claude name
            for project_dir in (path / "projects").iterdir():
                if project_dir.is_dir():
                    sessions.extend(self._parse_project_directory(project_dir, since=since))
        else:
            # Assume it's a project directory directly
            sessions.extend(self._parse_project_directory(path, since=since))

        return sessions

    def _parse_project_directory(
        self,
        project_dir: Path,
        *,
        since: date | None = None,
    ) -> list[ClaudeSession]:
        """Parse all sessions from a single project directory.

        Args:
            project_dir: Path to a project directory containing session files.
                         Handles both direct .jsonl files and sessions/ subdirectory.
            since: Only parse files modified on or after this date (uses mtime).

        Returns:
            List of parsed ClaudeSession objects
        """
        sessions: list[ClaudeSession] = []
        session_files: list[Path] = []

        # Look for session files directly in project directory
        session_files.extend(project_dir.glob("*.jsonl"))
        session_files.extend(project_dir.glob("*.json"))

        # Also check sessions/ subdirectory (common Claude structure)
        sessions_dir = project_dir / "sessions"
        if sessions_dir.exists() and sessions_dir.is_dir():
            session_files.extend(sessions_dir.glob("*.jsonl"))
            session_files.extend(sessions_dir.glob("*.json"))

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

    def _parse_session_file(self, file_path: Path) -> ClaudeSession | None:
        """Parse a single session JSONL file.

        Args:
            file_path: Path to the .jsonl session file

        Returns:
            Parsed ClaudeSession or None if parsing fails
        """
        messages: list[Message] = []
        tool_calls: list[ToolUsage] = []
        session_id = file_path.stem  # Use filename (without extension) as session ID
        first_timestamp: datetime | None = None
        model: str | None = None
        git_branch: str | None = None
        cwd: str | None = None
        version: str | None = None
        metadata: dict[str, Any] = {}

        # Track tool use IDs to match with results
        pending_tool_uses: dict[str, ToolUsage] = {}

        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    error_msg = f"JSON decode error in {file_path}:{line_num}: {e}"
                    logger.debug(error_msg)
                    self._parse_errors.append(error_msg)
                    continue

                # Extract session metadata from first relevant entry
                if "sessionId" in entry:
                    session_id = entry["sessionId"]
                if "timestamp" in entry:
                    try:
                        ts = self._parse_timestamp(entry["timestamp"])
                        if first_timestamp is None or ts < first_timestamp:
                            first_timestamp = ts
                    except (ValueError, TypeError):
                        pass

                # Extract other metadata
                if "gitBranch" in entry:
                    git_branch = entry["gitBranch"]
                if "cwd" in entry:
                    cwd = entry["cwd"]
                if "version" in entry:
                    version = entry["version"]

                entry_type = entry.get("type")

                if entry_type == "user":
                    self._process_user_entry(entry, messages, pending_tool_uses, tool_calls)
                elif entry_type == "assistant":
                    model = self._process_assistant_entry(entry, messages, pending_tool_uses, model)

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

        session = ClaudeSession(
            session_id=session_id,
            timestamp=first_timestamp,
            messages=messages,
            tool_calls=tool_calls,
            model=model,
            git_branch=git_branch,
            cwd=cwd,
            version=version,
            metadata=metadata,
            project=project,
        )

        self._enrich_session(session)
        return session

    def _process_user_entry(
        self,
        entry: dict[str, Any],
        messages: list[Message],
        pending_tool_uses: dict[str, ToolUsage],
        tool_calls: list[ToolUsage],
    ) -> None:
        """Process a user-type entry from the JSONL file.

        Handles both text messages and tool results.
        """
        message_data = entry.get("message", {})
        content = message_data.get("content")
        timestamp = self._safe_parse_timestamp(entry.get("timestamp"))

        if isinstance(content, str):
            # Simple text message
            messages.append(Message(role="user", content=content, timestamp=timestamp))
        elif isinstance(content, list):
            # Could be tool results or structured content
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "tool_result":
                        # Match tool result with pending tool use
                        tool_use_id = item.get("tool_use_id")
                        if tool_use_id and tool_use_id in pending_tool_uses:
                            tool_use = pending_tool_uses.pop(tool_use_id)
                            result_content = item.get("content", "")
                            if isinstance(result_content, list):
                                result_content = str(result_content)
                            tool_use.result = result_content

                            # Get duration from toolUseResult if available
                            tool_result_meta = entry.get("toolUseResult", {})
                            if "durationMs" in tool_result_meta:
                                tool_use.duration_ms = tool_result_meta["durationMs"]

                            tool_calls.append(tool_use)
                    elif item.get("type") == "text":
                        messages.append(
                            Message(
                                role="user",
                                content=item.get("text", ""),
                                timestamp=timestamp,
                            )
                        )

    def _process_assistant_entry(
        self,
        entry: dict[str, Any],
        messages: list[Message],
        pending_tool_uses: dict[str, ToolUsage],
        current_model: str | None,
    ) -> str | None:
        """Process an assistant-type entry from the JSONL file.

        Handles text content and tool use blocks.

        Returns:
            The model name if found in this entry
        """
        message_data = entry.get("message", {})
        content = message_data.get("content", [])
        timestamp = self._safe_parse_timestamp(entry.get("timestamp"))
        model = message_data.get("model", current_model)

        if isinstance(content, str):
            messages.append(Message(role="assistant", content=content, timestamp=timestamp))
        elif isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))
                    elif item_type == "tool_use":
                        # Create pending tool use
                        tool_id = item.get("id", "")
                        tool_name = item.get("name", "unknown")
                        tool_input = item.get("input", {})
                        tool_use = ToolUsage(
                            tool_name=tool_name,
                            arguments=tool_input if isinstance(tool_input, dict) else {},
                        )
                        pending_tool_uses[tool_id] = tool_use
                    # Skip "thinking" blocks - they're internal

            if text_parts:
                messages.append(
                    Message(
                        role="assistant",
                        content="\n".join(text_parts),
                        timestamp=timestamp,
                    )
                )

        return model

    def _enrich_session(self, session: ClaudeSession) -> None:
        """Enrich a parsed session with outcomes, summary, and tags."""
        # Generate summary from first user message if not already set
        if not session.summary:
            user_msgs = [m for m in session.messages if m.role == "user"]
            if user_msgs:
                first_msg = user_msgs[0].content[:200]
                session.summary = first_msg

        # Extract outcomes from tool calls
        if session.tool_calls and not session.outcomes:
            files_modified: list[str] = []
            commands_run = 0

            for tc in session.tool_calls:
                if tc.tool_name in ("Edit", "Write", "NotebookEdit"):
                    file_path = tc.arguments.get("file_path", "")
                    if file_path and file_path not in files_modified:
                        files_modified.append(file_path)
                elif tc.tool_name == "Bash":
                    commands_run += 1

            outcomes: list[SessionOutcome] = []
            if files_modified:
                outcomes.append(
                    SessionOutcome(
                        description=f"Modified {len(files_modified)} file(s)",
                        files_modified=files_modified,
                    )
                )
            if commands_run > 0:
                outcomes.append(
                    SessionOutcome(
                        description=f"Ran {commands_run} shell command(s)",
                    )
                )
            session.outcomes = outcomes

        # Generate narrative from session metadata
        from distill.narrative import enrich_narrative

        enrich_narrative(session)

        # Auto-tag based on content
        if not session.tags:
            tags: list[str] = []
            all_text = " ".join(m.content.lower() for m in session.messages)

            tag_keywords = {
                "debugging": ["bug", "fix", "error", "debug", "traceback", "exception"],
                "refactoring": ["refactor", "rename", "restructure", "reorganize", "cleanup"],
                "feature": ["implement", "add feature", "new feature", "create"],
                "testing": ["test", "pytest", "coverage", "assert"],
                "documentation": ["readme", "docstring", "documentation", "docs"],
            }
            for tag, keywords in tag_keywords.items():
                if any(kw in all_text for kw in keywords):
                    tags.append(tag)

            session.tags = tags

    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse an ISO format timestamp string.

        Args:
            ts_str: ISO format timestamp string

        Returns:
            datetime object

        Raises:
            ValueError: If timestamp cannot be parsed
        """
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

    def parse_session_file(self, file_path: Path) -> ClaudeSession | None:
        """Public method to parse a single session file.

        Args:
            file_path: Path to the .jsonl session file

        Returns:
            Parsed ClaudeSession or None if parsing fails
        """
        self._parse_errors = []
        try:
            return self._parse_session_file(file_path)
        except Exception as e:
            error_msg = f"Error parsing {file_path}: {e}"
            logger.error(error_msg)
            self._parse_errors.append(error_msg)
            return None
