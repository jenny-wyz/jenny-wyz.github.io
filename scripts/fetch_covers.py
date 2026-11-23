#!/usr/bin/env python3
"""
Fetch book covers from Open Library for the Reading section.

Reads data/books.json, looks each book up on Open Library, downloads a cover
when there is a confident match, and stores it as
assets/covers/<title> - <id>.jpg (see cover_name).
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

Your own covers: put an image (jpg, png or webp) in assets/covers/ and it wins
over Open Library, for any book, collections included. Name it after the book,

    assets/covers/The Power of Now.jpg      the title as it is in Notion
    assets/covers/<32-character id>.jpg     or the page id from the Notion link

and the next run renames it to "<title> - <id>.jpg", shrinks it, and marks the
book "manual" in data/covers.json so it is never looked up or replaced. To
change a cover later, overwrite that file. A file that matches no book is left
alone and reported. `--manual-only` does just this part, without Open Library.

File names: every cover ends up as "<title> - <id>.jpg", readable in the
folder; the site finds it by the id at the end (layouts/partials/reading/
books.html). When a title changes in Notion, the next run renames the file.
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


ID_RE = re.compile(r"[0-9a-f]{32}")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
# "<anything> - <id>.jpg", or "<id>.jpg" from before titles were added
COVER_RE = re.compile(r"^(?:.* - )?([0-9a-f]{32})\.jpg$")
UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_title(title: str) -> str:
    """The title, made safe as a file name on Windows, Mac and Linux."""
    t = UNSAFE_RE.sub(" ", unicodedata.normalize("NFC", title or ""))
    t = re.sub(r"\s+", " ", t).strip().rstrip(". ")
    return t[:80].rstrip(". ") or "untitled"


def cover_name(book: dict) -> str:
    return f"{safe_title(book['title'])} - {book['id']}.jpg"


def find_covers(dest: str) -> dict[str, str]:
    """id -> file name, for every cover file in dest."""
    found = {}
    for name in os.listdir(dest):
        m = COVER_RE.match(name)
        if m:
            found[m.group(1)] = name
    return found


def has_cover(dest: str, book_id: str) -> bool:
    return book_id in find_covers(dest)


def adopt_manual(books: list[dict], cache: dict, dest: str, today: str, dry_run: bool = False, verbose: bool = False) -> int:
    """Take over the images someone put into `dest` by hand. Returns how many."""
    ids = {b["id"]: b for b in books}
    by_title: dict[str, list[dict]] = {}
    for b in books:
        by_title.setdefault(norm(b["title"]), []).append(b)

    adopted = 0
    for name in sorted(os.listdir(dest)):
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext not in IMAGE_EXTS:
            continue
        path = os.path.join(dest, name)
        m = COVER_RE.match(name)
        if m:
            # Already in place. Ours unless Open Library put it there.
            bid = m.group(1)
            if bid in ids:
                if (cache.get(bid) or {}).get("status") not in ("ok", "manual"):
                    cache[bid] = {"status": "manual", "checked": today, "title": ids[bid]["title"]}
                    adopted += 1
                    log(verbose, f"manual: {ids[bid]['title']}")
                want = cover_name(ids[bid])
                if name != want and not dry_run:
                    if os.path.exists(os.path.join(dest, want)):
                        os.remove(os.path.join(dest, want))
                    os.rename(path, os.path.join(dest, want))
            elif bid not in cache:
                print(f"cover {name}: no book with this id (yet); left alone", file=sys.stderr)
            continue
        # A name to resolve: an id with another extension, "...-<id>", or a title.
        tail = re.search(r"([0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$", stem.lower())
        book = ids.get(tail.group(1).replace("-", "")) if tail else None
        if book is None:
            found = by_title.get(norm(stem), [])
            if len(found) == 1:
                book = found[0]
            else:
                why = "several books have this title; use the id" if found else "no book with this title or id (yet)"
                print(f"cover {name}: {why}; left alone", file=sys.stderr)
                continue
        with open(path, "rb") as f:
            data = f.read()
        try:
            from PIL import Image  # type: ignore  # noqa: F401
        except ImportError:
            if ext not in (".jpg", ".jpeg"):
                print(f"cover {name}: needs Pillow to convert to jpg; left alone", file=sys.stderr)
                continue
        if not dry_run:
            for old in [n for n in os.listdir(dest) if COVER_RE.match(n) and COVER_RE.match(n).group(1) == book["id"]]:
                os.remove(os.path.join(dest, old))           # the cover it replaces
            with open(os.path.join(dest, cover_name(book)), "wb") as f:
                f.write(shrink(data))
            if name != cover_name(book):
                os.remove(path)
        cache[book["id"]] = {"status": "manual", "checked": today, "title": book["title"]}
        adopted += 1
        log(verbose, f"manual: {book['title']}  ({name})")
    return adopted


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--books", default="data/books.json")
    ap.add_argument("--cache", default="data/covers.json")
    ap.add_argument("--dest", default="assets/covers")
    ap.add_argument("--limit", type=int, default=0, help="look up at most N books this run (0 = all)")
    ap.add_argument("--recheck-days", type=int, default=90)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between Open Library requests")
    ap.add_argument("--manual-only", action="store_true", help="only take over covers put into --dest by hand; no Open Library")
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
    manual = adopt_manual(books, cache, args.dest, today.isoformat(), args.dry_run, args.verbose)
    todo = []
    for b in books:
        if args.manual_only or b.get("collection"):
            continue
        entry = cache.get(b["id"])
        if entry:
            if entry.get("status") == "manual":
                if has_cover(args.dest, b["id"]):
                    continue
                entry = None          # the hand-made cover is gone: look it up again
                cache.pop(b["id"], None)
        if entry:
            if entry.get("status") == "ok" and has_cover(args.dest, b["id"]):
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
            with open(os.path.join(args.dest, cover_name(b)), "wb") as f:
                f.write(shrink(img))
        cache[b["id"]] = {"status": "ok", "cover_i": cid, "checked": today.isoformat(), "title": b["title"]}
        hits += 1
        log(args.verbose, f"ok: {b['title']} (cover {cid})")

    # Remove covers for books that no longer exist (only ones this script
    # knows from an earlier run; a file it has never seen is left alone).
    ids = {b["id"] for b in books}
    for bid, name in find_covers(args.dest).items():
        if bid in cache and bid not in ids and not args.dry_run:
            os.remove(os.path.join(args.dest, name))
            cache.pop(bid, None)

    if not args.dry_run:
        with open(args.cache, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(cache.items())), f, ensure_ascii=False, indent=2)
            f.write("\n")
    count = lambda st: sum(1 for v in cache.values() if v.get("status") == st)  # noqa: E731
    print(f"done: {hits} new from Open Library ({count('ok')} total), {manual} new by hand ({count('manual')} total)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
