"""Checks for external book files, using disposable temporary files."""

import json
from pathlib import Path
import tempfile
import unittest

from booknest.book_loader import load_book
from booknest.retrieval import find_passages


class BookLoaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "book.json"

    def write_book(self, book):
        self.path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")

    def test_load_preserves_unicode_text_and_citations(self):
        book = {"title": "Mira’s story", "chapters": [["Rain fell.", "Mira found a key."], ["The cabinet opened."]]}
        self.write_book(book)
        loaded = load_book(self.path)
        self.assertEqual(loaded, book)
        result = find_passages(loaded["chapters"], 1, "key")
        self.assertEqual(result[0]["source"], "Chapter 1, paragraph 2")
        self.assertEqual(find_passages(loaded["chapters"], 1, "cabinet"), [])

    def test_missing_file(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            load_book(self.path)

    def test_invalid_json(self):
        self.path.write_text('{"title":', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid JSON at line"):
            load_book(self.path)

    def test_invalid_encoding(self):
        self.path.write_bytes(b'\xff')
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            load_book(self.path)

    def test_directory_instead_of_file(self):
        with self.assertRaisesRegex(ValueError, "Could not read"):
            load_book(self.path.parent)

    def test_invalid_book_structure(self):
        invalid_books = [
            [], {}, {"title": " ", "chapters": [["Text"]]},
            {"title": 42, "chapters": [["Text"]]},
            {"title": "Story"}, {"title": "Story", "chapters": []},
            {"title": "Story", "chapters": "Text"},
            {"title": "Story", "chapters": [[]]},
            {"title": "Story", "chapters": ["Text"]},
            {"title": "Story", "chapters": [[42]]},
            {"title": "Story", "chapters": [[" "]]},
        ]
        for book in invalid_books:
            with self.subTest(book=book):
                self.write_book(book)
                with self.assertRaises(ValueError):
                    load_book(self.path)


if __name__ == "__main__":
    unittest.main()
