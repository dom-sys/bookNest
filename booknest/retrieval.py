"""Find relevant book passages without searching unread chapters.

Starter book format: a list of chapters in reading order. Each chapter is
itself a list of paragraph strings. Chapter and paragraph numbers start at 1.
This module does not check ownership or enforce account question quotas yet.
"""

from collections import Counter
from math import sqrt
import re


# A small starter list: keep meaningful words such as "not" and "never".
STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "be", "been", "do", "does", "did",
    "who", "what", "when", "where", "why", "how",
}


def tokens(text):
    """Return lowercase words, excluding punctuation and common stop words."""
    words = re.findall(r"\w+", text.lower())
    meaningful_words = []
    for word in words:
        if word not in STOP_WORDS:
            meaningful_words.append(word)
    return meaningful_words


def similarity(question_words, passage_words):
    """Compare word counts using cosine similarity (a score from 0 to 1)."""
    question_counts = Counter(question_words)
    passage_counts = Counter(passage_words)
    shared_words = sum(
        count * passage_counts[word]
        for word, count in question_counts.items()
    )
    question_length = sqrt(sum(count ** 2 for count in question_counts.values()))
    passage_length = sqrt(sum(count ** 2 for count in passage_counts.values()))
    if question_length == 0 or passage_length == 0:
        return 0.0
    return shared_words / (question_length * passage_length)


def find_passages(chapters, completed_chapter, question, limit=3):
    """Return ranked passage dictionaries from completed chapters only.

    The limit is the number of passages returned, not a user question quota.
    Zero completed chapters or no matching words produces an empty list.
    """
    if type(completed_chapter) is not int or not 0 <= completed_chapter <= len(chapters):
        raise ValueError("Completed chapter must be a whole number within this book.")
    if type(limit) is not int or limit < 1:
        raise ValueError("Passage limit must be a positive whole number.")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError("Enter a question between 1 and 2,000 characters.")

    question_words = tokens(question)
    matches = []

    # Filter FIRST: unread chapters never enter the search or its results.
    allowed_chapters = chapters[:completed_chapter]
    for chapter_number, paragraphs in enumerate(allowed_chapters, start=1):
        for paragraph_number, text in enumerate(paragraphs, start=1):
            score = similarity(question_words, tokens(text))
            if score > 0.08:
                matches.append({
                    "chapter": chapter_number,
                    "paragraph": paragraph_number,
                    "text": text,
                    "score": score,
                    "source": f"Chapter {chapter_number}, paragraph {paragraph_number}",
                })

    # Python's stable sort keeps reading order when scores are equal.
    matches.sort(key=lambda passage: passage["score"], reverse=True)
    return matches[:limit]
