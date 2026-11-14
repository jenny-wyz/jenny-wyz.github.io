#!/usr/bin/env python3
"""Tests for sync_braindump.py. Run: python3 -I scripts/test_sync_braindump.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_braindump as sb  # noqa: E402


def rt(text):
    return [{"type": "text", "plain_text": text, "text": {"content": text}, "annotations": {}}]


BLOCKS = [
    {"type": "heading_2", "heading_2": {"rich_text": rt("Recyclable")}},
    {"type": "child_page", "id": "a", "child_page": {"title": "0"}},
    {"type": "paragraph", "paragraph": {"rich_text": []}},
    {"type": "heading_2", "heading_2": {"rich_text": rt("Not recyclable")}},
    {"type": "child_page", "id": "b", "child_page": {"title": "1"}},
]


class DumpTests(unittest.TestCase):
    def test_groups_follow_headings(self):
        got = [(b["id"], g, o) for b, g, o in sb.collect(BLOCKS)]
        self.assertEqual(got, [("a", "Recyclable", 1), ("b", "Not recyclable", 2)])

    def test_page_before_any_heading_has_no_group(self):
        got = sb.collect([{"type": "child_page", "id": "x", "child_page": {"title": "t"}}] + BLOCKS)
        self.assertEqual(got[0][1:], ("", 0))

    def test_front_matter(self):
        fm = sb.front_matter({"title": "0", "date": "2026-11-14", "weight": 1, "group": "Recyclable", "group_weight": 1, "id": "abc"})
        self.assertIn('title: "0"', fm)
        self.assertIn('group: "Recyclable"', fm)
        self.assertNotIn("group", sb.front_matter({"title": "t", "date": "d", "weight": 1, "group": "", "id": "z"}))


if __name__ == "__main__":
    unittest.main()
