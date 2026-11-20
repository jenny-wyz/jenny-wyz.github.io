#!/usr/bin/env python3
"""
Sync the Brain dump section from Notion.

Source: the page "Absolute dump". It has headed sections (Recycling, Waste);
every subpage under a heading becomes one entry, and the heading becomes the
entry's `group`, in the order the headings appear. Subpages above the first
heading have no group. Loose text on the page is ignored.

Entries may sit inside toggles, toggle headings or columns (for instance one
toggle per year): the sync looks inside every block that can hold others. A
heading that is just a year ("2026") only organizes the Notion page; it is
never a group, and neither is a level-4 heading.

Entries are named by date in Notion, optionally with a time or a counter:

    20261116            one entry that day
    20261116-1          a counter, when the day has several (-0, -1, ...)
    20261116 01:20      the time it was thought (also 20261116-0120)

Inside an entry, an empty line (Enter pressed twice in Notion) is kept as a
`<div class="gap">` marker, so the site can show it as a slightly larger gap
than a plain new paragraph (styles: `.dump-body .prose` in custom.css).

An entry is published unless its name ends with an apostrophe:

    20261116-0659'      hidden: not written to the site, and removed from it
                        if it was there (\u2019, \u2018, ' and ` all count)

Notion's own "created" time cannot be edited and is often later than the
thought, so date and time come from the title. The site never shows the raw
title: the entry's `title` becomes the written-out date ("Monday, 16 November
2026 · 01:20"), `date` the day and `time` the time, if given. A title that
is not a date is kept as it is and dated by the page's creation date.

`weight` is the display order of layouts/braindump/list.html: oldest day
first, newest last; within a day, entries without a time (by counter, then
by their order in Notion), then the timed ones from early to late.

Safety: if a run would publish fewer than half the entries the site has now
(a reorganized Notion page the sync cannot read, say), it stops and changes
nothing. `--force` overrides that when the drop is intended.

Each entry becomes content/braindump/<slug>.md. Reuses the block converter
and file writer from sync_notes.py: only files with a `notion_id` are
managed, hand-written files are left alone, no-change runs make no git diff.

Usage:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_braindump.py [--dry-run] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_notes as sn  # noqa: E402
from sync_books import API_VERSION_NEW, Notion, NotionError, compact_id  # noqa: E402

HEADINGS = ("heading_1", "heading_2", "heading_3")


def plain(rich) -> str:
    return "".join(p.get("plain_text", "") for p in (rich or [])).strip()


# A line break typed at the very end of a paragraph would show as a stray "\".
TRAILING_BREAK = re.compile(r"\\(?=\n\n|\n?\Z)")
TITLE_RE = re.compile(r"^(\d{4})[-./]?(\d{2})[-./]?(\d{2})(?:[\s_-]+(.*))?$")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


HIDE_MARKS = "'\u2019\u2018\u02bc`\u00b4\u2032"


def is_hidden(title: str) -> bool:
    """A name ending with an apostrophe keeps the entry off the site."""
    return title.strip()[-1:] in HIDE_MARKS if title.strip() else False


def parse_title(title: str) -> Optional[dict]:
    """'20261116', '20261116-1', '20261116 01:20', '20261116-0120' ->
    {"date": "2026-11-16", "time": "01:20" or "", "seq": 1 or None, "title": written-out date}.
    None when the title is not a date."""
    m = TITLE_RE.match(title.strip())
    if not m:
        return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    rest, time, seq = (m.group(4) or "").strip(), "", None
    t = re.fullmatch(r"(\d{1,2})[:.h](\d{2})|(\d{2})(\d{2})", rest)
    if t:
        hh, mm = int(t.group(1) or t.group(3)), int(t.group(2) or t.group(4))
        if hh < 24 and mm < 60:
            time = f"{hh:02d}:{mm:02d}"
    elif re.fullmatch(r"\d{1,3}", rest):
        seq = int(rest)
    nice = f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]} {d.year}"
    return {"date": d.isoformat(), "time": time, "seq": seq, "title": nice + (f" \u00b7 {time}" if time else "")}


def display_order(entries: list[dict]) -> None:
    """Set each entry's weight: oldest day first; inside a day the untimed
    entries (by counter, then Notion order), then the timed ones, early to late."""
    def key(e: dict):
        y, m, d = (int(x) for x in (e["date"] or "1970-01-01").split("-"))
        seq = e.get("seq")
        return (date(y, m, d).toordinal(), e.get("time") or "", 999 if seq is None else seq, e["pos"])
    for w, e in enumerate(sorted(entries, key=key), start=1):
        e["weight"] = w


def front_matter(e: dict) -> str:
    lines = ["---", f"title: {sn.yaml_str(e['title'])}", f"date: {e['date']}"]
    if e.get("time"):
        lines.append(f"time: {sn.yaml_str(e['time'])}")
    lines.append(f"weight: {e['weight']}")
    if e.get("group"):
        lines += [f"group: {sn.yaml_str(e['group'])}", f"group_weight: {e['group_weight']}"]
    lines += [f"notion_id: {e['id']}", "---"]
    return "\n".join(lines) + "\n"


YEAR = re.compile(r"(?:19|20)\d{2}")


def collect(blocks: list[dict], children=None) -> list[tuple[dict, str, int]]:
    """Every child_page block with its group: (block, group, group order).

    `children(block_id)` returns the blocks inside a block; with it, pages
    inside toggles, toggle headings and columns are found too, in page order.
    A level 1-3 heading sets the group, unless its text is just a year."""
    out: list[tuple[dict, str, int]] = []
    state = {"group": "", "order": 0}

    def walk(bs: list[dict], depth: int) -> None:
        for b in bs:
            t = b.get("type") or ""
            if t == "child_page":
                out.append((b, state["group"], state["order"]))
                continue
            if t in HEADINGS:
                text = plain(b[t].get("rich_text"))
                if text and not YEAR.fullmatch(text):
                    state["group"] = text
                    state["order"] += 1
            if children and b.get("has_children") and t != "child_database" and depth < 6:
                walk(children(b["id"]), depth + 1)

    walk(blocks, 0)
    return out


def too_few(new_count: int, old_count: int) -> bool:
    """True when a run would shrink a well-filled section to under half."""
    return old_count >= 10 and new_count * 2 < old_count


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="scripts/sync_config.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--force", action="store_true", help="write even if most entries would disappear")
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
    hidden = 0
    def inside(block_id: str) -> list[dict]:
        return list(client.paginate("GET", f"/blocks/{block_id}/children"))

    try:
        found = collect(top, inside)
    except NotionError as e:
        print(f"error: could not read inside the page: {e}", file=sys.stderr)
        return 1
    for pos, (block, group, order) in enumerate(found):
        title = block["child_page"]["title"].strip() or "Untitled"
        if is_hidden(title):   # never fetched, never written
            hidden += 1
            continue
        conv = sn.Converter(client)
        conv.keep_blank = True   # two Enters in Notion = a slightly larger gap on the site
        parts = conv.convert(conv.children(block["id"]))
        while parts and parts[0] == sn.BLANK:
            parts.pop(0)
        while parts and parts[-1] == sn.BLANK:
            parts.pop()
        body = "\n\n".join(parts)
        body = re.sub(r"\n\n(?=(?:\s*(?:-|\d+\.) ))", "\n", body)
        body = TRAILING_BREAK.sub("", body)
        slug = sn.slugify(title)
        # dump titles repeat easily ("0", "1", "idea"): keep every slug unique
        taken[slug] = taken.get(slug, 0) + 1
        if taken[slug] > 1:
            slug = f"{slug}-{compact_id(block['id'])[:6]}"
        named = parse_title(title) or {}
        entries.append({
            "id": compact_id(block["id"]),
            "title": named.get("title", title),
            "slug": slug,
            "subjects": [],
            "date": named.get("date") or (block.get("created_time") or "")[:10],
            "time": named.get("time", ""),
            "seq": named.get("seq"),
            "pos": pos,
            "group": group,
            "group_weight": order,
            "weight": pos + 1,
            "body": body.strip() + "\n",
            "images": conv.images,
        })
    print(f"  {len(entries)} entr(y/ies), {hidden} hidden", file=sys.stderr)
    display_order(entries)

    on_site = len(sn.managed_files(root))
    if too_few(len(entries), on_site) and not args.force:
        print(f"error: only {len(entries)} entr(y/ies) found, but the site has {on_site}. "
              "Nothing was changed. If the Notion page was reorganized in a way the sync "
              "cannot read, fix that; if the drop is intended, run with --force.", file=sys.stderr)
        return 1

    sn.front_matter = front_matter
    written, removed = sn.write_notes(entries, root, args.dry_run, log)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} changed entr(y/ies), removed {removed}; {len(entries)} in total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
