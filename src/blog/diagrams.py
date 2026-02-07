"""Mermaid diagram extraction and validation from LLM output.

Post-processes blog prose to validate and clean Mermaid blocks,
ensuring only syntactically valid diagrams remain in the output.
"""

from __future__ import annotations

import re

VALID_DIAGRAM_TYPES = frozenset({
    "graph",
    "flowchart",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "statediagram-v2",
    "erdiagram",
    "gantt",
    "pie",
    "timeline",
    "gitgraph",
    "mindmap",
})


def extract_mermaid_blocks(prose: str) -> list[str]:
    """Extract ```mermaid ... ``` blocks from prose.

    Returns the content of each block (without the fence markers).
    """
    pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    return [m.group(1).strip() for m in pattern.finditer(prose)]


def validate_mermaid(block: str) -> bool:
    """Basic syntax validation for a Mermaid block.

    Checks that the block starts with a recognized diagram type keyword.
    """
    if not block.strip():
        return False

    first_line = block.strip().splitlines()[0].strip().lower()

    # Check for diagram type at start of first line
    for dtype in VALID_DIAGRAM_TYPES:
        if first_line.startswith(dtype):
            return True

    # Some diagram types use a hyphenated form
    return bool(first_line.startswith("state diagram"))


def clean_diagrams(prose: str) -> str:
    """Remove invalid Mermaid blocks from prose, keeping valid ones.

    Invalid blocks are replaced with empty string (removing the entire
    fenced block). Valid blocks are left in place.
    """
    def _replace(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        if validate_mermaid(content):
            return match.group(0)  # Keep valid blocks as-is
        return ""

    pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    result = pattern.sub(_replace, prose)

    # Clean up any double blank lines left by removed blocks
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result
