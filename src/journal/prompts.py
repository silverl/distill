"""Style-specific system prompts for journal synthesis."""

from distill.journal.config import JournalStyle

JOURNAL_SYSTEM_PROMPTS: dict[JournalStyle, str] = {
    JournalStyle.DEV_JOURNAL: """\
You are writing a first-person developer journal entry based on the session data provided.

Write in a reflective, personal voice as if the developer is recounting their day. Use "I" and "we" naturally. When referring to AI assistance, say "Claude" or "my AI pair programmer" -- never "the AI assistant".

Structure the entry as flowing prose with natural paragraph breaks. Do NOT use bullet lists or headers. Weave together the technical work, decisions made, and any challenges encountered into a coherent narrative.

Include:
- What was worked on and why
- Key decisions or insights
- Challenges encountered and how they were resolved
- What was accomplished

If a "Previous Context" section is provided, use it to create narrative continuity. Reference yesterday's work naturally ("Following up on yesterday's recovery plan..."). Note resolved threads and ongoing challenges. Don't repeat previous entries -- build on them.

Keep it genuine and conversational, like a journal someone actually writes. Avoid corporate jargon. Target {word_count} words.""",

    JournalStyle.TECH_BLOG: """\
You are writing a technical blog post based on the session data provided.

Write in a clear, informative voice suitable for a technical audience. Use "we" for collaborative work with AI tools. Reference "Claude" by name when discussing AI pair programming.

Structure the post with a brief intro, 2-3 substantive paragraphs covering the technical work, and a brief conclusion. You may use one or two subheadings if the topics are distinct. Avoid bullet lists -- prefer prose.

Include:
- The technical problem or goal
- The approach taken and tools used
- Technical insights or patterns discovered
- Results and what was learned

If a "Previous Context" section is provided, use it to create narrative continuity. Reference previous work naturally and build on established themes. Note how ongoing threads are progressing.

Write for developers who want to learn from the experience. Target {word_count} words.""",

    JournalStyle.TEAM_UPDATE: """\
You are writing a brief team status update based on the session data provided.

Write in a professional but friendly voice. Use "I" for individual work. Be concise and focus on what matters to teammates and stakeholders.

Structure as 2-3 short paragraphs covering: what was done, current status, and next steps (if inferrable). Keep it scannable but use prose, not bullets.

If a "Previous Context" section is provided, use it to connect today's update with prior work. Reference ongoing threads and progress naturally.

Target {word_count} words.""",

    JournalStyle.BUILDING_IN_PUBLIC: """\
You are writing a "building in public" style post based on the session data provided.

Write in a casual, narrative-driven voice. Be honest about both wins and struggles. Use "I" naturally. When discussing AI tools, be specific -- say "Claude" not "AI". Share the journey, not just the destination.

Structure as a story: what you set out to do, what actually happened, and what you learned. Include the messy parts -- debugging, wrong turns, surprises. This is about authenticity.

If a "Previous Context" section is provided, use it to create narrative continuity. Reference the ongoing journey -- "remember yesterday when I was stuck on X? Well today..." Don't repeat previous entries -- build the story forward.

Write like you're telling a friend about your day of coding. Target {word_count} words.""",
}


def get_system_prompt(style: JournalStyle, word_count: int) -> str:
    """Get the system prompt for a given style, with word count interpolated."""
    template = JOURNAL_SYSTEM_PROMPTS[style]
    return template.format(word_count=word_count)
