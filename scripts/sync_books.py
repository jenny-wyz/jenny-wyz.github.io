#!/usr/bin/env python3
"""
Sync the Reading section from Notion.

Reads "Jernier's List" (books) and "Jernier's Notes" (notes linked to books)
through the Notion API and writes data/books.json, which the Hugo templates
in layouts/reading/ render.

Usage:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_books.py [--config scripts/sync_config.json]
                                                          [--output data/books.json]
                                                          [--dry-run] [--verbose]

Design notes (why it is built this way):
  * Standard library only, so it runs anywhere Python 3.9+ exists.
  * Every request retries with backoff on 429/5xx and network errors.
  * Pagination is followed everywhere (books, notes, page bodies).
  * The output is deterministic (sorted keys and rows), so a nightly run with
    no changes produces no git diff and therefore no commit.
  * The file is only replaced when the sync produced a plausible result:
    at least one book, and not fewer than half of what the previous file had.
    A Notion outage can therefore never empty the site.
  * Rows with a checked "Private" checkbox (if that column exists) are skipped.
  * Newer Notion API (2025-09-03, data sources) is tried first, with a
    fallback to the 2022-06-28 database endpoints.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional

API = "https://api.notion.com/v1"
API_VERSION_NEW = "2025-09-03"
API_VERSION_OLD = "2022-06-28"
PAGE_SIZE = 100
MAX_RETRIES = 6
TIMEOUT = 30

CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")
STAR_RE = re.compile("⭐")  # ⭐ (the variation selector that may follow is ignored)

STATUS_ORDER = ["Reading", "Paused", "To Read", "Completed"]


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

class NotionError(RuntimeError):
    pass


class Notion:
    def __init__(self, token: str, version: str, verbose: bool = False):
        self.token = token
        self.version = version
        self.verbose = verbose

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"  {msg}", file=sys.stderr)

    def request(self, method: str, path: str, body: Optional[dict] = None,
                query: Optional[dict] = None) -> dict:
        url = f"{API}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
            "User-Agent": "jenny-wyz.github.io book sync",
        }
        delay = 1.0
        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                payload = e.read().decode("utf-8", errors="replace")
                if e.code in (400, 401, 403, 404):
                    # Permanent for this request: wrong token, no access, wrong id, bad version.
                    raise NotionError(f"{method} {path} -> HTTP {e.code}: {payload[:300]}") from e
                retry_after = e.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                self.log(f"HTTP {e.code} on {path}; retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                last_err = NotionError(f"{method} {path} -> HTTP {e.code}: {payload[:300]}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.log(f"network error on {path}: {e}; retry {attempt}/{MAX_RETRIES} in {delay:.1f}s")
                last_err = e
                wait = delay
            time.sleep(wait)
            delay = min(delay * 2, 30)
        raise NotionError(f"gave up on {method} {path}: {last_err}")

    def paginate(self, method: str, path: str, body: Optional[dict] = None,
                 query: Optional[dict] = None) -> Iterable[dict]:
        cursor = None
        while True:
            if method == "POST":
                b = dict(body or {})
                b["page_size"] = PAGE_SIZE
                if cursor:
                    b["start_cursor"] = cursor
                page = self.request(method, path, body=b)
            else:
                q = dict(query or {})
                q["page_size"] = PAGE_SIZE
                if cursor:
                    q["start_cursor"] = cursor
                page = self.request(method, path, query=q)
            for item in page.get("results", []):
                yield item
            if not page.get("has_more"):
                return
            cursor = page.get("next_cursor")
            if not cursor:
                return


def query_rows(token: str, source: dict, verbose: bool) -> tuple[list[dict], str]:
    """Return all rows of a database, trying the data-source API first."""
    ds_id = source.get("data_source_id")
    db_id = source.get("database_id")
    errors = []
    if ds_id:
        try:
            client = Notion(token, API_VERSION_NEW, verbose)
            rows = list(client.paginate("POST", f"/data_sources/{ds_id}/query"))
            return rows, API_VERSION_NEW
        except NotionError as e:
            errors.append(str(e))
    if db_id:
        try:
            client = Notion(token, API_VERSION_OLD, verbose)
            rows = list(client.paginate("POST", f"/databases/{db_id}/query"))
            return rows, API_VERSION_OLD
        except NotionError as e:
            errors.append(str(e))
    raise NotionError("could not query Notion source:\n  " + "\n  ".join(errors))


# --------------------------------------------------------------------------- #
# Property extraction
# --------------------------------------------------------------------------- #

def rich_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "".join(part.get("plain_text", "") for part in value).strip()


def prop(page: dict, name: str) -> Optional[dict]:
    props = page.get("properties") or {}
    p = props.get(name)
    if p is None:
        # Tolerate case or whitespace differences in the column name.
        key = name.strip().lower()
        for k, v in props.items():
            if k.strip().lower() == key:
                return v
    return p


def get_text(page: dict, name: str) -> str:
    p = prop(page, name)
    if not p:
        return ""
    t = p.get("type")
    if t == "title":
        return rich_text(p.get("title"))
    if t == "rich_text":
        return rich_text(p.get("rich_text"))
    if t == "select":
        return (p.get("select") or {}).get("name", "") or ""
    if t == "status":
        return (p.get("status") or {}).get("name", "") or ""
    if t == "formula":
        f = p.get("formula") or {}
        return str(f.get(f.get("type"), "") or "")
    if t == "url":
        return p.get("url") or ""
    if t == "number":
        n = p.get("number")
        return "" if n is None else str(n)
    return ""


def get_multi(page: dict, name: str) -> list[str]:
    p = prop(page, name)
    if not p:
        return []
    if p.get("type") == "multi_select":
        return [o.get("name", "") for o in p.get("multi_select") or [] if o.get("name")]
    if p.get("type") == "select":
        n = (p.get("select") or {}).get("name")
        return [n] if n else []
    return []


def get_date(page: dict, name: str) -> Optional[str]:
    p = prop(page, name)
    if not p or p.get("type") != "date":
        return None
    d = p.get("date") or {}
    start = d.get("start")
    return start[:10] if start else None


def get_checkbox(page: dict, name: str) -> bool:
    p = prop(page, name)
    return bool(p and p.get("type") == "checkbox" and p.get("checkbox"))


def get_relation_ids(page: dict, name: str) -> list[str]:
    p = prop(page, name)
    if not p or p.get("type") != "relation":
        return []
    return [compact_id(r.get("id", "")) for r in p.get("relation") or [] if r.get("id")]


def compact_id(s: str) -> str:
    """Notion ids appear with and without dashes; normalise to 32 hex chars."""
    compact = re.sub(r"[^0-9a-fA-F]", "", s or "").lower()
    return compact if len(compact) == 32 else (s or "").strip().lower()


def star_count(label: str) -> Optional[int]:
    if not label:
        return None
    n = len(STAR_RE.findall(label))
    if n == 0:
        m = re.search(r"\d", label)
        n = int(m.group()) if m else 0
    return n if 1 <= n <= 5 else None


def detect_lang(*texts: str) -> str:
    sample = " ".join(t for t in texts if t)
    if not sample:
        return "en"
    cjk = len(CJK_RE.findall(sample))
    return "zh" if cjk >= max(1, len(sample) // 4) else "en"


def is_collection(title: str) -> bool:
    return title.strip().lower().startswith("*collection*")


def clean_title(title: str) -> str:
    t = re.sub(r"^\*collection\*\s*:\s*", "", title.strip(), flags=re.IGNORECASE)
    return t


# --------------------------------------------------------------------------- #
# Page bodies (notes written inside a Notion page, not in a property)
# --------------------------------------------------------------------------- #

def block_to_markdown(block: dict, depth: int = 0) -> str:
    t = block.get("type")
    payload = block.get(t) or {}
    text = rich_text(payload.get("rich_text"))
    indent = "  " * depth
    if t == "paragraph":
        return text
    if t in ("heading_1", "heading_2", "heading_3"):
        level = int(t[-1])
        return f"{'#' * level} {text}"
    if t == "bulleted_list_item":
        return f"{indent}- {text}"
    if t == "numbered_list_item":
        return f"{indent}1. {text}"
    if t == "to_do":
        box = "[x]" if payload.get("checked") else "[ ]"
        return f"{indent}- {box} {text}"
    if t == "quote":
        return f"> {text}"
    if t == "callout":
        return f"> {text}"
    if t == "code":
        lang = payload.get("language") or ""
        return f"```{lang}\n{text}\n```"
    if t == "divider":
        return "---"
    return text  # toggle, etc.: keep the text, drop the structure


def fetch_body(client: Notion, block_id: str, depth: int = 0, max_blocks: int = 400) -> str:
    """Return the page body as simple Markdown. Nested children are followed one level."""
    lines: list[str] = []
    count = 0
    try:
        for block in client.paginate("GET", f"/blocks/{block_id}/children"):
            count += 1
            if count > max_blocks:
                lines.append("…")
                break
            md = block_to_markdown(block, depth)
            if md.strip():
                lines.append(md)
            if block.get("has_children") and depth < 1 and block.get("type") not in ("child_page", "child_database"):
                child = fetch_body(client, block["id"], depth + 1, max_blocks // 4)
                if child.strip():
                    lines.append(child)
    except NotionError as e:
        client.log(f"could not read body of {block_id}: {e}")
    return "\n\n".join(lines).strip()


# --------------------------------------------------------------------------- #
# Transform
# --------------------------------------------------------------------------- #

def build_books(book_rows: list[dict], note_rows: list[dict], names: dict,
                bodies: Optional[dict[str, str]] = None) -> list[dict]:
    bn = names["books"]
    nn = names["notes"]
    bodies = bodies or {}

    notes_by_book: dict[str, list[dict]] = {}
    for row in note_rows:
        if row.get("archived") or row.get("in_trash"):
            continue
        text = get_text(row, nn["text"])
        body = bodies.get(compact_id(row.get("id", "")), "")
        combined = "\n\n".join(p for p in (text, body) if p and p.strip() not in ("…", "..."))
        if not combined.strip():
            continue
        note = {
            "title": get_text(row, nn["title"]) or "Notes",
            "text": combined.strip(),
            "created": (row.get("created_time") or "")[:10],
        }
        for bid in get_relation_ids(row, nn["book"]):
            notes_by_book.setdefault(bid, []).append(note)

    books: list[dict] = []
    for row in book_rows:
        if row.get("archived") or row.get("in_trash"):
            continue
        if get_checkbox(row, bn.get("private", "Private")):
            continue
        raw_title = get_text(row, bn["title"])
        if not raw_title:
            continue
        bid = compact_id(row.get("id", ""))
        author = get_text(row, bn["author"])
        title = clean_title(raw_title)
        status = get_text(row, bn["status"]) or "To Read"
        book = {
            "id": bid,
            "title": title,
            "author": author,
            "status": status,
            "rating": star_count(get_text(row, bn["rating"])),
            "categories": sorted(get_multi(row, bn["categories"])),
            "started": get_date(row, bn["started"]),
            "completed": get_date(row, bn["completed"]),
            "added": (row.get("created_time") or "")[:10],
            "review": get_text(row, bn["review"]),
            "lang": detect_lang(title, author),
            "collection": is_collection(raw_title),
            "notes": sorted(notes_by_book.get(bid, []), key=lambda n: (n["created"], n["title"])),
        }
        body = bodies.get(bid, "")
        if body:
            book["body"] = body
        books.append(book)

    # Stable file order (the page sorts client-side), so unchanged data gives no git diff.
    books.sort(key=lambda b: (b["title"].lower(), b["id"]))
    return books


def validate(books: list[dict], previous_count: int) -> None:
    if not books:
        raise NotionError("sync produced zero books; refusing to overwrite the data file")
    if previous_count and len(books) < previous_count / 2:
        raise NotionError(
            f"sync produced {len(books)} books but the previous file had {previous_count}; "
            "this looks like a partial result, refusing to overwrite"
        )
    ids = [b["id"] for b in books]
    if len(ids) != len(set(ids)):
        raise NotionError("duplicate book ids in result")
    for b in books:
        if b["status"] not in STATUS_ORDER:
            print(f"warning: unexpected status '{b['status']}' for '{b['title']}'", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="scripts/sync_config.json")
    ap.add_argument("--output", default=None, help="override the output path from the config")
    ap.add_argument("--dry-run", action="store_true", help="fetch and validate but do not write")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        print("error: NOTION_TOKEN is not set", file=sys.stderr)
        return 2

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    output = args.output or cfg.get("output", "data/books.json")
    names = cfg["properties"]

    previous_count = 0
    if os.path.exists(output):
        try:
            with open(output, encoding="utf-8") as f:
                previous_count = len(json.load(f).get("books", []))
        except (json.JSONDecodeError, OSError, AttributeError):
            previous_count = 0

    print("Fetching books…", file=sys.stderr)
    book_rows, version = query_rows(token, cfg["books"], args.verbose)
    print(f"  {len(book_rows)} rows (API {version})", file=sys.stderr)
    print("Fetching notes…", file=sys.stderr)
    note_rows, _ = query_rows(token, cfg["notes"], args.verbose)
    print(f"  {len(note_rows)} rows", file=sys.stderr)

    bodies: dict[str, str] = {}
    if cfg.get("fetch_page_bodies", True):
        client = Notion(token, version, args.verbose)
        print("Fetching note bodies…", file=sys.stderr)
        for row in note_rows:
            bid = compact_id(row.get("id", ""))
            bodies[bid] = fetch_body(client, row["id"])
        # Book pages may also carry text in their body; include it when present.
        print("Fetching book bodies…", file=sys.stderr)
        for row in book_rows:
            bid = compact_id(row.get("id", ""))
            bodies[bid] = fetch_body(client, row["id"])

    books = build_books(book_rows, note_rows, names, bodies)
    validate(books, previous_count)

    doc = {"books": books}
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.dry_run:
        print(f"dry run: {len(books)} books, {sum(len(b['notes']) for b in books)} notes attached", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    tmp = output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, output)
    print(f"wrote {output}: {len(books)} books", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except NotionError as err:
        print(f"error: {err}", file=sys.stderr)
        print("The existing data file was left untouched.", file=sys.stderr)
        sys.exit(1)
