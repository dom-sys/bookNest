"""Check the standalone assistant's public response behavior."""

import json
from pathlib import Path
import tempfile
import unittest

from booknest.ai import Assistant


class AssistantTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "book.json"
        book = {
            "title": "Sample Story",
            "chapters": [
                ["Rain fell.", "Mira found a brass key."],
                ["The cabinet held a map."],
            ],
        }
        self.path.write_text(json.dumps(book), encoding="utf-8")
        self.assistant = Assistant(self.path)

    def test_loads_book_and_returns_cited_original_passage(self):
        self.assertEqual(self.assistant.title, "Sample Story")
        self.assertEqual(self.assistant.chapter_count, 2)
        answer = self.assistant.ask_book(1, "brass key")
        self.assertIn("RAG-only mode", answer)
        self.assertIn("[Chapter 1, paragraph 2]\nMira found a brass key.", answer)
        self.assertNotIn("Rain fell.", answer)

    def test_later_chapter_is_only_available_after_completion(self):
        answer = self.assistant.ask_book(1, "cabinet map")
        self.assertEqual(answer, "No matching passages were found in the completed chapters.")
        answer = self.assistant.ask_book(2, "cabinet map")
        self.assertIn("[Chapter 2, paragraph 1]\nThe cabinet held a map.", answer)
        # Asking with an earlier limit must not reuse later-chapter evidence.
        self.assertNotIn("The cabinet held a map.", self.assistant.ask_book(1, "cabinet map"))

    def test_zero_progress_and_unmatched_question(self):
        for chapter, question in [(0, "key"), (2, "spaceship")]:
            with self.subTest(chapter=chapter, question=question):
                self.assertEqual(self.assistant.ask_book(chapter, question),
                                 "No matching passages were found in the completed chapters.")

    def test_invalid_input_reaches_caller_as_value_error(self):
        for chapter, question in [(3, "key"), (1, "")]:
            with self.subTest(chapter=chapter, question=question):
                with self.assertRaises(ValueError):
                    self.assistant.ask_book(chapter, question)

    def test_missing_book_reaches_caller_as_value_error(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            Assistant(self.path.parent / "missing.json")


if __name__ == "__main__":
    unittest.main()
