"""Claude CLI integration for journal synthesis (Phase 2).

Calls ``claude -p`` to transform compressed session context into
narrative prose. Pattern follows VerMAS LLMService.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import date

from distill.journal.config import JournalConfig
from distill.journal.context import DailyContext
from distill.journal.memory import DailyMemoryEntry, MemoryThread
from distill.journal.prompts import get_system_prompt

logger = logging.getLogger(__name__)


class SynthesisError(Exception):
    """Raised when LLM synthesis fails."""


class JournalSynthesizer:
    """Synthesizes journal entries via Claude CLI."""

    def __init__(self, config: JournalConfig) -> None:
        self._config = config

    def synthesize(self, context: DailyContext) -> str:
        """Transform daily context into narrative prose.

        Args:
            context: Compressed daily session context.

        Returns:
            Raw prose string from Claude.

        Raises:
            SynthesisError: If the CLI call fails.
        """
        system_prompt = get_system_prompt(
            self._config.style, self._config.target_word_count
        )
        user_prompt = context.render_text()
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        cmd: list[str] = ["claude", "-p"]
        if self._config.model:
            cmd.extend(["--model", self._config.model])
        cmd.append(full_prompt)

        logger.debug("Calling Claude CLI for journal synthesis (%s)", context.date)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._config.claude_timeout,
            )
        except FileNotFoundError as e:
            raise SynthesisError(
                "Claude CLI not found -- is 'claude' on the PATH?"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise SynthesisError(
                f"Claude CLI timed out after {self._config.claude_timeout}s"
            ) from e
        except OSError as e:
            raise SynthesisError(f"Failed to run Claude CLI: {e}") from e

        if result.returncode != 0:
            err_text = result.stderr.strip() if result.stderr else ""
            raise SynthesisError(
                f"Claude CLI exited {result.returncode}: {err_text}"
            )

        return result.stdout.strip()

    def extract_memory(
        self, prose: str, target_date: date
    ) -> tuple[DailyMemoryEntry, list[MemoryThread]]:
        """Extract structured memory from generated prose.

        Makes a second LLM call to pull out themes, insights, decisions,
        open questions, and ongoing threads from the journal prose.

        Args:
            prose: The generated journal prose.
            target_date: The date the prose covers.

        Returns:
            Tuple of (daily entry, list of threads).

        Raises:
            SynthesisError: If the CLI call fails.
        """
        extraction_prompt = f"""\
Extract structured memory from this journal entry dated {target_date.isoformat()}.

Return ONLY valid JSON with this exact structure (no markdown fences, no commentary):
{{
  "themes": ["3-5 high-level themes from today"],
  "key_insights": ["what was learned or discovered"],
  "decisions_made": ["what was decided"],
  "open_questions": ["unresolved things"],
  "tomorrow_intentions": ["what was planned or implied for next steps"],
  "threads": [
    {{
      "name": "short-kebab-case-name",
      "summary": "current state of this ongoing thread",
      "status": "open or resolved"
    }}
  ]
}}

Threads are ongoing narratives that span multiple days -- problems being debugged,
features being built, patterns being established. Only include threads if the prose
describes something clearly ongoing or recently resolved.

Journal entry:
{prose}"""

        cmd: list[str] = ["claude", "-p"]
        if self._config.model:
            cmd.extend(["--model", self._config.model])
        cmd.append(extraction_prompt)

        logger.debug("Extracting memory for %s", target_date)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._config.claude_timeout,
            )
        except FileNotFoundError as e:
            raise SynthesisError(
                "Claude CLI not found -- is 'claude' on the PATH?"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise SynthesisError(
                f"Claude CLI timed out after {self._config.claude_timeout}s"
            ) from e
        except OSError as e:
            raise SynthesisError(f"Failed to run Claude CLI: {e}") from e

        if result.returncode != 0:
            err_text = result.stderr.strip() if result.stderr else ""
            raise SynthesisError(
                f"Claude CLI exited {result.returncode}: {err_text}"
            )

        raw = result.stdout.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[: -3].rstrip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SynthesisError(
                f"Memory extraction returned invalid JSON: {e}"
            ) from e

        entry = DailyMemoryEntry(
            date=target_date,
            themes=data.get("themes", []),
            key_insights=data.get("key_insights", []),
            decisions_made=data.get("decisions_made", []),
            open_questions=data.get("open_questions", []),
            tomorrow_intentions=data.get("tomorrow_intentions", []),
        )

        threads: list[MemoryThread] = []
        for t in data.get("threads", []):
            threads.append(
                MemoryThread(
                    name=t.get("name", "unnamed"),
                    summary=t.get("summary", ""),
                    first_mentioned=target_date,
                    last_mentioned=target_date,
                    status=t.get("status", "open"),
                )
            )

        return entry, threads
