"""Run: python3 -m unittest discover -s tests -p 'test_retrieval.py' -v"""

import unittest
from unittest.mock import patch

from booknest.retrieval import find_passages, tokens


class RetrievalTests(unittest.TestCase):
    def test_relevant_passage_has_original_citation(self):
        chapters = [["Rain fell outside.", "Mira found the brass key."]]
        result = find_passages(chapters, 1, "Who found the brass key?")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], chapters[0][1])
        self.assertEqual(result[0]["source"], "Chapter 1, paragraph 2")

    def test_common_words_alone_do_not_make_a_passage_relevant(self):
        chapters = [[
            "Mira found a brass key beside the bookshop window.",
            "Jonah carried a box of poetry books into the shop.",
        ]]
        result = find_passages(chapters, 1, "WHO found THE brass key?")
        self.assertEqual([item["paragraph"] for item in result], [1])
        self.assertEqual(result[0]["text"], chapters[0][0])

    def test_question_with_only_stop_words_returns_no_matches(self):
        self.assertEqual(find_passages([["The key was in a box."]], 1, "THE of a?"), [])

    def test_unread_chapter_is_not_even_tokenized(self):
        unread = "The secret owner of the brass key was Jonah."
        with patch("booknest.retrieval.tokens", wraps=tokens) as tokenize:
            result = find_passages([["Mira found a key."], [unread]], 1, "brass key")
        self.assertTrue(all(item["chapter"] == 1 for item in result))
        self.assertNotIn(unittest.mock.call(unread), tokenize.call_args_list)

    def test_finishing_next_chapter_makes_its_passage_available(self):
        chapters = [["Rain fell."], ["Mira opened the cabinet."]]
        self.assertEqual(find_passages(chapters, 1, "cabinet"), [])
        self.assertEqual(find_passages(chapters, 2, "cabinet")[0]["chapter"], 2)

    def test_zero_progress_and_no_matches_return_empty(self):
        self.assertEqual(find_passages([["A brass key."]], 0, "key"), [])
        self.assertEqual(find_passages([["A brass key."]], 1, "spaceship"), [])
        self.assertEqual(find_passages([["A brass key."]], 1, "???"), [])

    def test_ranking_and_limit(self):
        chapters = [["key rain wind snow", "brass key"]]
        result = find_passages(chapters, 1, "brass key", limit=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["paragraph"], 2)

    def test_invalid_questions_are_rejected(self):
        for question in ["", "   ", "x" * 2001, None]:
            with self.subTest(question=str(question)[:20]):
                with self.assertRaises(ValueError):
                    find_passages([["text"]], 1, question)

    def test_invalid_chapter_and_passage_limits_are_rejected(self):
        for chapter in [-1, 2, 0.5, True]:
            with self.subTest(chapter=chapter):
                with self.assertRaises(ValueError):
                    find_passages([["text"]], chapter, "text")
        for limit in [0, -1, 1.5, True]:
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    find_passages([["text"]], 1, "text", limit)


if __name__ == "__main__":
    unittest.main()
