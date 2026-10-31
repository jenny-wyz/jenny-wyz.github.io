#!/usr/bin/env python3
"""Unit tests for fetch_covers.py matching logic. Run: python3 -I scripts/test_fetch_covers.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_covers as fc  # noqa: E402


class MatchTests(unittest.TestCase):
    def test_title_variants(self):
        self.assertTrue(fc.title_matches("The Brothers Karamazov", "Brothers Karamazov"))
        self.assertTrue(fc.title_matches("Siddhartha", "Siddhartha: A Novel"))
        self.assertTrue(fc.title_matches("Klingsor’s Last Summer", "Klingsor's Last Summer"))
        self.assertFalse(fc.title_matches("The Idiot", "The Idiot's Guide to Cooking Everything"))
        self.assertFalse(fc.title_matches("1984", "Animal Farm"))
        self.assertTrue(fc.title_matches("三体", "三体"))

    def test_author(self):
        self.assertTrue(fc.author_matches("Dostoevsky", ["Fyodor Dostoevsky"]))
        self.assertTrue(fc.author_matches("Fyodor Dostoyevsky", ["Fyodor Dostoyevsky"]))
        self.assertTrue(fc.author_matches("William Somerset Maugham", ["W. Somerset Maugham"]))
        self.assertFalse(fc.author_matches("Hermann Hesse", ["Stephen King"]))
        self.assertTrue(fc.author_matches("", ["Anyone"]))
        self.assertTrue(fc.author_matches("Karl Marx, Freidrich Engels", ["Karl Marx"]))

    def test_pick_prefers_matching_and_popular(self):
        book = {"title": "The Outsider", "author": "Albert Camus"}
        docs = [
            {"title": "The Outsider", "author_name": ["Stephen King"], "cover_i": 1, "edition_count": 90},
            {"title": "The Outsider", "author_name": ["Albert Camus"], "cover_i": 2, "edition_count": 40},
            {"title": "The Stranger", "author_name": ["Albert Camus"], "cover_i": 3, "edition_count": 200},
            {"title": "The Outsider: A Novel", "author_name": ["Albert Camus"], "cover_i": 4, "edition_count": 60},
        ]
        self.assertEqual(fc.pick_cover(book, docs), 4)

    def test_pick_none_when_no_cover(self):
        book = {"title": "Walden", "author": "Thoreau"}
        self.assertIsNone(fc.pick_cover(book, [{"title": "Walden", "author_name": ["Henry David Thoreau"]}]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
