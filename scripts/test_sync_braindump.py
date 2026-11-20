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

    def test_pages_inside_year_toggles_are_found_and_years_are_not_groups(self):
        tree = {
            "y23": [{"type": "child_page", "id": "p1", "child_page": {"title": "20231117-0130"}}],
            "y24": [{"type": "child_page", "id": "p2", "child_page": {"title": "20240101"}},
                    {"type": "toggle", "id": "t", "has_children": True, "toggle": {"rich_text": rt("more")}}],
            "t": [{"type": "child_page", "id": "p3", "child_page": {"title": "20240102"}}],
        }
        blocks = [
            {"type": "heading_2", "id": "h", "heading_2": {"rich_text": rt("Recycling")}},
            {"type": "heading_4", "id": "y23", "has_children": True, "heading_4": {"rich_text": rt("2023"), "is_toggleable": True}},
            {"type": "heading_3", "id": "y24", "has_children": True, "heading_3": {"rich_text": rt("2024"), "is_toggleable": True}},
            {"type": "heading_4", "id": "y27", "heading_4": {"rich_text": rt("2027")}},
            {"type": "heading_2", "id": "w", "heading_2": {"rich_text": rt("Waste")}},
            {"type": "child_page", "id": "p4", "child_page": {"title": "20261110'"}},
        ]
        got = [(b["id"], g, o) for b, g, o in sb.collect(blocks, lambda i: tree.get(i, []))]
        self.assertEqual(got, [("p1", "Recycling", 1), ("p2", "Recycling", 1), ("p3", "Recycling", 1), ("p4", "Waste", 2)])
        # without a way to look inside, only the top level is seen (old behaviour)
        self.assertEqual([b["id"] for b, _, _ in sb.collect(blocks)], ["p4"])

    def test_safety_stop(self):
        self.assertTrue(sb.too_few(4, 136))
        self.assertFalse(sb.too_few(130, 136))
        self.assertFalse(sb.too_few(0, 3))      # a small section may empty out

    def test_front_matter(self):
        fm = sb.front_matter({"title": "0", "date": "2026-11-14", "weight": 1, "group": "Recyclable", "group_weight": 1, "id": "abc"})
        self.assertIn('title: "0"', fm)
        self.assertIn('group: "Recyclable"', fm)
        self.assertNotIn("group", sb.front_matter({"title": "t", "date": "d", "weight": 1, "group": "", "id": "z"}))

    def test_title_is_a_date(self):
        self.assertEqual(sb.parse_title("20261116"),
                         {"date": "2026-11-16", "time": "", "seq": None, "title": "Monday, 16 November 2026"})
        self.assertEqual(sb.parse_title("20261116-1")["seq"], 1)
        for t in ("20261116 01:20", "20261116-0120", "2026-11-16 1:20", "20261116 01.20"):
            got = sb.parse_title(t)
            self.assertEqual((got["date"], got["time"], got["seq"]), ("2026-11-16", "01:20", None), t)
        self.assertEqual(sb.parse_title("20261116 01:20")["title"], "Monday, 16 November 2026 \u00b7 01:20")
        self.assertEqual(sb.parse_title("20261116 2575")["time"], "")   # not a time
        self.assertIsNone(sb.parse_title("idea"))
        self.assertIsNone(sb.parse_title("20261340"))                    # not a date

    def test_apostrophe_hides_an_entry(self):
        for t in ("20261116-0659\u2019", "20261116-0659'", "20261116 01:20 \u2018", "20261116`", "idea' "):
            self.assertTrue(sb.is_hidden(t), t)
        for t in ("20261116-0659", "20261116 01:20", "don't", ""):
            self.assertFalse(sb.is_hidden(t), t)

    def test_empty_paragraph_becomes_a_gap_marker(self):
        def para(t, i):
            rt = [{"type": "text", "plain_text": t, "text": {"content": t}, "annotations": {}}] if t else []
            return {"type": "paragraph", "id": i, "has_children": False, "paragraph": {"rich_text": rt}}
        blocks = [para("one", "a"), para("", "b"), para("two", "c")]
        conv = sb.sn.Converter(None)
        self.assertEqual(conv.convert(blocks), ["one", "two"])          # other sections: dropped, as before
        conv.keep_blank = True
        self.assertEqual(conv.convert(blocks), ["one", sb.sn.BLANK, "two"])

    def test_display_order(self):
        es = [
            {"id": "old", "date": "2026-11-14", "time": "", "seq": 0, "pos": 0},
            {"id": "late", "date": "2026-11-16", "time": "23:05", "seq": None, "pos": 1},
            {"id": "n1", "date": "2026-11-16", "time": "", "seq": 1, "pos": 2},
            {"id": "early", "date": "2026-11-16", "time": "01:20", "seq": None, "pos": 3},
            {"id": "n0", "date": "2026-11-16", "time": "", "seq": 0, "pos": 4},
        ]
        sb.display_order(es)
        self.assertEqual([e["id"] for e in sorted(es, key=lambda e: e["weight"])], ["old", "n0", "n1", "early", "late"])

    def test_trailing_line_break_is_dropped(self):
        self.assertEqual(sb.TRAILING_BREAK.sub("", "a\\\nb\\\n\nc\\"), "a\\\nb\n\nc")

    def test_time_in_front_matter(self):
        fm = sb.front_matter({"title": "t", "date": "2026-11-16", "time": "01:20", "weight": 1, "group": "", "id": "z"})
        self.assertIn('time: "01:20"', fm)


if __name__ == "__main__":
    unittest.main()
