#!/usr/bin/env python3
"""Tests for sync_journal.py. Run: python3 -I scripts/test_sync_journal.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_journal as sj  # noqa: E402

NAMES = {"title": "Name", "week": "Week", "publish": "Publish"}


def rt(text):
    return [{"type": "text", "plain_text": text, "text": {"content": text}, "annotations": {}}]


def row(title="6. bis 12. September 2026", start="2026-09-06", end="2026-09-12", publish=True):
    return {"id": "abc123", "created_time": "2026-11-03T00:00:00Z", "properties": {
        "Name": {"type": "title", "title": rt(title)},
        "Week": {"type": "date", "date": {"start": start, "end": end}},
        "Publish": {"type": "checkbox", "checkbox": publish},
    }}


class JournalTests(unittest.TestCase):
    def test_entry_and_front_matter(self):
        e = sj.build_entry(row(), NAMES, "Text", [])
        self.assertEqual(e["slug"], "2026-09-06")
        self.assertEqual(e["week_end"], "2026-09-12")
        fm = sj.front_matter(e)
        self.assertIn('title: "6. bis 12. September 2026"', fm)
        self.assertIn("date: 2026-09-06", fm)
        self.assertIn("week_end: 2026-09-12", fm)
        self.assertIn("notion_id: abc123", fm)

    def test_single_date_week(self):
        e = sj.build_entry(row(end=None), NAMES, "x", [])
        self.assertEqual(e["week_end"], "2026-09-06")

    def test_unpublished_skipped(self):
        self.assertIsNone(sj.build_entry(row(publish=False), NAMES, "x", []))


if __name__ == "__main__":
    unittest.main()
