#!/usr/bin/env python3
"""Tests for sync_essays.py. Run: python3 -I scripts/test_sync_essays.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_essays as se  # noqa: E402


def rt(text):
    return [{"type": "text", "plain_text": text, "text": {"content": text}, "annotations": {}}]


BLOCKS = [
    {"type": "heading_1", "heading_1": {"rich_text": rt("Ver 1")}},
    {"type": "paragraph", "paragraph": {"rich_text": rt("Polished minimally.")}},
    {"type": "child_page", "id": "a", "child_page": {"title": "example 1"}},
    {"type": "divider", "divider": {}},
    {"type": "heading_1", "heading_1": {"rich_text": rt("Ver 0")}},
    {"type": "child_page", "id": "b", "child_page": {"title": "1"}},
    {"type": "child_page", "id": "c", "child_page": {"title": "2"}},
]


class EssayTests(unittest.TestCase):
    def test_only_the_publish_section_is_collected(self):
        picked = se.collect(BLOCKS, "Ver 1")
        self.assertEqual([b["id"] for b in picked], ["a"])

    def test_nothing_before_a_heading_or_under_ver_0(self):
        self.assertEqual(se.collect(BLOCKS, "Ver 2"), [])
        self.assertEqual([b["id"] for b in se.collect(BLOCKS, "Ver 0")], ["b", "c"])

    def test_front_matter(self):
        fm = se.front_matter({"title": "example 1", "date": "2026-11-09", "weight": 1, "id": "abc"})
        self.assertIn('title: "example 1"', fm)
        self.assertIn("notion_id: abc", fm)


if __name__ == "__main__":
    unittest.main()
