#!/usr/bin/env python3
"""
Sync the Essays section from Notion.

Source: the page "Jernier 随笔". It has headed sections; only the subpages
under the heading named in the config (`publish_heading`, "Ver 1") are
published. Subpages under any other heading (Ver 0, the raw drafts) are
never fetched, never written, never touched.

Each published subpage becomes content/essays/<slug>.md with its title, the
page's creation date and its content. Reuses the block converter and file
writer from sync_notes.py: only files with a `notion_id` are managed,
hand-written files are left alone, no-change runs make no git diff.

Usage:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_essays.py [--dry-run] [--verbose]
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
from sync_books import API_VERSION_NEW, Notion, NotionError, compact_id  # noqa: E402

HEADINGS = ("heading_1", "heading_2", "heading_3")


def plain(rich) -> str:
    return "".join(p.get("plain_text", "") for p in (rich or [])).strip()


def front_matter(e: dict) -> str:
    return (f"---\ntitle: {sn.yaml_str(e['title'])}\ndate: {e['date']}\n"
            f"weight: {e['weight']}\nnotion_id: {e['id']}\n---\n")


def collect(blocks: list[dict], publish_heading: str) -> list[dict]:
    """The child_page blocks that sit under the publish heading, in order."""
    out, current = [], None
    for b in blocks:
        t = b.get("type")
        if t in HEADINGS:
            current = plain(b[t].get("rich_text"))
        elif t == "child_page" and current == publish_heading:
            out.append(b)
    return out


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
    src = cfg["essays"]
    root = src.get("output_dir", "content/essays")

    def log(msg: str) -> None:
        if args.verbose:
            print(f"  {msg}", file=sys.stderr)

    client = Notion(token, API_VERSION_NEW, args.verbose)
    print("Fetching essays…", file=sys.stderr)
    try:
        top = list(client.paginate("GET", f"/blocks/{src['page_id']}/children"))
    except NotionError as e:
        print(f"error: could not read the essays page: {e}", file=sys.stderr)
        return 1

    essays: list[dict] = []
    for pos, block in enumerate(collect(top, src.get("publish_heading", "Ver 1"))):
        title = block["child_page"]["title"].strip()
        if not title:
            continue
        conv = sn.Converter(client)
        body = "\n\n".join(conv.convert(conv.children(block["id"])))
        body = re.sub(r"\n\n(?=(?:\s*(?:-|\d+\.) ))", "\n", body)
        essays.append({
            "id": compact_id(block["id"]),
            "title": title,
            "slug": sn.slugify(title),
            "subjects": [],
            "date": (block.get("created_time") or "")[:10],
            "weight": pos + 1,
            "body": body.strip() + "\n",
            "images": conv.images,
        })
    print(f"  {len(essays)} published essay(s)", file=sys.stderr)

    sn.front_matter = front_matter
    written, removed = sn.write_notes(essays, root, args.dry_run, log)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} changed essay(s), removed {removed}; {len(essays)} in total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
