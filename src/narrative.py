"""Narrative generation for session insights.

Generates human-readable narrative summaries from session data,
transforming raw tool/outcome data into coherent stories about
what was accomplished.
"""

from __future__ import annotations

import re

from distill.parsers.models import BaseSession

# XML tag pattern for sanitization
_XML_TAG_RE = re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^>]*)?>")

# Patterns that indicate raw prompt / command text rather than real summaries
_RAW_PROMPT_PATTERNS = [
    re.compile(r"<\w[\w-]*>"),  # XML-style tags
    re.compile(r"^(analyze|init|help|run|build|test|start|stop|deploy|status)\s*\w*$", re.IGNORECASE),
    re.compile(r"^/\w+"),  # slash commands
]


def _is_low_quality_summary(text: str) -> bool:
    """Check if a summary is low quality and should be replaced."""
    if not text or not text.strip():
        return True
    text = text.strip()
    # Too short
    if len(text.split()) < 5:
        return True
    # Contains XML tags
    if _XML_TAG_RE.search(text):
        return True
    # Looks like a raw command
    for pattern in _RAW_PROMPT_PATTERNS:
        if pattern.match(text) and len(text.split()) <= 3:
            return True
    # Is just a file path
    if re.match(r"^[\w./\\-]+\.\w{1,5}$", text):
        return True
    return False


def _sanitize_text(text: str) -> str:
    """Strip XML tags and clean up text for narrative use."""
    cleaned = _XML_TAG_RE.sub("", text)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _generate_metadata_narrative(session: BaseSession) -> str:
    """Generate a narrative purely from session metadata when summary is unusable."""
    parts: list[str] = []

    # Duration
    duration = session.duration_minutes
    duration_str = ""
    if duration is not None:
        if duration < 1:
            duration_str = "Brief"
        elif duration < 60:
            duration_str = f"{int(duration)}-minute"
        else:
            hours = int(duration // 60)
            mins = int(duration % 60)
            duration_str = f"{hours}h {mins}m" if mins else f"{hours}-hour"

    # Project context
    project_str = ""
    if session.project and session.project not in ("(unknown)", "(unassigned)", "unknown"):
        project_str = f"in {session.project}"

    # Build opening clause
    if duration_str and project_str:
        parts.append(f"{duration_str} session {project_str}")
    elif duration_str:
        parts.append(f"{duration_str} coding session")
    elif project_str:
        parts.append(f"Session {project_str}")
    else:
        parts.append("Coding session")

    # Tools used
    if session.tools_used:
        top_tools = sorted(session.tools_used, key=lambda t: t.count, reverse=True)[:4]
        tool_parts = [f"{t.name} ({t.count}x)" for t in top_tools]
        total_calls = sum(t.count for t in session.tools_used)
        parts[0] += f" using {', '.join(tool_parts)}"
        if total_calls > len(top_tools):
            parts[0] += f" across {total_calls} total tool calls"

    parts[0] += "."

    # Outcomes
    if session.outcomes:
        all_files: list[str] = []
        for o in session.outcomes:
            all_files.extend(o.files_modified)
        successes = [o for o in session.outcomes if o.success]
        if all_files:
            parts.append(f"Modified {len(all_files)} file(s)")
            # Add breadth description
            dirs = {f.rsplit("/", 1)[0] for f in all_files if "/" in f}
            if len(dirs) > 1:
                parts[-1] += f" across {len(dirs)} directories"
            parts[-1] += "."
        if successes:
            descs = [o.description for o in successes[:2]]
            parts.append("Accomplished: " + "; ".join(descs) + ".")
        failures = [o for o in session.outcomes if not o.success]
        if failures:
            descs = [o.description for o in failures[:2]]
            parts.append("Incomplete: " + "; ".join(descs) + ".")

    # Tags
    if session.tags:
        parts.append(f"Activity type: {', '.join(session.tags)}.")

    # Workflow context
    if session.cycle_info:
        ci = session.cycle_info
        if ci.task_name:
            parts.append(f"Task: {ci.task_name}.")
        if ci.outcome and ci.outcome != "unknown":
            parts.append(f"Workflow outcome: {ci.outcome}.")

    return " ".join(parts)


def generate_narrative(session: BaseSession) -> str:
    """Generate a human-readable narrative for a session.

    Combines summary, outcomes, tools used, tags, and task context
    into a coherent paragraph describing what happened in the session.
    If the session summary is low quality (contains XML tags, literal
    commands, etc.), falls back to generating from metadata alone.

    Args:
        session: The session to narrate.

    Returns:
        A human-readable narrative string.
    """
    parts: list[str] = []

    # Determine if we have a usable summary or task description
    has_good_opening = False

    # Opening: what the session was about
    if session.task_description and not _is_low_quality_summary(session.task_description):
        cleaned = _sanitize_text(session.task_description.strip()[:200])
        if cleaned and len(cleaned.split()) >= 5:
            parts.append(f"Worked on: {cleaned}.")
            has_good_opening = True
    if not has_good_opening and session.summary and not _is_low_quality_summary(session.summary):
        summary = _sanitize_text(session.summary.strip())
        if len(summary) > 200:
            summary = summary[:197] + "..."
        if summary and len(summary.split()) >= 5:
            parts.append(summary)
            has_good_opening = True

    # If no good opening from summary/task, generate purely from metadata
    if not has_good_opening:
        return _generate_metadata_narrative(session)

    # Duration context
    duration = session.duration_minutes
    if duration is not None:
        if duration < 1:
            parts.append("This was a brief interaction.")
        elif duration < 10:
            parts.append(f"The session lasted about {int(duration)} minutes.")
        elif duration < 60:
            parts.append(f"The session ran for {int(duration)} minutes.")
        else:
            hours = int(duration // 60)
            mins = int(duration % 60)
            if mins:
                parts.append(f"The session spanned {hours}h {mins}m.")
            else:
                parts.append(f"The session spanned {hours} hour{'s' if hours > 1 else ''}.")

    # Tools narrative
    if session.tools_used:
        top_tools = sorted(session.tools_used, key=lambda t: t.count, reverse=True)[:3]
        tool_parts = [f"{t.name} ({t.count}x)" for t in top_tools]
        parts.append(f"Primary tools: {', '.join(tool_parts)}.")

    # Outcomes narrative
    if session.outcomes:
        successes = [o for o in session.outcomes if o.success]
        failures = [o for o in session.outcomes if not o.success]
        if successes:
            outcome_descriptions = [o.description for o in successes[:3]]
            parts.append("Accomplished: " + "; ".join(outcome_descriptions) + ".")
        if failures:
            fail_descriptions = [o.description for o in failures[:2]]
            parts.append("Incomplete: " + "; ".join(fail_descriptions) + ".")

        # Files modified
        all_files: list[str] = []
        for o in session.outcomes:
            all_files.extend(o.files_modified)
        if all_files:
            parts.append(f"Touched {len(all_files)} file(s).")

    # Tags as activity context
    if session.tags:
        parts.append(f"Activity type: {', '.join(session.tags)}.")

    # VerMAS workflow context
    if session.cycle_info:
        ci = session.cycle_info
        if ci.outcome and ci.outcome != "unknown":
            parts.append(f"Workflow outcome: {ci.outcome}.")

    return " ".join(parts)


def enrich_narrative(session: BaseSession) -> None:
    """Populate the session's narrative field if empty or low quality.

    Modifies the session in-place.

    Args:
        session: The session to enrich.
    """
    if not session.narrative or _is_low_quality_summary(session.narrative):
        generated = generate_narrative(session)
        # Only replace if we actually produce a better narrative
        if generated and len(generated.split()) > len((session.narrative or "").split()):
            session.narrative = generated
