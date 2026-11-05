#!/usr/bin/env python3
"""
Sync the Journal section from Notion.

Reads "Jernier's Tagebuch" and writes one Markdown file per entry with the
"Publish" checkbox ticked into content/journal/. An entry is a week: the
"Week" date range becomes the page date (start) and `week_end`; the title is
the page name ("6. bis 12. September 2026"). Photos of the notebook pages
are downloaded into a page bundle next to the entry and shrunk to a sensible
web size.

Reuses the block converter and file writer from sync_notes.py, so the same
rules apply: only ticked pages are written, files carrying a `notion_id`
belong to the sync, hand-written files are left alone, a run with no
changes makes no git diff.

Usage:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_journal.py [--dry-run] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_notes as sn  # noqa: E402
from sync_books import Notion, compact_id, get_checkbox, get_text, prop, query_rows  # noqa: E402

MAX_IMAGE_PX = 1800
JPEG_QUALITY = 82


def get_date_range(page: dict, name: str) -> tuple[str, str]:
    p = prop(page, name) or {}
    d = p.get("date") or {}
    start = (d.get("start") or "")[:10]
    end = (d.get("end") or start)[:10]
    return start, end


def front_matter(entry: dict) -> str:
    lines = [
        "---",
        f"title: {sn.yaml_str(entry['title'])}",
        f"date: {entry['date']}",
        f"week_end: {entry['week_end']}",
        f"notion_id: {entry['id']}",
        "---",
    ]
    return "\n".join(lines) + "\n"


def build_entry(row: dict, names: dict, body: str, images: list) -> Optional[dict]:
    if row.get("archived") or row.get("in_trash"):
        return None
    if not get_checkbox(row, names["publish"]):
        return None
    title = get_text(row, names["title"]).strip()
    if not title:
        return None
    start, end = get_date_range(row, names["week"])
    if not start:
        start = end = (row.get("created_time") or "")[:10]
    return {
        "id": compact_id(row.get("id", "")),
        "title": title,
        "slug": start,               # one entry per week: the start date is the slug
        "subjects": [],              # no subject pages for journal entries
        "date": start,
        "week_end": end,
        "body": body.strip() + "\n",
        "images": images,
    }


def shrink_image(path: str, log) -> None:
    """Downscale a downloaded photo in place; the originals are phone-sized."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        log("Pillow not installed; keeping full-size image")
        return
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX))
            if path.lower().endswith((".jpg", ".jpeg")):
                im.convert("RGB").save(path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            elif path.lower().endswith(".png"):
                im.save(path, "PNG", optimize=True)
            else:
                im.save(path)
    except Exception as e:  # noqa: BLE001
        log(f"could not shrink {path}: {e}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="scripts/sync_config.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        print("error: NOTION_TOKEN is not set", file=sys.stderr)
        return 2
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    src = cfg["journal"]
    names = cfg["properties"]["journal"]
    root = src.get("output_dir", "content/journal")

    def log(msg: str) -> None:
        if args.verbose:
            print(f"  {msg}", file=sys.stderr)

    print("Fetching journal entries…", file=sys.stderr)
    rows, version = query_rows(token, src, args.verbose)
    print(f"  {len(rows)} rows (API {version})", file=sys.stderr)
    client = Notion(token, version, args.verbose)

    entries: list[dict] = []
    for row in rows:
        if not get_checkbox(row, names["publish"]):
            continue
        conv = sn.Converter(client)
        body = "\n\n".join(conv.convert(conv.children(row["id"])))
        body = re.sub(r"\n\n(?=(?:\s*(?:-|\d+\.) ))", "\n", body)
        entry = build_entry(row, names, body, conv.images)
        if entry:
            entries.append(entry)
    entries.sort(key=lambda e: e["slug"])

    # The notes writer handles files, renames, removals and image downloads.
    sn.front_matter = front_matter          # journal front matter instead of the notes one
    written, removed = sn.write_notes(entries, root, args.dry_run, log)
    if not args.dry_run:
        for e in entries:
            if e["images"]:
                for _, name in e["images"]:
                    path = os.path.join(root, e["slug"], name)
                    if os.path.exists(path) and os.path.getsize(path) > 400_000:
                        shrink_image(path, log)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} changed entr(y/ies), removed {removed}; {len(entries)} published in total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
