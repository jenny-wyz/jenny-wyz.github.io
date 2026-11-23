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



class ManualCoverTests(unittest.TestCase):
    A, B, C = "a" * 32, "b" * 32, "c" * 32

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self._shrink, fc.shrink = fc.shrink, (lambda d: d)      # the test files are not real images
        self.addCleanup(lambda: setattr(fc, "shrink", self._shrink))
        self.books = [{"id": self.A, "title": "The Power of Now"}, {"id": self.B, "title": "\u6211\u4e0e\u5730\u575b"},
                      {"id": self.C, "title": "Twins"}, {"id": "d" * 32, "title": "Twins"}]

    def put(self, name, data=b"\xff\xd8jpegish"):
        with open(os.path.join(self.dir, name), "wb") as f:
            f.write(data)

    def files(self):
        return sorted(os.listdir(self.dir))

    def test_title_and_id_names_are_adopted(self):
        self.put("the power of now.jpg")                       # title, any case, leading "the" optional
        self.put("\u6211\u4e0e\u5730\u575b.jpeg")           # Chinese title
        self.put("Twins-" + self.C + ".jpg")                    # "...-<id>" as in a Notion link
        cache = {}
        n = fc.adopt_manual(self.books, cache, self.dir, "2026-11-23")
        self.assertEqual(n, 3)
        self.assertEqual(self.files(), [self.A + ".jpg", self.B + ".jpg", self.C + ".jpg"])
        self.assertEqual({k: v["status"] for k, v in cache.items()}, {self.A: "manual", self.B: "manual", self.C: "manual"})

    def test_unknown_and_ambiguous_names_are_left_alone(self):
        self.put("Twins.jpg")                                   # two books share the title
        self.put("Not a book.jpg")
        self.put("e" * 32 + ".jpg")                             # an id no book has yet
        cache = {}
        self.assertEqual(fc.adopt_manual(self.books, cache, self.dir, "2026-11-23"), 0)
        self.assertEqual(len(self.files()), 3)
        self.assertEqual(cache, {})

    def test_file_in_place_is_manual_unless_fetched(self):
        self.put(self.A + ".jpg")
        self.put(self.B + ".jpg")
        cache = {self.B: {"status": "ok", "cover_i": 1}}
        fc.adopt_manual(self.books, cache, self.dir, "2026-11-23")
        self.assertEqual(cache[self.A]["status"], "manual")
        self.assertEqual(cache[self.B]["status"], "ok")

    def test_main_keeps_manual_covers_and_strangers(self):
        import json
        books = os.path.join(self.dir, "books.json")
        cachef = os.path.join(self.dir, "covers.json")
        dest = os.path.join(self.dir, "covers")
        os.mkdir(dest)
        with open(books, "w") as f:
            json.dump({"books": [{"id": self.A, "title": "The Power of Now", "author": "x"}]}, f)
        with open(cachef, "w") as f:
            json.dump({self.C: {"status": "ok"}}, f)            # a book that is gone
        for name in ("The Power of Now.jpg", "e" * 32 + ".jpg", self.C + ".jpg"):
            with open(os.path.join(dest, name), "wb") as f:
                f.write(b"\xff\xd8jpegish")
        orig = fc.shrink
        fc.shrink = lambda d: d                                # no real image here
        try:
            fc.main(["--books", books, "--cache", cachef, "--dest", dest, "--manual-only"])
        finally:
            fc.shrink = orig
        self.assertEqual(sorted(os.listdir(dest)), [self.A + ".jpg", "e" * 32 + ".jpg"])   # adopted; stranger kept; gone book removed
        with open(cachef) as f:
            saved = json.load(f)
        self.assertEqual({k: v["status"] for k, v in saved.items()}, {self.A: "manual"})


if __name__ == "__main__":
    unittest.main(verbosity=1)
