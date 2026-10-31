#!/usr/bin/env python3
"""Unit tests for sync_books.py. Run: python3 -I scripts/test_sync_books.py"""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_books as sb  # noqa: E402

with open(os.path.join(os.path.dirname(__file__), "sync_config.json"), encoding="utf-8") as f:
    NAMES = json.load(f)["properties"]


def rt(text):
    return [{"type": "text", "plain_text": text, "text": {"content": text}}]


def book_row(pid, title, author="A. Author", status="Completed", rating="⭐️⭐️⭐️⭐️",
             cats=("Fiction",), started=None, completed=None, review="", private=None, archived=False):
    props = {
        "Title": {"type": "title", "title": rt(title)},
        "Author": {"type": "rich_text", "rich_text": rt(author) if author else []},
        "Status": {"type": "status", "status": {"name": status} if status else None},
        "Rating": {"type": "select", "select": {"name": rating} if rating else None},
        "Category": {"type": "multi_select", "multi_select": [{"name": c} for c in cats]},
        "Date Started": {"type": "date", "date": {"start": started} if started else None},
        "Date completed": {"type": "date", "date": {"start": completed} if completed else None},
        "Review": {"type": "rich_text", "rich_text": rt(review) if review else []},
    }
    if private is not None:
        props["Private"] = {"type": "checkbox", "checkbox": private}
    return {"id": pid, "created_time": "2026-09-01T22:41:57.000Z", "archived": archived, "properties": props}


def note_row(nid, book_ids, text, title="Notes & Thoughts"):
    return {
        "id": nid,
        "created_time": "2025-06-25T02:12:46.000Z",
        "properties": {
            "Name": {"type": "title", "title": rt(title)},
            "Name of book": {"type": "relation", "relation": [{"id": b} for b in book_ids], "has_more": False},
            "Thoughts & Notes": {"type": "rich_text", "rich_text": rt(text) if text else []},
        },
    }


class TransformTests(unittest.TestCase):
    def test_basic_book(self):
        rows = [book_row("3ceef088-fb8b-80bf-841f-e7b72625454a", "Klingsor’s Last Summer", "Hermann Hesse",
                         cats=("Memoir", "Fiction"), completed="2026-08-30T00:00:00.000+02:00")]
        notes = [note_row("n1", ["3ceef088-fb8b-80bf-841f-e7b72625454a"], "tremendous passion for life")]
        books = sb.build_books(rows, notes, NAMES, bodies={"n1": "a book like a vibrant oil painting"})
        self.assertEqual(len(books), 1)
        b = books[0]
        self.assertEqual(b["id"], "3ceef088fb8b80bf841fe7b72625454a")
        self.assertEqual(b["rating"], 4)
        self.assertEqual(b["categories"], ["Fiction", "Memoir"])
        self.assertEqual(b["completed"], "2026-08-30")
        self.assertEqual(b["lang"], "en")
        self.assertFalse(b["collection"])
        self.assertEqual(len(b["notes"]), 1)
        self.assertIn("tremendous passion", b["notes"][0]["text"])
        self.assertIn("oil painting", b["notes"][0]["text"])

    def test_chinese_and_collection(self):
        rows = [book_row("a1", "三体", "刘慈欣", rating="⭐️⭐️⭐️⭐️⭐️"),
                book_row("a2", "*Collection*: Agatha Christie", "Agatha Christie", rating=None)]
        books = sb.build_books(rows, [], NAMES)
        by = {b["title"]: b for b in books}
        self.assertEqual(by["三体"]["lang"], "zh")
        self.assertEqual(by["三体"]["rating"], 5)
        self.assertTrue(by["Agatha Christie"]["collection"])
        self.assertIsNone(by["Agatha Christie"]["rating"])

    def test_private_and_archived_skipped(self):
        rows = [book_row("p1", "Secret", private=True), book_row("p2", "Gone", archived=True),
                book_row("p3", "Public", private=False)]
        books = sb.build_books(rows, [], NAMES)
        self.assertEqual([b["title"] for b in books], ["Public"])

    def test_missing_fields_tolerated(self):
        row = {"id": "m1", "created_time": "2026-01-01T00:00:00Z",
               "properties": {"Title": {"type": "title", "title": rt("Holy Bible")}}}
        books = sb.build_books([row], [], NAMES)
        self.assertEqual(books[0]["author"], "")
        self.assertEqual(books[0]["status"], "To Read")
        self.assertEqual(books[0]["categories"], [])
        self.assertIsNone(books[0]["rating"])

    def test_placeholder_notes_dropped(self):
        rows = [book_row("b1", "The Devil")]
        notes = [note_row("n1", ["b1"], "…")]
        books = sb.build_books(rows, notes, NAMES)
        self.assertEqual(books[0]["notes"], [])

    def test_deterministic_output(self):
        rows = [book_row("z", "Zeta"), book_row("a", "Alpha")]
        a = json.dumps(sb.build_books(rows, [], NAMES), sort_keys=True)
        b = json.dumps(sb.build_books(list(reversed(rows)), [], NAMES), sort_keys=True)
        self.assertEqual(a, b)

    def test_validate_refuses_shrink(self):
        books = sb.build_books([book_row("a", "A")], [], NAMES)
        with self.assertRaises(sb.NotionError):
            sb.validate(books, previous_count=10)
        sb.validate(books, previous_count=1)  # fine
        with self.assertRaises(sb.NotionError):
            sb.validate([], previous_count=0)

    def test_star_count(self):
        self.assertEqual(sb.star_count("⭐️⭐️⭐️"), 3)
        self.assertEqual(sb.star_count("⭐️⭐️⭐️⭐️⭐️"), 5)
        self.assertEqual(sb.star_count("4 stars"), 4)
        self.assertIsNone(sb.star_count(""))
        self.assertIsNone(sb.star_count("⭐️" * 7))

    def test_block_markdown(self):
        blocks = [
            {"type": "heading_2", "heading_2": {"rich_text": rt("Thoughts")}},
            {"type": "paragraph", "paragraph": {"rich_text": rt("A line.")}},
            {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rt("point")}},
            {"type": "quote", "quote": {"rich_text": rt("quoted")}},
        ]
        out = [sb.block_to_markdown(b) for b in blocks]
        self.assertEqual(out, ["## Thoughts", "A line.", "- point", "> quoted"])


class HttpTests(unittest.TestCase):
    def test_pagination_and_fallback(self):
        pages = {
            ("POST", "/data_sources/ds/query"): sb.NotionError("POST -> HTTP 404"),
            ("POST", "/databases/db/query"): [
                {"results": [{"id": "1"}], "has_more": True, "next_cursor": "c2"},
                {"results": [{"id": "2"}], "has_more": False},
            ],
        }
        calls = []

        def fake_request(self, method, path, body=None, query=None):
            calls.append((method, path, (body or {}).get("start_cursor")))
            r = pages[(method, path)]
            if isinstance(r, Exception):
                raise r
            return r.pop(0)

        with mock.patch.object(sb.Notion, "request", fake_request):
            rows, version = sb.query_rows("tok", {"data_source_id": "ds", "database_id": "db"}, False)
        self.assertEqual([r["id"] for r in rows], ["1", "2"])
        self.assertEqual(version, sb.API_VERSION_OLD)
        self.assertEqual(calls[-1][2], "c2")

    def test_retry_on_429_then_success(self):
        responses = [
            mock_http_error(429, {"Retry-After": "0"}),
            mock.MagicMock(**{"__enter__.return_value.read.return_value": b'{"ok": true}'}),
        ]

        def fake_urlopen(req, timeout=0):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch.object(sb.urllib.request, "urlopen", fake_urlopen), \
             mock.patch.object(sb.time, "sleep", lambda s: None):
            out = sb.Notion("t", sb.API_VERSION_NEW).request("GET", "/x")
        self.assertEqual(out, {"ok": True})

    def test_401_is_fatal_without_retry(self):
        def fake_urlopen(req, timeout=0):
            raise mock_http_error(401, {})
        with mock.patch.object(sb.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(sb.NotionError):
                sb.Notion("t", sb.API_VERSION_NEW).request("GET", "/x")


def mock_http_error(code, headers):
    import io
    import urllib.error
    from email.message import Message
    h = Message()
    for k, v in headers.items():
        h[k] = v
    return urllib.error.HTTPError("https://api.notion.com/v1/x", code, "err", h, io.BytesIO(b'{"message":"x"}'))


if __name__ == "__main__":
    unittest.main(verbosity=1)
