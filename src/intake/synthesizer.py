"""LLM synthesis for intake content."""

from __future__ import annotations

import logging
import subprocess

from distill.intake.config import IntakeConfig
from distill.intake.context import DailyIntakeContext
from distill.intake.prompts import get_daily_intake_prompt, get_unified_intake_prompt

logger = logging.getLogger(__name__)


class IntakeSynthesisError(Exception):
    """Raised when intake LLM synthesis fails."""


class IntakeSynthesizer:
    """Synthesizes intake content via Claude CLI."""

    def __init__(self, config: IntakeConfig) -> None:
        self._config = config

    def synthesize_daily(self, context: DailyIntakeContext, memory_context: str = "") -> str:
        """Transform daily intake context into a research digest.

        Uses the unified prompt when sessions or seeds are present,
        falling back to the standard reading-only prompt otherwise.

        Args:
            context: The assembled daily intake context.
            memory_context: Rendered working memory for continuity.

        Returns:
            Synthesized prose as markdown.
        """
        if context.has_sessions or context.has_seeds:
            system_prompt = get_unified_intake_prompt(
                target_word_count=self._config.target_word_count,
                memory_context=memory_context,
                has_sessions=context.has_sessions,
                has_seeds=context.has_seeds,
            )
        else:
            system_prompt = get_daily_intake_prompt(
                target_word_count=self._config.target_word_count,
                memory_context=memory_context,
            )
        user_prompt = context.combined_text
        return self._call_claude(system_prompt, user_prompt, f"intake {context.date.isoformat()}")

    def _call_claude(self, system_prompt: str, user_prompt: str, label: str) -> str:
        """Call Claude CLI with prompt piped via stdin.

        Uses stdin to avoid OS argument length limits when the prompt
        is very large (e.g. hundreds of RSS articles).
        """
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        cmd: list[str] = ["claude", "-p"]
        if self._config.model:
            cmd.extend(["--model", self._config.model])

        logger.debug("Calling Claude CLI for intake synthesis (%s)", label)

        try:
            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=self._config.claude_timeout,
            )
        except FileNotFoundError as e:
            raise IntakeSynthesisError("Claude CLI not found -- is 'claude' on the PATH?") from e
        except subprocess.TimeoutExpired as e:
            raise IntakeSynthesisError(
                f"Claude CLI timed out after {self._config.claude_timeout}s"
            ) from e
        except OSError as e:
            raise IntakeSynthesisError(f"Failed to run Claude CLI: {e}") from e

        if result.returncode != 0:
            err_text = result.stderr.strip() if result.stderr else ""
            raise IntakeSynthesisError(f"Claude CLI exited {result.returncode}: {err_text}")

        return result.stdout.strip()
