#!/usr/bin/env python3
"""
Fetch book covers from Open Library for the Reading section.

Reads data/books.json, looks each book up on Open Library, downloads a cover
when there is a confident match, and stores it as assets/covers/<id>.jpg.
Results (hits and misses) are cached in data/covers.json so each book is
looked up once; misses are retried after `recheck_days`.

Usage:
    python3 scripts/fetch_covers.py [--books data/books.json] [--cache data/covers.json]
                                    [--dest assets/covers] [--limit N] [--dry-run] [-v]

The switch: covers are only fetched when this script runs. The nightly workflow
runs it when its COVERS variable is "true" (see .github/workflows/sync-books.yaml),
and the site only shows covers when params.reading.covers is true in
config/_default/params.toml. Turn either off and the shelf falls back to the
typographic spines, which need no external data at all.

Matching is deliberately conservative: a wrong cover is worse than no cover.
A hit requires the normalised Open Library title to match the book title and,
when an author is known, the author's surname to appear in the result's authors.
Collections (several books under one entry) are skipped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

SEARCH = "https://openlibrary.org/search.json"
COVER = "https://covers.openlibrary.org/b/id/{id}-L.jpg?default=false"
UA = "jenny-wyz.github.io cover fetch (github.com/jenny-wyz/jenny-wyz.github.io)"
TIMEOUT = 30
MAX_WIDTH = 360          # stored width in px; Hugo resizes further for display
JPEG_QUALITY = 82
MIN_BYTES = 2000         # Open Library returns a tiny placeholder for missing images

CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")


def log(verbose: bool, msg: str) -> None:
    if verbose:
        print(f"  {msg}", file=sys.stderr)


def http_get(url: str, retries: int = 4) -> Optional[bytes]:
    delay = 1.0
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            return None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            return None
    return None


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", s)
    return s.strip()


def surname(author: str) -> str:
    a = norm(author.split(",")[0])
    parts = a.split()
    return parts[-1] if parts else ""


def title_matches(book_title: str, result_title: str) -> bool:
    a, b = norm(book_title), norm(result_title)
    if not a or not b:
        return False
    if a == b:
        return True
    # Allow subtitles and translated-title variants: one must contain the other,
    # and the shorter must carry most of the information.
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return short in long_ and len(short) >= max(4, int(len(long_) * 0.5))


def author_matches(author: str, names: list[str]) -> bool:
    if not author:
        return True
    s = surname(author)
    if not s:
        return True
    hay = " ".join(norm(n) for n in names)
    return s in hay.split() or (len(s) >= 4 and s in hay)


def pick_cover(book: dict, docs: list[dict]) -> Optional[int]:
    best = None
    for d in docs:
        cid = d.get("cover_i")
        if not cid:
            continue
        if not title_matches(book["title"], d.get("title", "")):
            continue
        if not author_matches(book.get("author", ""), d.get("author_name") or []):
            continue
        # Prefer results with more editions (a proxy for the canonical work).
        score = d.get("edition_count") or 0
        if best is None or score > best[0]:
            best = (score, cid)
    return best[1] if best else None


def search(book: dict, verbose: bool) -> Optional[int]:
    params = {"title": book["title"], "limit": "8",
              "fields": "key,title,author_name,cover_i,edition_count"}
    if book.get("author"):
        params["author"] = book["author"].split(",")[0]
    url = SEARCH + "?" + urllib.parse.urlencode(params)
    raw = http_get(url)
    if raw is None:
        log(verbose, f"search failed: {book['title']}")
        return None
    try:
        docs = json.loads(raw.decode("utf-8")).get("docs", [])
    except json.JSONDecodeError:
        return None
    cid = pick_cover(book, docs)
    if cid is None and book.get("author") and docs == []:
        # Retry once without the author; some records have no author field.
        params.pop("author", None)
        raw = http_get(SEARCH + "?" + urllib.parse.urlencode(params))
        if raw:
            try:
                cid = pick_cover(book, json.loads(raw.decode("utf-8")).get("docs", []))
            except json.JSONDecodeError:
                cid = None
    return cid


def shrink(data: bytes) -> bytes:
    """Downscale with Pillow when available; otherwise keep the original bytes."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return data
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGB")
    if im.width > MAX_WIDTH:
        h = round(im.height * MAX_WIDTH / im.width)
        im = im.resize((MAX_WIDTH, h), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--books", default="data/books.json")
    ap.add_argument("--cache", default="data/covers.json")
    ap.add_argument("--dest", default="assets/covers")
    ap.add_argument("--limit", type=int, default=0, help="look up at most N books this run (0 = all)")
    ap.add_argument("--recheck-days", type=int, default=90)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between Open Library requests")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    with open(args.books, encoding="utf-8") as f:
        books = json.load(f)["books"]
    cache: dict = {}
    if os.path.exists(args.cache):
        with open(args.cache, encoding="utf-8") as f:
            cache = json.load(f)
    os.makedirs(args.dest, exist_ok=True)

    today = dt.date.today()
    todo = []
    for b in books:
        if b.get("collection"):
            continue
        entry = cache.get(b["id"])
        if entry:
            if entry.get("status") == "ok" and os.path.exists(os.path.join(args.dest, f"{b['id']}.jpg")):
                continue
            if entry.get("status") == "miss":
                checked = dt.date.fromisoformat(entry.get("checked", "1970-01-01"))
                if (today - checked).days < args.recheck_days:
                    continue
        todo.append(b)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} books to look up, {len(cache)} cached", file=sys.stderr)

    hits = 0
    for i, b in enumerate(todo):
        if i:
            time.sleep(args.delay)
        cid = search(b, args.verbose)
        if cid is None:
            cache[b["id"]] = {"status": "miss", "checked": today.isoformat(), "title": b["title"]}
            log(args.verbose, f"miss: {b['title']}")
            continue
        img = http_get(COVER.format(id=cid))
        if not img or len(img) < MIN_BYTES:
            cache[b["id"]] = {"status": "miss", "checked": today.isoformat(), "title": b["title"]}
            log(args.verbose, f"no image for cover {cid}: {b['title']}")
            continue
        if not args.dry_run:
            with open(os.path.join(args.dest, f"{b['id']}.jpg"), "wb") as f:
                f.write(shrink(img))
        cache[b["id"]] = {"status": "ok", "cover_i": cid, "checked": today.isoformat(), "title": b["title"]}
        hits += 1
        log(args.verbose, f"ok: {b['title']} (cover {cid})")

    # Remove covers for books that no longer exist.
    ids = {b["id"] for b in books}
    for name in os.listdir(args.dest):
        stem, ext = os.path.splitext(name)
        if ext == ".jpg" and stem not in ids and not args.dry_run:
            os.remove(os.path.join(args.dest, name))
            cache.pop(stem, None)

    if not args.dry_run:
        with open(args.cache, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(cache.items())), f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(f"done: {hits} new covers, {sum(1 for v in cache.values() if v.get('status') == 'ok')} total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
