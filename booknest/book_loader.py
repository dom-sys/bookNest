"""Read a standalone demo book; this is not the team's shared storage layer.

Format: {"title": "Book title", "chapters": [["Paragraph one.", "Paragraph two."]]}
Chapters and paragraphs are numbered by their position, starting at 1.
"""

import json
from pathlib import Path


def load_book(path):
    """Return a book dictionary after checking its title and chapter structure."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(f"Book file was not found: {path}") from None
    except UnicodeError:
        raise ValueError("Book file must be saved as UTF-8 text.") from None
    except OSError as error:
        raise ValueError(f"Could not read book file: {error}") from None

    try:
        book = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}"
        ) from None

    if not isinstance(book, dict):
        raise ValueError("Book must be a JSON object with title and chapters fields.")
    title = book.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Book title must be nonempty text.")

    chapters = book.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("Book chapters must be a nonempty list.")
    for chapter_number, paragraphs in enumerate(chapters, start=1):
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ValueError(f"Chapter {chapter_number} must be a nonempty list of paragraphs.")
        for paragraph_number, paragraph in enumerate(paragraphs, start=1):
            if not isinstance(paragraph, str) or not paragraph.strip():
                raise ValueError(
                    f"Chapter {chapter_number}, paragraph {paragraph_number} must be nonempty text."
                )

    # Preserve the original text and order so citations keep the same numbering.
    return book
