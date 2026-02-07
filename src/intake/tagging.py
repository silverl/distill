"""Keyword extraction for content items that lack tags.

Uses word frequency analysis with position weighting and stopword
filtering to extract the most relevant keywords from title + body
text.  No external dependencies — stdlib only.
"""

from __future__ import annotations

import re
import string
from collections import Counter

from distill.intake.models import ContentItem

# ── Built-in English stopword list ────────────────────────────────────
# Covers the most common English function words, pronouns, prepositions,
# articles, conjunctions, and generic web/tech filler.
STOPWORDS: frozenset[str] = frozenset(
    {
        # Articles & determiners
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "some",
        "any",
        "each",
        "every",
        "all",
        "both",
        "few",
        "more",
        "most",
        "other",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        # Pronouns
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
        "ourselves",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "her",
        "hers",
        "herself",
        "it",
        "its",
        "itself",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        # Prepositions
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "about",
        "against",
        "between",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "to",
        "from",
        "up",
        "down",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "into",
        "upon",
        "without",
        "within",
        "along",
        "across",
        "around",
        # Conjunctions
        "and",
        "but",
        "or",
        "if",
        "while",
        "because",
        "as",
        "until",
        "although",
        "since",
        "unless",
        "so",
        "yet",
        "than",
        "when",
        "where",
        "how",
        "why",
        # Verbs (auxiliary / very common)
        "be",
        "is",
        "am",
        "are",
        "was",
        "were",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "need",
        "dare",
        "get",
        "got",
        "gets",
        "getting",
        "make",
        "made",
        "makes",
        "let",
        "say",
        "said",
        "says",
        "go",
        "goes",
        "went",
        "gone",
        "going",
        "come",
        "came",
        "take",
        "took",
        "taken",
        "know",
        "knew",
        "known",
        "see",
        "saw",
        "seen",
        "think",
        "use",
        "used",
        "using",
        "uses",
        "want",
        "also",
        "well",
        "just",
        "now",
        "way",
        "like",
        "look",
        "give",
        "find",
        "tell",
        "work",
        "seem",
        "feel",
        "try",
        "leave",
        "call",
        "keep",
        "put",
        "show",
        "turn",
        "begin",
        "help",
        "run",
        "move",
        "live",
        "set",
        # Adverbs & misc
        "here",
        "there",
        "very",
        "really",
        "still",
        "already",
        "even",
        "much",
        "many",
        "too",
        "quite",
        "rather",
        "enough",
        "ever",
        "never",
        "always",
        "often",
        "sometimes",
        "usually",
        "however",
        "therefore",
        "instead",
        "perhaps",
        "though",
        "actually",
        "especially",
        "basically",
        "simply",
        "almost",
        "else",
        "probably",
        "certainly",
        "indeed",
        "anyway",
        # Generic web/content filler
        "new",
        "first",
        "last",
        "long",
        "great",
        "good",
        "right",
        "old",
        "big",
        "high",
        "small",
        "large",
        "next",
        "early",
        "young",
        "important",
        "different",
        "able",
        "best",
        "better",
        "sure",
        "free",
        "true",
        "real",
        "full",
        "back",
        "part",
        "read",
        "post",
        "blog",
        "article",
        "page",
        "site",
        "link",
        "click",
        "share",
        "comments",
        "comment",
        "reply",
        "subscribe",
        "newsletter",
        "via",
        "one",
        "two",
        "three",
        "don",
        "doesn",
        "didn",
        "won",
        "isn",
        "aren",
        "wasn",
        "weren",
        "hasn",
        "haven",
        "hadn",
        "couldn",
        "shouldn",
        "wouldn",
        "thing",
        "things",
        "people",
        "time",
        "year",
        "years",
        "day",
        "days",
        "lot",
        "end",
        "case",
        "point",
        "number",
        "world",
        "something",
        "nothing",
        "everything",
        "anything",
    }
)

# Characters to strip from word boundaries
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)

# Minimum word length after normalization
_MIN_WORD_LEN = 3

# Title words receive this multiplier to their frequency score
_TITLE_WEIGHT = 3


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens, stripping punctuation.

    Returns only tokens with length >= ``_MIN_WORD_LEN`` that are not
    purely numeric and not in the stopword list.
    """
    # Replace common non-breaking/special whitespace with regular space
    text = re.sub(r"[\u00a0\u2003\u2002\t\r\n]+", " ", text)
    raw_tokens = text.lower().split()

    result: list[str] = []
    for raw in raw_tokens:
        word = raw.translate(_PUNCT_TABLE)
        if len(word) < _MIN_WORD_LEN:
            continue
        if word.isdigit():
            continue
        if word in STOPWORDS:
            continue
        result.append(word)
    return result


def extract_tags(title: str, body: str, max_tags: int = 5) -> list[str]:
    """Extract the most relevant keywords from title and body text.

    Title words are weighted higher than body words.  Tags are returned
    in descending order of relevance (frequency * position weight).

    Args:
        title: The content title.
        body: The content body text.
        max_tags: Maximum number of tags to return.

    Returns:
        A list of lowercase keyword strings, sorted by relevance.
    """
    if not title and not body:
        return []

    title_tokens = _tokenize(title)
    body_tokens = _tokenize(body)

    # Count weighted frequencies
    freq: Counter[str] = Counter()
    for token in title_tokens:
        freq[token] += _TITLE_WEIGHT
    for token in body_tokens:
        freq[token] += 1

    if not freq:
        return []

    # Return the top-N most common keywords
    return [tag for tag, _count in freq.most_common(max_tags)]


def enrich_tags(items: list[ContentItem]) -> list[ContentItem]:
    """Populate tags for content items that have none.

    Iterates over *items* and, for each one whose ``tags`` list is
    empty, calls :func:`extract_tags` on its title and body to fill
    in auto-generated tags.  Items that already have tags are left
    untouched.

    The list is modified in place **and** returned for convenience.

    Args:
        items: Content items to enrich.

    Returns:
        The same list with tags populated where they were missing.
    """
    for item in items:
        if not item.tags:
            item.tags = extract_tags(item.title, item.body)
    return items
