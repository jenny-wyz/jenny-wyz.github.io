#!/usr/bin/env python3
"""
Sync the Recipes section from Notion.

The source is not a database but a tree of pages:

    Recipes                       (one top-level page)
    ├── 中                        (a cuisine page; its emoji icon is kept)
    │   ├── 番茄炒蛋              (a recipe page)
    │   ├── ## 面条               (a heading on the cuisine page starts a group)
    │   ├── 炒面
    │   └── ...
    ├── 西
    └── ...

Each cuisine becomes a folder content/recipes/<cuisine-slug>/ with an
_index.md (title, icon, weight by position), and each recipe page becomes
a Markdown file in it with the recipe's title, icon, group, cuisine and
position. Loose text on a cuisine page (ideas, not pages) is ignored.

Reuses the block converter and file writer from sync_notes.py: only files
carrying a `notion_id` are managed, hand-written files are left alone, and a
run with no changes makes no git diff.

Usage:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_recipes.py [--dry-run] [--verbose]
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


def page_icon(client: Notion, page_id: str) -> str:
    try:
        page = client.request("GET", f"/pages/{page_id}")
    except NotionError:
        return ""
    icon = page.get("icon") or {}
    return icon.get("emoji", "") if icon.get("type") == "emoji" else ""


def walk_cuisine(client: Notion, cuisine_block: dict, cuisine_slug: str, conv_factory) -> list[dict]:
    """Return the recipes of one cuisine page, in page order, with their group."""
    recipes = []
    group, group_weight = "", 0
    for pos, block in enumerate(client.paginate("GET", f"/blocks/{cuisine_block['id']}/children")):
        t = block.get("type")
        if t in HEADINGS:
            group = plain(block[t].get("rich_text"))
            group_weight += 1
            continue
        if t != "child_page":
            continue                                    # loose ideas, dividers, empty lines
        title = block["child_page"]["title"].strip()
        if not title:
            continue
        conv = conv_factory()
        body = "\n\n".join(conv.convert(conv.children(block["id"])))
        body = re.sub(r"\n\n(?=(?:\s*(?:-|\d+\.) ))", "\n", body)
        # Recipe pages use their headings as section labels; flatten them all to h2.
        body = re.sub(r"^#{2,4} ", "## ", body, flags=re.M)
        # A second numbered list right after the first (another way to cook it)
        # would merge into one in Markdown; a comment keeps them apart.
        body = re.sub(r"(\n\d+\. [^\n]*)\n(?=1\. )", r"\1\n\n<!-- -->\n\n", body)
        recipes.append({
            "id": compact_id(block["id"]),
            "title": title,
            "icon": page_icon(client, block["id"]),
            "slug": f"{cuisine_slug}/{sn.slugify(title)}",
            "subjects": [],
            "date": (block.get("created_time") or "")[:10],
            "group": group,
            "group_weight": group_weight,
            "weight": pos + 1,
            "body": body.strip() + "\n",
            "images": conv.images,
        })
    return recipes


def front_matter(r: dict) -> str:
    lines = ["---",
             f"title: {sn.yaml_str((r['icon'] + ' ' + r['title']).strip())}",
             f"date: {r['date']}",
             f"weight: {r['weight']}"]
    if r.get("group"):
        lines += [f"group: {sn.yaml_str(r['group'])}", f"group_weight: {r['group_weight']}"]
    lines += [f"notion_id: {r['id']}", "---"]
    return "\n".join(lines) + "\n"


def cuisine_index(title: str, icon: str, weight: int, notion_id: str) -> str:
    return (f"---\ntitle: {sn.yaml_str(title)}\nicon: {sn.yaml_str(icon)}\nweight: {weight}\n"
            f"notion_id: {notion_id}\n---\n")


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
    src = cfg["recipes"]
    root = src.get("output_dir", "content/recipes")
    slugs = src.get("cuisine_slugs", {})

    def log(msg: str) -> None:
        if args.verbose:
            print(f"  {msg}", file=sys.stderr)

    client = Notion(token, API_VERSION_NEW, args.verbose)
    print("Fetching recipes…", file=sys.stderr)
    try:
        top = list(client.paginate("GET", f"/blocks/{src['page_id']}/children"))
    except NotionError as e:
        print(f"error: could not read the Recipes page: {e}", file=sys.stderr)
        return 1

    recipes: list[dict] = []
    cuisines: list[tuple[str, str]] = []            # (folder, index content)
    weight = 0
    for block in top:
        if block.get("type") != "child_page":
            continue
        title = block["child_page"]["title"].strip()
        if not title:
            continue
        weight += 1
        slug = slugs.get(title) or sn.slugify(title)
        icon = page_icon(client, block["id"])
        cuisines.append((slug, cuisine_index(title, icon, weight, compact_id(block["id"]))))
        found = walk_cuisine(client, block, slug, lambda: sn.Converter(client))
        log(f"{title}: {len(found)} recipes")
        recipes.extend(found)
    print(f"  {len(cuisines)} cuisines, {len(recipes)} recipes", file=sys.stderr)

    if not args.dry_run:
        for slug, content in cuisines:
            path = os.path.join(root, slug, "_index.md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            current = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            if current != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                log(f"write {path}")
    sn.front_matter = front_matter
    written, removed = sn.write_notes(recipes, root, args.dry_run, log)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} changed recipe(s), removed {removed}; {len(recipes)} in total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
