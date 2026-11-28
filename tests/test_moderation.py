"""Tests for Subsystem 4 (Reviews, Warnings & Conduct): taboo-word moderation."""
import unittest

from booknest.moderation import filter_comment, normalize


class Normalize(unittest.TestCase):
    def test_lowercases_and_translates_leetspeak(self):
        self.assertEqual(normalize('H3LL0'), 'helo')

    def test_collapses_repeated_letters(self):
        self.assertEqual(normalize('HEEELL0'), 'helo')

    def test_symbol_substitutions(self):
        self.assertEqual(normalize('$tup1d'), 'stupid')
        self.assertEqual(normalize('@ss'), 'as')


class FilterComment(unittest.TestCase):
    def test_clean_comment_unchanged(self):
        masked, count = filter_comment('A lovely, thoughtful book.', ['stupid'])
        self.assertEqual(count, 0)
        self.assertEqual(masked, 'A lovely, thoughtful book.')

    def test_obfuscation_and_whole_words(self):
        masked, count = filter_comment('STUUUP1D stupidly $tupid', ['stupid'])
        self.assertEqual(count, 2)
        self.assertEqual(masked, '******** stupidly ******')

    def test_mask_length_matches_original_word(self):
        masked, _ = filter_comment('so stuuupid', ['stupid'])
        self.assertEqual(masked, 'so ' + '*' * len('stuuupid'))

    def test_counts_occurrences_not_distinct_words(self):
        _, count = filter_comment('idiot idiot idiot', ['idiot'])
        self.assertEqual(count, 3)

    def test_block_boundary_three_vs_four(self):
        # review() blocks only when count > 3, so 3 is masked and 4 is blocked.
        _, three = filter_comment('idiot idiot idiot', ['idiot'])
        _, four = filter_comment('idiot idiot idiot idiot', ['idiot'])
        self.assertLessEqual(three, 3)
        self.assertGreater(four, 3)

    def test_taboo_list_is_normalized_too(self):
        _, count = filter_comment('stupid', ['  STUP1D  '])
        self.assertEqual(count, 1)

    def test_blank_taboo_entries_ignored(self):
        masked, count = filter_comment('fine text', ['', '   '])
        self.assertEqual((masked, count), ('fine text', 0))


if __name__ == '__main__':
    unittest.main()
