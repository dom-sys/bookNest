import tempfile
import unittest
from unittest.mock import patch

from booknest.ai import Assistant
from booknest.seed import populate
from booknest.services import BookNest


class AskTheBookTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = BookNest(directory.name)
        populate(self.service)
        with self.service.store.transaction() as state:
            book = next(book for book in state['books'] if book['id'] == 'book-1')
            book['chapters'] = [
                {'number': 1, 'paragraphs': ['Mira found the brass key.', 'Jonah entered the shop.']},
                {'number': 2, 'paragraphs': ['The cabinet held a map.']},
            ]
        self.assistant = Assistant(self.service, generate=False)

    def test_shared_common_words_do_not_make_a_passage_relevant(self):
        answer = self.assistant.ask_book('book-1', 1, 'Who found the brass key?')
        self.assertIn('[chapter 1, paragraph 1] Mira found the brass key.', answer)
        self.assertNotIn('Jonah entered', answer)

    def test_no_match_skips_generation_and_logs_no_sources(self):
        with patch.object(self.assistant, '_generate') as generate:
            answer = self.assistant.ask_book('book-1', 1, 'What was in the cabinet?')
        generate.assert_not_called()
        self.assertIn('No matching passages', answer)
        record = self.service.store.snapshot()['chat_log'][-1]
        self.assertEqual(record['sources'], [])

    def test_recap_still_uses_completed_chapter_evidence(self):
        with patch.object(self.assistant, '_generate', return_value='A recap.') as generate:
            answer = self.assistant.ask_book('book-1', 1, 'Recap so far')
        evidence = generate.call_args.args[1]
        self.assertIn('Mira found the brass key.', evidence)
        self.assertNotIn('cabinet', evidence)
        self.assertIn('A recap.', answer)
        self.assertIn('[chapter 1, paragraph 1]', answer)
        self.assertEqual(self.assistant.progress('book-1'), 1)
