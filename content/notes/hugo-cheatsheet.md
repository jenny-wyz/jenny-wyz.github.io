---
title: "Hugo cheat sheet for this site"
date: 2026-10-31
subjects: ["tech"]
---

## Everyday

- New journal entry: create `content/journal/YYYY-MM-DD-title.md` with a title and date in the front matter.
- New note: add a page to the Notion database "Jernier's Notes on Stuff", pick one or more Tags (the subjects) and tick Publish; the nightly sync writes it to `content/notes/`. A hand-written note still works too: a file in `content/notes/` with `subjects: ["<subject>"]`.
- Preview locally: `hugo server -D` and open the printed address. `-D` includes drafts.
- Publish: commit and push to `main`. GitHub Actions builds and deploys the site.

## Occasionally

- New top-level section: `content/<name>/_index.md`, a menu entry in `config/_default/menus.en.toml`, and optionally a color theme in `data/sections.yaml`.
- Update the theme: `git submodule update --remote themes/blowfish`, then rebuild and check.
- Change the site-wide colors: edit `assets/css/schemes/capsule.css`.

## Front matter fields used here

`title`, `date`, `summary`, `tags`, `categories`, `subjects` (notes), `series` and `series_order` (essays), `draft: true` (hide a page), `colors: <section>` (borrow another section's color theme for one page).
