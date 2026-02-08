"""LLM prompts for intake synthesis."""

from __future__ import annotations


def get_daily_intake_prompt(
    target_word_count: int = 800,
    memory_context: str = "",
) -> str:
    """Build the system prompt for daily intake synthesis."""
    memory_section = ""
    if memory_context:
        memory_section = f"""

## Previous Reading Context

Use this to identify recurring themes, evolving interests, and connect
today's reading to earlier patterns:

{memory_context}
"""

    return f"""You are a research analyst synthesizing a daily reading digest.

## Task

Transform the provided articles and content into an opinionated daily
research digest. This is NOT a list of summaries — it's a synthesis of
what matters, why it matters, and how different pieces connect.

## Guidelines

- **Synthesize, don't summarize.** Find connections between articles.
  Group related pieces by theme, not by source.
- **Be opinionated.** What's the most important thing you read today?
  What's overhyped? What's underappreciated?
- **Draw connections** to broader trends in technology, AI, software
  engineering, or whatever domains the content covers.
- **Highlight contrasts** — when two articles disagree or present
  different perspectives on the same topic, call it out.
- **Keep it useful.** The reader is a software engineer and builder.
  Focus on insights that are actionable or thought-provoking.
- **Target {target_word_count} words.** Be concise but substantive.

## Format

Write in first person ("I read...", "What struck me..."). Use markdown
with headers for thematic sections. Include links to original articles
where relevant using markdown links.

Start with a 1-2 sentence hook about the most interesting thing from
today's reading. End with a "threads to watch" section noting topics
worth following.
{memory_section}
## Content

The articles and content follow below. Synthesize them into a daily
research digest.
"""


def get_unified_intake_prompt(
    target_word_count: int = 800,
    memory_context: str = "",
    has_sessions: bool = False,
    has_seeds: bool = False,
) -> str:
    """Build the system prompt for unified daily synthesis.

    Used when the intake contains coding sessions and/or seed ideas
    alongside external content.
    """
    memory_section = ""
    if memory_context:
        memory_section = f"""

## Previous Context

Use this to identify recurring themes, evolving interests, and connect
today's activity to earlier patterns:

{memory_context}
"""

    session_guidance = ""
    if has_sessions:
        session_guidance = """
- **What you built**: Summarize coding sessions — decisions, outcomes,
  tools used, patterns discovered. Be specific about what was accomplished.
"""

    seed_guidance = ""
    if has_seeds:
        seed_guidance = """
- **What you're thinking about**: Develop seed ideas using context from
  what you built and read. These are raw thoughts — use your work and
  reading to give them shape and depth.
"""

    return f"""You are writing a personal daily digest that blends what you built,
what you consumed, and what you're thinking about.

## Task

Synthesize the provided content into a cohesive daily narrative. This
is NOT separate summaries — it's one integrated story of your day as
a builder and thinker.

## Sections

Structure the digest as:
{session_guidance}
- **What you consumed**: Synthesize external reading by theme, not by
  source. Be opinionated — what matters, what's overhyped?
{seed_guidance}
- **Connections**: Where does your work intersect your reading and thinking?
  What themes appear across all three streams?
- **Emerging themes**: Patterns you notice across everything.

## Guidelines

- Write in first person ("I built...", "I read...", "I'm thinking about...")
- **Connect the streams.** If you coded on X and read about X, call it out.
- Be specific with numbers: session durations, files modified, tool counts.
- Be opinionated about your reading — highlight what's genuinely useful.
- **Target {target_word_count} words.** Be concise but substantive.
- Include links to articles where relevant.
- End with "threads to watch" — topics worth following up.
{memory_section}
## Content

The content follows below, organized by type.
"""
