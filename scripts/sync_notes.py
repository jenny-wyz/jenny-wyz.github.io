#!/usr/bin/env python3
"""
Sync the Notes section from Notion.

Reads the "Jernier's Notes on Stuff" database through the Notion API and
writes one Markdown file per note with the "Publish" checkbox ticked into
content/notes/<subject>/. Images in a note are downloaded next to it (the
note then becomes a Hugo page bundle, content/notes/<subject>/<slug>/index.md).

Usage:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_notes.py [--config scripts/sync_config.json]
                                                          [--dry-run] [--verbose]

Rules of the road:
  * Only pages with Publish ticked are written. A page that gets unticked,
    deleted or archived in Notion disappears from the site on the next run.
  * The sync owns exactly the files that carry a `notion_id` in their front
    matter. Hand-written notes (no notion_id) are never touched.
  * The output is deterministic, so a run with no changes makes no git diff.
  * A Notion outage never wipes the section: if the query fails, nothing is
    written or deleted. If it succeeds, the result is trusted as is (an empty
    Publish set is a legitimate choice, not an error).
  * A new subject gets its page, content/subjects/<subject>/_index.md, created
    on demand with just a title.
  * Reuses the HTTP client and property helpers from sync_books.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.request
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_books import (  # noqa: E402
    Notion, NotionError, compact_id, get_checkbox, get_date, get_multi,
    get_text, prop, query_rows,
)

IMAGE_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
             "image/webp": ".webp", "image/svg+xml": ".svg", "image/heic": ".heic"}
MAX_BLOCKS = 2000
MAX_DEPTH = 6


# --------------------------------------------------------------------------- #
# Rich text and blocks to Markdown
# --------------------------------------------------------------------------- #

def inline(parts) -> str:
    """Notion rich text (with annotations) to inline Markdown."""
    if not isinstance(parts, list):
        return ""
    out = []
    for part in parts:
        t = part.get("type")
        if t == "equation":
            out.append(f"${(part.get('equation') or {}).get('expression', '')}$")
            continue
        text = part.get("plain_text", "")
        if t == "mention":
            m = part.get("mention") or {}
            if m.get("type") == "date":
                d = m.get("date") or {}
                text = d.get("start", "") + (f" to {d['end']}" if d.get("end") else "")
        if not text:
            continue
        a = part.get("annotations") or {}
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = text.strip()
        if core:
            if a.get("code"):
                core = f"`{core}`"
            else:
                if a.get("bold"):
                    core = f"**{core}**"
                if a.get("italic"):
                    core = f"*{core}*"
                if a.get("strikethrough"):
                    core = f"~~{core}~~"
            href = part.get("href") or ((part.get("text") or {}).get("link") or {}).get("url")
            if href and t != "mention":
                core = f"[{core}]({href})"
        out.append(lead + core + trail)
    return "".join(out)


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "note"


class Converter:
    """Turns a page's block tree into Markdown, collecting image downloads."""

    def __init__(self, client: Optional[Notion]):
        self.client = client
        self.images: list[tuple[str, str]] = []   # (url, local filename)
        self.count = 0

    def children(self, block_id: str):
        if self.client is None:
            return []
        try:
            return list(self.client.paginate("GET", f"/blocks/{block_id}/children"))
        except NotionError as e:
            self.client.log(f"could not read children of {block_id}: {e}")
            return []

    def convert(self, blocks: list[dict], depth: int = 0) -> list[str]:
        lines: list[str] = []
        numbered = 0
        for block in blocks:
            self.count += 1
            if self.count > MAX_BLOCKS:
                lines.append("…")
                break
            t = block.get("type")
            numbered = numbered + 1 if t == "numbered_list_item" else 0
            lines.extend(self.block(block, depth, numbered))
        return lines

    def block(self, block: dict, depth: int, number: int) -> list[str]:
        t = block.get("type") or ""
        p = block.get(t) or {}
        text = inline(p.get("rich_text"))
        indent = "  " * depth
        kids = self.children(block["id"]) if block.get("has_children") and depth < MAX_DEPTH else []

        def nested(extra_depth: int = 1) -> list[str]:
            return self.convert(kids, depth + extra_depth) if kids else []

        if t in ("bulleted_list_item", "numbered_list_item", "to_do"):
            if t == "numbered_list_item":
                marker = f"{number}."
            elif t == "to_do":
                marker = "- [x]" if p.get("checked") else "- [ ]"
            else:
                marker = "-"
            return [f"{indent}{marker} {text}"] + nested()

        # Everything below is a top-level block; indentation only applies to lists.
        if t == "paragraph":
            return ([text] if text else []) + nested(0)
        if t in ("heading_1", "heading_2", "heading_3"):
            level = int(t[-1]) + 1          # Notion h1 -> ## so the page title stays the only h1
            return [f"{'#' * level} {text}"] + nested(0)
        if t == "quote":
            body = [text] + nested(0)
            return ["> " + "\n> ".join(body)]
        if t == "callout":
            icon = (p.get("icon") or {}).get("emoji", "")
            body = [(icon + " " + text).strip()] + nested(0)
            return ["> " + "\n> ".join(body)]
        if t == "toggle":
            return [f"**{text}**"] + nested(0)
        if t == "code":
            lang = p.get("language") or ""
            lang = "" if lang == "plain text" else lang
            return [f"```{lang}\n{inline(p.get('rich_text'))}\n```"]
        if t == "equation":
            return [f"$$\n{p.get('expression', '')}\n$$"]
        if t == "divider":
            return ["---"]
        if t == "table":
            return [self.table(kids, bool(p.get("has_column_header")))]
        if t == "image":
            return [self.image(p)]
        if t in ("bookmark", "embed", "link_preview", "video", "file", "pdf"):
            url = (p.get("external") or {}).get("url") or (p.get("file") or {}).get("url") or p.get("url", "")
            cap = inline(p.get("caption")) or url
            return [f"[{cap}]({url})"] if url else []
        if t in ("column_list", "column", "synced_block"):
            return nested(0)
        if t == "table_of_contents" or t.startswith("child_"):
            return []
        return [text] if text else []

    def table(self, rows: list[dict], header: bool) -> str:
        cells = [[inline(c) for c in (r.get("table_row") or {}).get("cells", [])] for r in rows
                 if r.get("type") == "table_row"]
        if not cells:
            return ""
        width = max(len(r) for r in cells)
        cells = [r + [""] * (width - len(r)) for r in cells]
        esc = lambda s: s.replace("|", "\\|")
        if not header:
            cells.insert(0, [""] * width)
        out = ["| " + " | ".join(esc(c) for c in cells[0]) + " |",
               "|" + "---|" * width]
        out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in cells[1:]]
        return "\n".join(out)

    def image(self, p: dict) -> str:
        url = (p.get("external") or {}).get("url") or (p.get("file") or {}).get("url") or ""
        if not url:
            return ""
        n = len(self.images) + 1
        ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext not in IMAGE_EXT.values():
            ext = ".jpg"
        name = f"img-{n}{ext}"
        self.images.append((url, name))
        return f"![{inline(p.get('caption'))}]({name})"


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #

def yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def front_matter(note: dict) -> str:
    lines = ["---", f"title: {yaml_str(note['title'])}", f"date: {note['date']}"]
    lines.append("subjects: [" + ", ".join(yaml_str(t) for t in note["subjects"]) + "]")
    lines.append(f"notion_id: {note['id']}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def build_note(row: dict, names: dict, body: str, images: list[tuple[str, str]]) -> Optional[dict]:
    if row.get("archived") or row.get("in_trash"):
        return None
    if not get_checkbox(row, names["publish"]):
        return None
    title = get_text(row, names["title"]).strip()
    if not title:
        return None
    icon = row.get("icon") or {}
    if icon.get("type") == "emoji":
        title = f"{icon['emoji']} {title}"
    subjects = sorted({slugify(t) for t in get_multi(row, names["subjects"]) if t.strip()}) or ["misc"]
    date = get_date(row, names["date"]) or (row.get("created_time") or "")[:10]
    return {
        "id": compact_id(row.get("id", "")),
        "title": title,
        "slug": slugify(get_text(row, names["title"])),
        "subjects": subjects,
        "date": date[:10],
        "body": body.strip() + "\n",
        "images": images,
    }


def read_front_matter(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4000)
    except OSError:
        return {}
    m = re.match(r"^---\n(.*?)\n---", head, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def managed_files(root: str) -> dict[str, str]:
    """notion_id -> path for every synced note currently in the tree."""
    found = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".md") and f != "_index.md":
                path = os.path.join(dirpath, f)
                nid = read_front_matter(path).get("notion_id")
                if nid:
                    found[nid] = path
    return found


def ensure_subject(root: str, subject: str) -> None:
    """Create content/subjects/<subject>/_index.md if the subject is new."""
    d = os.path.join(os.path.dirname(root.rstrip("/")), "subjects", subject)
    idx = os.path.join(d, "_index.md")
    if os.path.exists(idx):
        return
    os.makedirs(d, exist_ok=True)
    nice = subject.replace("-", " ").title()
    with open(idx, "w", encoding="utf-8") as f:
        f.write(f'---\ntitle: "{nice}"\n---\n')


def download(url: str, dest: str, log) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jenny-wyz.github.io notes sync"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return True
    except Exception as e:  # noqa: BLE001
        log(f"image download failed for {dest}: {e}")
        return False


def write_notes(notes: list[dict], root: str, dry_run: bool, log) -> tuple[int, int]:
    before = managed_files(root)
    keep: set[str] = set()
    written = 0
    for n in notes:
        for subject in n["subjects"]:
            ensure_subject(root, subject)
        base = root
        bundle = bool(n["images"])
        if bundle:
            path = os.path.join(base, n["slug"], "index.md")
        else:
            path = os.path.join(base, n["slug"] + ".md")
        text = front_matter(n) + "\n" + n["body"]
        old = before.get(n["id"])
        if old and os.path.normpath(old) != os.path.normpath(path):
            # Renamed or moved in Notion: remove the old file (or bundle).
            if not dry_run:
                old_dir = os.path.dirname(old)
                if os.path.basename(old) == "index.md":
                    shutil.rmtree(old_dir, ignore_errors=True)
                else:
                    os.remove(old)
            log(f"moved {old} -> {path}")
        keep.add(path)
        current = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                current = f.read()
        if current != text:
            written += 1
            log(f"write {path}")
            if not dry_run:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
        if bundle and not dry_run:
            for url, name in n["images"]:
                dest = os.path.join(os.path.dirname(path), name)
                if not os.path.exists(dest):
                    download(url, dest, log)
    removed = 0
    current_ids = {n["id"] for n in notes}
    for nid, path in before.items():
        if nid not in current_ids:
            removed += 1
            log(f"remove {path} (unpublished or deleted in Notion)")
            if not dry_run:
                if os.path.basename(path) == "index.md":
                    shutil.rmtree(os.path.dirname(path), ignore_errors=True)
                else:
                    os.remove(path)
    return written, removed


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="scripts/sync_config.json")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report but do not write or delete")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        print("error: NOTION_TOKEN is not set", file=sys.stderr)
        return 2

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    src = cfg["site_notes"]
    names = cfg["properties"]["site_notes"]
    root = src.get("output_dir", "content/notes")

    def log(msg: str) -> None:
        if args.verbose:
            print(f"  {msg}", file=sys.stderr)

    print("Fetching notes…", file=sys.stderr)
    rows, version = query_rows(token, src, args.verbose)
    print(f"  {len(rows)} rows (API {version})", file=sys.stderr)
    client = Notion(token, version, args.verbose)

    notes: list[dict] = []
    for row in rows:
        if not get_checkbox(row, names["publish"]):
            continue
        conv = Converter(client)
        body = "\n\n".join(conv.convert(conv.children(row["id"])))
        # Lists are tighter without blank lines between items.
        body = re.sub(r"\n\n(?=(?:\s*(?:-|\d+\.) ))", "\n", body)
        note = build_note(row, names, body, conv.images)
        if note:
            notes.append(note)
    notes.sort(key=lambda n: n["slug"])

    # Two notes with the same title would overwrite each other.
    seen: dict[str, dict] = {}
    for n in notes:
        key = n["slug"]
        if key in seen:
            n["slug"] += "-" + n["id"][:6]
        seen[key] = n

    written, removed = write_notes(notes, root, args.dry_run, log)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} changed note(s), removed {removed}; {len(notes)} published in total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
