"""Markdown templates for Obsidian output."""

from string import Template


# Session frontmatter template (YAML)
SESSION_FRONTMATTER = Template("""\
---
id: ${id}
date: ${date}
time: ${time}
source: ${source}
duration_minutes: ${duration}
tags:
${tags}
tools_used:
${tools}
created: ${created}
---
""")


# Session body template
SESSION_BODY = Template("""\
# ${title}

## Summary

${summary}

## Timeline

- **Started:** ${start_time}
- **Ended:** ${end_time}
- **Duration:** ${duration_str}

## Tools Used

${tools_section}

## Outcomes

${outcomes_section}

## Conversation

${conversation_section}

## Related Notes

${related_notes}
""")


# Daily summary frontmatter
DAILY_FRONTMATTER = Template("""\
---
date: ${date}
type: daily-summary
total_sessions: ${total_sessions}
total_duration_minutes: ${total_duration}
tags:
${tags}
created: ${created}
---
""")


# Daily summary body
DAILY_BODY = Template("""\
# Daily Summary - ${date}

## Overview

- **Total Sessions:** ${total_sessions}
- **Total Time:** ${total_duration_str}
- **Tools Used:** ${unique_tools_count}

## Sessions

${sessions_list}

## Statistics

### Tool Usage

${tool_stats}

### Patterns

${patterns_section}

## Notes

${notes_section}
""")


def format_tag(tag: str) -> str:
    """Format a single tag for YAML frontmatter."""
    return f"  - \"#{tag}\""


def format_yaml_list_item(item: str) -> str:
    """Format a list item for YAML."""
    return f"  - \"{item}\""


def format_obsidian_link(note_name: str, display_text: str | None = None) -> str:
    """Format an Obsidian-compatible wiki link."""
    if display_text:
        return f"[[{note_name}|{display_text}]]"
    return f"[[{note_name}]]"


def format_duration(minutes: float | None) -> str:
    """Format duration in human-readable format."""
    if minutes is None:
        return "Unknown"
    if minutes < 1:
        return f"{int(minutes * 60)} seconds"
    if minutes < 60:
        return f"{int(minutes)} minutes"
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    if remaining_minutes == 0:
        return f"{hours} hour{'s' if hours > 1 else ''}"
    return f"{hours}h {remaining_minutes}m"
