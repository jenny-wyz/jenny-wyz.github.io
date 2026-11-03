#!/usr/bin/env python3
"""Tests for protect_pages.py. Run: python3 -I scripts/test_protect_pages.py"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protect_pages as pp  # noqa: E402

PAGE = """<!doctype html><html><head><title>Secret · Jenny</title>
<meta name="description" content="the summary leaks">
<meta property="og:description" content="the summary leaks too">
<meta name=jw-protected content=1>
<script type="application/ld+json">{"articleBody":"leak"}</script>
</head><body><header>nav</header><main id="main-content" class="grow"><article><h1>Secret</h1><p>top secret body</p></article></main><footer>foot</footer></body></html>"""


class ProtectTests(unittest.TestCase):
    def test_roundtrip(self):
        v = pp.encrypt("hunter22", "<p>hello</p>")
        self.assertEqual(pp.decrypt("hunter22", v), "<p>hello</p>")
        with self.assertRaises(Exception):
            pp.decrypt("wrong", v)

    def test_lock_html_hides_content_and_descriptions(self):
        out = pp.lock_html(PAGE, "hunter22", "/shabi/")
        self.assertNotIn("top secret body", out)
        self.assertNotIn("summary leaks", out)
        self.assertNotIn("articleBody", out)
        self.assertIn("<header>nav</header>", out)
        self.assertIn("<footer>foot</footer>", out)
        self.assertIn("Knock knock.", out)
        self.assertIn('"/shabi/"', out)
        vault = json.loads(re.search(r'id="jw-vault">(.*?)</script>', out, re.S).group(1))
        self.assertIn("<p>top secret body</p>", pp.decrypt("hunter22", vault))

    def test_find_marker(self):
        self.assertTrue(pp.MARKER_RE.search(PAGE))
        self.assertTrue(pp.MARKER_RE.search('<meta name=jw-protected content="1">'))


if __name__ == "__main__":
    unittest.main()
