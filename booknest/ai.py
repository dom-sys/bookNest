"""Standalone, single-book assistant for the retrieval demo.

This starter returns original passages, not generated answers. It does not yet
connect to BookNest services, check ownership, or track progress and quotas.
"""

from .book_loader import load_book
from .retrieval import find_passages


class Assistant:
    """Load one book and answer questions with cited, chapter-limited passages."""

    def __init__(self, book_file):
        book = load_book(book_file)
        self.title = book["title"]
        self.chapters = book["chapters"]
        self.chapter_count = len(self.chapters)

    def ask_book(self, completed_chapter, question):
        """Return display-ready text; invalid input raises ValueError."""
        passages = find_passages(self.chapters, completed_chapter, question)
        if not passages:
            return "No matching passages were found in the completed chapters."

        answer_parts = ["[RAG-only mode: retrieved passages]"]
        for passage in passages:
            answer_parts.append(f"[{passage['source']}]\n{passage['text']}")
        return "\n\n".join(answer_parts)
