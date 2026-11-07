#!/usr/bin/env python3
"""Tests for sync_recipes.py. Run: python3 -I scripts/test_sync_recipes.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_recipes as sr  # noqa: E402


def rt(text):
    return [{"type": "text", "plain_text": text, "text": {"content": text}, "annotations": {}}]


class FakeClient:
    """Serves a tiny page tree: a cuisine with two recipes, one under a heading."""

    def __init__(self):
        self.tree = {
            "cuisine": [
                {"id": "r1", "type": "child_page", "child_page": {"title": "番茄炒蛋"}, "created_time": "2025-01-01T00:00:00Z"},
                {"id": "p1", "type": "paragraph", "paragraph": {"rich_text": rt("an idea, not a page")}},
                {"id": "h1", "type": "heading_2", "heading_2": {"rich_text": rt("面条")}},
                {"id": "r2", "type": "child_page", "child_page": {"title": "炒面"}, "created_time": "2025-01-02T00:00:00Z"},
            ],
            "r1": [
                {"id": "a", "type": "heading_2", "heading_2": {"rich_text": rt("Ingredients")}, "has_children": False},
                {"id": "b", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rt("蛋 3个")}, "has_children": False},
                {"id": "c", "type": "heading_2", "heading_2": {"rich_text": rt("Procedure")}, "has_children": False},
                {"id": "d", "type": "numbered_list_item", "numbered_list_item": {"rich_text": rt("炒")}, "has_children": False},
                {"id": "e", "type": "paragraph", "paragraph": {"rich_text": []}, "has_children": False},
                {"id": "f", "type": "numbered_list_item", "numbered_list_item": {"rich_text": rt("another way")}, "has_children": False},
            ],
            "r2": [],
        }

    def paginate(self, method, path, body=None, query=None):
        return list(self.tree.get(path.split("/")[2], []))

    def request(self, method, path, body=None, query=None):
        return {"icon": {"type": "emoji", "emoji": "🍅"}} if path.endswith("/r1") else {}

    def log(self, msg):
        pass


class RecipeTests(unittest.TestCase):
    def test_walk_groups_and_bodies(self):
        client = FakeClient()
        recipes = sr.walk_cuisine(client, {"id": "cuisine"}, "chinese", lambda: sr.sn.Converter(client))
        self.assertEqual([r["title"] for r in recipes], ["番茄炒蛋", "炒面"])
        self.assertEqual(recipes[0]["group"], "")
        self.assertEqual(recipes[1]["group"], "面条")
        self.assertEqual(recipes[0]["slug"], "chinese/番茄炒蛋")
        self.assertEqual(recipes[0]["icon"], "🍅")
        body = recipes[0]["body"]
        self.assertIn("## Ingredients", body)
        self.assertIn("## Procedure", body)
        self.assertIn("1. 炒\n\n<!-- -->\n\n1. another way", body)

    def test_front_matter(self):
        fm = sr.front_matter({"icon": "🍅", "title": "番茄炒蛋", "date": "2025-01-01", "weight": 1,
                              "group": "面条", "group_weight": 1, "id": "abc"})
        self.assertIn('title: "🍅 番茄炒蛋"', fm)
        self.assertIn('group: "面条"', fm)
        self.assertIn("notion_id: abc", fm)
        self.assertNotIn("group", sr.front_matter({"icon": "", "title": "x", "date": "d", "weight": 2, "id": "z"}))


if __name__ == "__main__":
    unittest.main()
