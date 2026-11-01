#!/usr/bin/env python3
"""Unit tests for sync_notes.py. Run: python3 -I scripts/test_sync_notes.py"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_notes as sn  # noqa: E402


def rt(text, **ann):
    return [{"type": "text", "plain_text": text, "text": {"content": text}, "annotations": ann}]


def blk(t, text="", bid="b1", children=None, **extra):
    payload = {"rich_text": rt(text) if text else []}
    payload.update(extra)
    b = {"id": bid, "type": t, t: payload, "has_children": bool(children)}
    b["_children"] = children or []
    return b


class FakeConverter(sn.Converter):
    """Reads children from the block dicts instead of the API."""

    def __init__(self, blocks):
        super().__init__(None)
        self.index = {}
        self._walk(blocks)

    def _walk(self, blocks):
        for b in blocks:
            self.index[b["id"]] = b["_children"]
            self._walk(b["_children"])

    def children(self, block_id):
        return self.index.get(block_id, [])


def md(blocks):
    return "\n\n".join(FakeConverter(blocks).convert(blocks))


class InlineTests(unittest.TestCase):
    def test_annotations(self):
        parts = rt("bold", bold=True) + rt(" and ") + rt("code", code=True) + rt(" it", italic=True)
        self.assertEqual(sn.inline(parts), "**bold** and `code` *it*")

    def test_link_keeps_edge_spaces(self):
        part = rt(" site ", bold=True)[0]
        part["href"] = "https://x.y"
        self.assertEqual(sn.inline([part]), " [**site**](https://x.y) ")

    def test_slugify(self):
        self.assertEqual(sn.slugify("Swiss cheese tier list"), "swiss-cheese-tier-list")
        self.assertEqual(sn.slugify("Gruyère & Tête de Moine!"), "gruyere-tete-de-moine")
        self.assertEqual(sn.slugify("音乐"), "音乐")


class BlockTests(unittest.TestCase):
    def test_headings_shift_down(self):
        self.assertEqual(md([blk("heading_1", "A"), blk("heading_2", "B", "b2")]), "## A\n\n### B")

    def test_nested_lists_and_todo(self):
        blocks = [blk("bulleted_list_item", "one", "b1", children=[
            blk("bulleted_list_item", "two", "b2"),
            blk("to_do", "done", "b3", checked=True),
        ])]
        self.assertEqual(md(blocks), "- one\n\n  - two\n\n  - [x] done")

    def test_numbered_list_counts(self):
        blocks = [blk("numbered_list_item", "a", "b1"), blk("numbered_list_item", "b", "b2")]
        self.assertEqual(md(blocks), "1. a\n\n2. b")

    def test_table(self):
        rows = [
            {"id": "r1", "type": "table_row", "table_row": {"cells": [rt("H1"), rt("H2")]}, "_children": []},
            {"id": "r2", "type": "table_row", "table_row": {"cells": [rt("a|b"), rt("c")]}, "_children": []},
        ]
        t = blk("table", "", "t1", children=rows, has_column_header=True)
        self.assertEqual(md([t]), "| H1 | H2 |\n|---|---|\n| a\\|b | c |")

    def test_quote_with_children_and_divider(self):
        q = blk("quote", "wise", "q1", children=[blk("paragraph", "more", "p2")])
        self.assertEqual(md([q, blk("divider", "", "d1")]), "> wise\n> more\n\n---")

    def test_quote_line_breaks(self):
        q = blk("quote", "line one\nline two", "q2")
        self.assertEqual(md([q]), "> line one\\\n> line two")

    def test_image_is_collected(self):
        conv = FakeConverter([])
        b = {"id": "i1", "type": "image", "has_children": False,
             "image": {"file": {"url": "https://s3/x/photo.png?sig=1"}, "caption": rt("Cat")}}
        self.assertEqual(conv.block(b, 0, 0), ["![Cat](img-1.png)"])
        self.assertEqual(conv.images, [("https://s3/x/photo.png?sig=1", "img-1.png")])


NAMES = {"title": "Name", "subjects": "Tags", "date": "Date", "publish": "Publish"}


def row(pid="abc123", title="Rock", publish=True, subjects=("music",), date="2024-04-25", icon=None):
    r = {"id": pid, "created_time": "2026-01-01T00:00:00Z", "properties": {
        "Name": {"type": "title", "title": rt(title)},
        "Tags": {"type": "multi_select", "multi_select": [{"name": t} for t in subjects]},
        "Date": {"type": "date", "date": {"start": date} if date else None},
        "Publish": {"type": "checkbox", "checkbox": publish},
    }}
    if icon:
        r["icon"] = {"type": "emoji", "emoji": icon}
    return r


class NoteTests(unittest.TestCase):
    def test_unpublished_is_skipped(self):
        self.assertIsNone(sn.build_note(row(publish=False), NAMES, "x", []))

    def test_icon_joins_title_and_front_matter(self):
        n = sn.build_note(row(title="Beef", icon="🥩", subjects=("Food", "biology")), NAMES, "body", [])
        self.assertEqual(n["title"], "🥩 Beef")
        self.assertEqual(n["slug"], "beef")
        self.assertEqual(n["subjects"], ["biology", "food"])
        fm = sn.front_matter(n)
        self.assertIn('title: "🥩 Beef"', fm)
        self.assertIn("notion_id: abc123", fm)
        self.assertIn('subjects: ["biology", "food"]', fm)
        self.assertNotIn("tags:", fm)
        self.assertNotIn("summary:", fm)

    def test_no_subject_falls_back_to_misc(self):
        n = sn.build_note(row(subjects=()), NAMES, "b", [])
        self.assertEqual(n["subjects"], ["misc"])

    def test_write_remove_and_leave_handwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "notes")
            os.makedirs(root)
            hand = os.path.join(root, "hand.md")
            with open(hand, "w") as f:
                f.write('---\ntitle: "Hand"\n---\n')
            n1 = sn.build_note(row("id1", "Rock"), NAMES, "r", [])
            n2 = sn.build_note(row("id2", "Jazz"), NAMES, "j", [])
            log = lambda m: None
            self.assertEqual(sn.write_notes([n1, n2], root, False, log), (2, 0))
            self.assertTrue(os.path.exists(os.path.join(root, "rock.md")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "subjects", "music", "_index.md")))
            # Unchanged run: nothing written.
            self.assertEqual(sn.write_notes([n1, n2], root, False, log), (0, 0))
            # Jazz unpublished, Rock renamed: old file goes, new one comes, hand.md stays.
            n1b = sn.build_note(row("id1", "Rock music"), NAMES, "r", [])
            self.assertEqual(sn.write_notes([n1b], root, False, log), (1, 1))
            self.assertEqual(sorted(os.listdir(root)), ["hand.md", "rock-music.md"])


if __name__ == "__main__":
    unittest.main()
