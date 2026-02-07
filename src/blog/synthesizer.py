"""Claude CLI integration for blog synthesis.

Calls ``claude -p`` to transform assembled blog context into publishable
prose. Follows the same subprocess pattern as journal/synthesizer.py.
"""

from __future__ import annotations

import logging
import subprocess

from distill.blog.config import BlogConfig, BlogPostType
from distill.blog.context import ThematicBlogContext, WeeklyBlogContext
from distill.blog.prompts import get_blog_prompt

logger = logging.getLogger(__name__)


class BlogSynthesisError(Exception):
    """Raised when blog LLM synthesis fails."""


class BlogSynthesizer:
    """Synthesizes blog posts via Claude CLI."""

    def __init__(self, config: BlogConfig) -> None:
        self._config = config

    def synthesize_weekly(self, context: WeeklyBlogContext) -> str:
        """Transform weekly context into blog prose.

        Args:
            context: Assembled weekly blog context.

        Returns:
            Raw prose string from Claude including Mermaid blocks.

        Raises:
            BlogSynthesisError: If the CLI call fails.
        """
        system_prompt = get_blog_prompt(
            BlogPostType.WEEKLY,
            self._config.target_word_count,
        )
        user_prompt = _render_weekly_prompt(context)
        return self._call_claude(system_prompt, user_prompt, f"weekly W{context.week}")

    def synthesize_thematic(self, context: ThematicBlogContext) -> str:
        """Transform thematic context into blog prose.

        Args:
            context: Assembled thematic blog context.

        Returns:
            Raw prose string from Claude including Mermaid blocks.

        Raises:
            BlogSynthesisError: If the CLI call fails.
        """
        system_prompt = get_blog_prompt(
            BlogPostType.THEMATIC,
            self._config.target_word_count,
            theme_title=context.theme.title,
        )
        user_prompt = _render_thematic_prompt(context)
        return self._call_claude(system_prompt, user_prompt, context.theme.slug)

    def _call_claude(self, system_prompt: str, user_prompt: str, label: str) -> str:
        """Call Claude CLI with combined prompt."""
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        cmd: list[str] = ["claude", "-p"]
        if self._config.model:
            cmd.extend(["--model", self._config.model])
        cmd.append(full_prompt)

        logger.debug("Calling Claude CLI for blog synthesis (%s)", label)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._config.claude_timeout,
            )
        except FileNotFoundError as e:
            raise BlogSynthesisError(
                "Claude CLI not found -- is 'claude' on the PATH?"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise BlogSynthesisError(
                f"Claude CLI timed out after {self._config.claude_timeout}s"
            ) from e
        except OSError as e:
            raise BlogSynthesisError(f"Failed to run Claude CLI: {e}") from e

        if result.returncode != 0:
            err_text = result.stderr.strip() if result.stderr else ""
            raise BlogSynthesisError(
                f"Claude CLI exited {result.returncode}: {err_text}"
            )

        return result.stdout.strip()


def _render_weekly_prompt(context: WeeklyBlogContext) -> str:
    """Render the user prompt for weekly synthesis."""
    lines: list[str] = []
    lines.append(f"# Week {context.year}-W{context.week:02d}")
    lines.append(
        f"({context.week_start.isoformat()} to {context.week_end.isoformat()})"
    )
    lines.append(f"Total sessions: {context.total_sessions}")
    lines.append(f"Total duration: {context.total_duration_minutes:.0f} minutes")

    if context.projects:
        lines.append(f"Projects: {', '.join(context.projects)}")
    lines.append("")

    if context.working_memory:
        lines.append(context.working_memory)
        lines.append("")

    lines.append("# Daily Journal Entries")
    lines.append("")
    lines.append(context.combined_prose)

    return "\n".join(lines)


def _render_thematic_prompt(context: ThematicBlogContext) -> str:
    """Render the user prompt for thematic synthesis."""
    lines: list[str] = []
    lines.append(f"# Theme: {context.theme.title}")
    lines.append(f"Description: {context.theme.description}")
    lines.append(
        f"Evidence from {context.evidence_count} journal entries "
        f"({context.date_range[0].isoformat()} to {context.date_range[1].isoformat()})"
    )
    lines.append("")

    if context.relevant_threads:
        lines.append("## Relevant Ongoing Threads")
        for thread in context.relevant_threads:
            lines.append(
                f"- {thread.name} ({thread.status}): {thread.summary}"
            )
        lines.append("")

    lines.append("# Evidence from Journal Entries")
    lines.append("")
    lines.append(context.combined_evidence)

    return "\n".join(lines)
