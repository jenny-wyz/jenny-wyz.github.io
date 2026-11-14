#!/usr/bin/env python3
"""
Sync the Brain dump section from Notion.

Source: the page "Absolute dump". It has headed sections (Recyclable,
Not recyclable); every subpage under a heading becomes one entry, and the
heading becomes the entry's `group`, in the order the headings appear.
Subpages above the first heading have no group. Loose text on the page is
ignored.

Each entry becomes content/braindump/<slug>.md with its title, the page's
creation date, its group and its content. Reuses the block converter and
file writer from sync_notes.py: only files with a `notion_id` are managed,
hand-written files are left alone, no-change runs make no git diff.

Usage:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_braindump.py [--dry-run] [--verbose]
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
    lines = ["---", f"title: {sn.yaml_str(e['title'])}", f"date: {e['date']}", f"weight: {e['weight']}"]
    if e.get("group"):
        lines += [f"group: {sn.yaml_str(e['group'])}", f"group_weight: {e['group_weight']}"]
    lines += [f"notion_id: {e['id']}", "---"]
    return "\n".join(lines) + "\n"


def collect(blocks: list[dict]) -> list[tuple[dict, str, int]]:
    """Every child_page block with the heading above it: (block, group, group order)."""
    out, group, order = [], "", 0
    for b in blocks:
        t = b.get("type")
        if t in HEADINGS:
            group = plain(b[t].get("rich_text")); order += 1
        elif t == "child_page":
            out.append((b, group, order))
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
    src = cfg["braindump"]
    root = src.get("output_dir", "content/braindump")

    def log(msg: str) -> None:
        if args.verbose:
            print(f"  {msg}", file=sys.stderr)

    client = Notion(token, API_VERSION_NEW, args.verbose)
    print("Fetching brain dump…", file=sys.stderr)
    try:
        top = list(client.paginate("GET", f"/blocks/{src['page_id']}/children"))
    except NotionError as e:
        print(f"error: could not read the page: {e}", file=sys.stderr)
        return 1

    entries: list[dict] = []
    taken: dict[str, int] = {}
    for pos, (block, group, order) in enumerate(collect(top)):
        title = block["child_page"]["title"].strip() or "Untitled"
        conv = sn.Converter(client)
        body = "\n\n".join(conv.convert(conv.children(block["id"])))
        body = re.sub(r"\n\n(?=(?:\s*(?:-|\d+\.) ))", "\n", body)
        slug = sn.slugify(title)
        # dump titles repeat easily ("0", "1", "idea"): keep every slug unique
        taken[slug] = taken.get(slug, 0) + 1
        if taken[slug] > 1:
            slug = f"{slug}-{compact_id(block['id'])[:6]}"
        entries.append({
            "id": compact_id(block["id"]),
            "title": title,
            "slug": slug,
            "subjects": [],
            "date": (block.get("created_time") or "")[:10],
            "group": group,
            "group_weight": order,
            "weight": pos + 1,
            "body": body.strip() + "\n",
            "images": conv.images,
        })
    print(f"  {len(entries)} entr(y/ies)", file=sys.stderr)

    sn.front_matter = front_matter
    written, removed = sn.write_notes(entries, root, args.dry_run, log)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} changed entr(y/ies), removed {removed}; {len(entries)} in total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
