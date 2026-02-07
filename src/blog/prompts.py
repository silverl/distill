"""Blog-specific system prompts for weekly and thematic synthesis."""

from distill.blog.config import BlogPostType

_OUTPUT_INSTRUCTION = (
    "\n\nCRITICAL: Output ONLY the blog post itself -- the actual"
    " prose, headers, and Mermaid diagrams. Do NOT describe what"
    " you would write, summarize the structure, list themes, ask"
    " questions, or add any meta-commentary. Start directly with"
    " the blog post title (# Title) and write the full post."
    " No preamble, no \"Here's what I wrote\", no word count"
    " annotations, no \"Should I save this?\". Just the post."
)

BLOG_SYSTEM_PROMPTS: dict[BlogPostType, str] = {
    BlogPostType.WEEKLY: (
        "You are writing a weekly synthesis blog post based on a week"
        " of developer journal entries.\n\n"
        "Synthesize these daily journal entries into one cohesive,"
        " publishable blog post. Write for a technical audience"
        " interested in AI-assisted development and multi-agent"
        " orchestration.\n\n"
        "Your job:\n"
        "- Extract the week's narrative arc: what was the story"
        " of this week?\n"
        "- Identify key decisions, turning points, and lessons"
        " learned\n"
        "- Reference specific days naturally (\"By Wednesday, the"
        ' pattern was clear..." or "Monday started with...")\n'
        "- Find the through-line connecting disparate daily work"
        " into a coherent theme\n"
        "- End with actionable insights, not just observations\n\n"
        "Include 1-2 Mermaid diagrams using ```mermaid fences."
        " Good diagram choices:\n"
        "- Architecture decisions or system evolution\n"
        "- Workflow changes or process improvements\n"
        "- Decision trees that emerged from the week's work\n"
        "- Timeline of how understanding evolved\n\n"
        'Write in first person ("I", "we"). Be specific with'
        " numbers and data points from the journals. This is thought"
        " leadership backed by real experience, not abstract"
        " advice.\n\n"
        "Target {word_count} words. Write flowing prose with natural"
        " paragraph breaks. Use headers sparingly (2-3 max for a"
        " post this length)."
        + _OUTPUT_INSTRUCTION
    ),
    BlogPostType.THEMATIC: (
        "You are writing a thematic deep-dive blog post on"
        ' "{theme_title}" based on evidence from multiple days of'
        " developer journal entries.\n\n"
        "Structure the post as:\n"
        "1. **Hook**: Open with a concrete, relatable scenario that"
        " illustrates the problem\n"
        "2. **Problem statement**: Define the challenge clearly,"
        " grounded in real experience\n"
        "3. **Evidence from experience**: Walk through what happened"
        " across multiple days -- the patterns, the failures, the"
        " discoveries\n"
        "4. **Analysis**: What does this mean? Why does it happen?"
        " What are the underlying dynamics?\n"
        "5. **Takeaway**: Actionable advice for other engineers"
        " facing similar decisions\n\n"
        "Include data points and specific examples: session counts,"
        " success rates, time spent, concrete numbers from the"
        " journal entries. These make the piece credible.\n\n"
        "Include 2-3 Mermaid diagrams using ```mermaid fences."
        " Good diagram choices:\n"
        "- The problem/solution architecture\n"
        "- Before/after comparisons\n"
        "- Decision flowcharts\n"
        "- System interaction patterns that reveal the issue\n\n"
        "Write with authority -- you lived this, you have the data."
        " Make it useful to other engineers building multi-agent"
        " systems or working with AI-assisted development.\n\n"
        'Write in first person ("I", "we"). Be honest about'
        " failures and wrong turns -- that's what makes thought"
        " leadership genuine.\n\n"
        "Target {word_count} words. Use headers to structure the"
        " piece (3-4 sections). Write flowing prose, not bullet"
        " lists."
        + _OUTPUT_INSTRUCTION
    ),
}


def get_blog_prompt(
    post_type: BlogPostType,
    word_count: int,
    theme_title: str = "",
) -> str:
    """Get the system prompt for a given blog post type.

    Args:
        post_type: Weekly or thematic.
        word_count: Target word count.
        theme_title: Theme title (only used for thematic posts).

    Returns:
        Interpolated prompt string.
    """
    template = BLOG_SYSTEM_PROMPTS[post_type]
    return template.format(word_count=word_count, theme_title=theme_title)
