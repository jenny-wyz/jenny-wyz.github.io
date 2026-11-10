# CLAUDE.md

Context for Claude when working on this repository. Read this and `README.md` before making changes.

## What this is

Jenny's personal "life capsule" website, published at https://jenny-wyz.github.io/ from this repo (`jenny-wyz/jenny-wyz.github.io`). Built with Hugo (extended) and the Blowfish theme (git submodule in `themes/blowfish`, v3.8.0). Deployed by GitHub Actions (`.github/workflows/hugo.yaml`) on every push to `main`.

Sections: Journal (weekly entries in German, synced from the Notion database "Jernier's Tagebuch" by `scripts/sync_journal.py`, one page per week with the text, a "Wörter der Woche" table and "Originalseiten" photos; password-protected like Brain dump; the entry layout is `layouts/journal/single.html` + the journal block in `assets/css/custom.css`), Essays (synced nightly from the Notion page "Jernier 随笔" by `scripts/sync_essays.py`: only the subpages under the heading "Ver 1" are published, the "Ver 0" drafts are never read; password-protected like Journal; formerly "Memoir", old /memoir/ URL redirects), Brain dump, Reading (data-driven, synced from Notion), Recipes (synced nightly from the Notion page "Recipes" by `scripts/sync_recipes.py`: cuisine subpages become `content/recipes/<cuisine>/` folders with an `_index.md` carrying the emoji icon and position, recipe pages become files with `group` = the heading above them on the cuisine page; `layouts/recipes/list.html` renders cuisine tiles and grouped recipe tiles, `layouts/recipes/single.html` lifts the Ingredients section into a side panel next to numbered steps; cuisine slugs are mapped in `scripts/sync_config.json`), Notes (one flat folder, `content/notes/`; subjects are the `subjects` taxonomy with term pages served at /notes/<subject>/ (title in `content/subjects/<subject>/_index.md`); a note can have several subjects; synced nightly from the Notion database "Jernier's Notes on Stuff" by `scripts/sync_notes.py`, whose "Tags" property holds the subjects; only pages with Publish ticked are written; files with a `notion_id` belong to the sync, files without are hand-written and left alone). More top-level sections may come later.

## Owner and preferences

- Jenny works on Windows (PowerShell). Give Windows commands when she has to run something herself.
- Design must be: clean, modern, professional, logical, user-friendly, chic. Prefer restraint over decoration.
- Default appearance is dark mode; the base palette is deep navy (`assets/css/schemes/capsule.css`). Each section has its own accent and tinted background, defined in `data/sections.yaml` and applied by `layouts/partials/extend-head-uncached.html`.
- Base language is English (American English). Entries may contain Chinese or German; keep CJK rendering correct.
- In prose written for the site or for Jenny, avoid long dashes (em dashes).
- She wants everything configurable later (names, colors, sections, switches), so keep settings in config or data files rather than hard-coding them in templates.
- Show visual changes with screenshots before calling them done. Verify every change with a clean `hugo --gc --minify` build.

## Layout of the code

- `config/_default/`: `hugo.toml`, `params.toml` (theme options, `[reading]` switches), `languages.en.toml` (name, headline, photo, links), `menus.en.toml` (header menu = section order), `markup.toml`.
- `content/`: Markdown for every section except the Reading shelf. `_index.md` per section.
- `data/sections.yaml`: per-section colors, icons, taglines for home cards.
- `layouts/`: site overrides of Blowfish.
  - `_default/list.html`: section list; shows cards for subsections, or for the terms of a taxonomy when the section sets `cards: "<taxonomy>"` (Notes uses the `subjects` taxonomy).
  - `partials/breadcrumbs.html`: subject pages show "Notes /" as their crumb.
  - `notes/single.html`: copy of the theme's single.html plus `partials/subject-rail.html`, the hover drawer on the right edge of a note listing the other notes in its subject(s). Notes also cascade `showPagination: false` and `showRelatedContent: false` from `content/notes/_index.md`.
  - `subjects/term.html`: copy of the theme's term.html plus `partials/subjects-rail.html`, the same kind of drawer on a subject page listing all subjects with counts and their bubble colors.
  - `notes/all-notes.html` + `content/notes/all.md`: the "All notes" page (/notes/all/), linked from a pill under the bubbles (`allLink` in content/notes/_index.md). Not named all.html on purpose: in Hugo that name is a catch-all layout for the whole section.
  - `partials/bubbles.html`: the floating subject bubbles on /notes/ (size by note count, pastel palette in `assets/css/custom.css`, tiny packing script, no-JS fallback).
  - `journal/list.html`: the Journal landing page as a ball of yarn (SVG built by an inline script from the plain week list, which stays as the no-JS fallback). Newest week = the loose end; clicking the ball unrolls older weeks (ball turns by length/radius and shrinks; the yarn slides along a generated meander); each week is a clickable stretch between knots. Knobs: the `Y` object at the top of the script. Styles: `.yarn-*` in custom.css.
- `journal/single.html`: copy of the theme's single.html with the content wrapped in `.journal-entry`, a tiny script that groups the photos into a grid, earlier/later chevrons on the page edges, and `partials/journal-calendar.html` (a month calendar in the right column on desktop; weeks with an entry are links, the current week is outlined).
- `shortcodes/sections.html`: home page section cards.
  - `reading/list.html`, `reading/single.html`, `partials/reading/*`: the Reading app.
- `assets/css/reading.css`, `assets/js/reading.js`: Reading section styles and client-side app (no dependencies).
- `archetypes/`: templates for `hugo new` (default, notes, reading).

## Reading section (most complex part)

- Data: `data/books.json`, generated by `scripts/sync_books.py` from two Notion databases on the page "Jernier reads": "Jernier's List" (books) and "Jernier's Notes" (notes related to books). IDs and Notion property names are in `scripts/sync_config.json`.
- Nightly sync: `.github/workflows/sync-books.yaml` (03:17 UTC and manual). Runs the tests, syncs, optionally fetches covers, commits only on change, then triggers `hugo.yaml`.
- Safety rules in the sync (keep them): retries with backoff, full pagination, data-source API with fallback to the 2022-06-28 database API, deterministic output, skip rows with a ticked "Private" checkbox if that column exists, refuse to write if the result is empty or less than half of the previous count.
- Covers: `scripts/fetch_covers.py` (Open Library, conservative matching, cache in `data/covers.json`, images in `assets/covers/<id>.jpg`). Two switches: repo variable `COVERS` controls fetching; `params.reading.covers` controls display. Without a cover, a typographic "spine" is rendered, colored by category via `data/reading_palette.yaml`.
- Views: Shelf, List, Timeline, Stats; chip filters; search; sort; URL state (`?view=`, `?cat=`, `?book=` ...); detail panel. Jenny explicitly does not want a "longest streak" statistic.
- Long write-ups about a book: a page in `content/reading/` with `book: <id>` in front matter.
- Tests: `python3 -I scripts/test_sync_books.py` and `python3 -I scripts/test_fetch_covers.py`.

## Password-protected pages

`protected: true` in a page's front matter (or a section's `_index.md` with a `cascade`, see `content/braindump/_index.md` for the full set of lines) makes the deploy step `scripts/protect_pages.py` encrypt that page's `<main>` content (AES-256-GCM, key from the `PAGE_PASSWORD` repository secret via PBKDF2) and replace it with a "Knock knock" prompt; the browser decrypts in place. Three wrong tries lock protected pages for 24h in that browser and redirect to `/shabi/` (`content/shabi.md`, the decoy). Protected pages are also kept out of search, RSS, sitemap and related blocks by the front matter lines. Local `hugo server` shows the content unencrypted; only the deploy locks it. Tests: `python3 -I scripts/test_protect_pages.py`.

## Current status and open items

- Site is live with sample entries in each section (placeholders Jenny will replace).
- The reading sync from Notion runs in production (114 books as of Nov 2026, covers fetched).
- Notes: 11 notes were imported from Apple Notes in Nov 2026 and copied into the Notion database "Jernier's Notes on Stuff" (database id in `scripts/sync_config.json`, key `site_notes`). The files under `content/notes/` carry the matching `notion_id`, so the first run of "Sync notes from Notion" should produce no or only cosmetic diffs. Before that first run: give the Notion integration access to that database (database page > ... > Connections). The "Substances" note is a draft in the repo and unpublished in Notion; the sync will remove the repo file, which is intended.
- Covers have never been fetched (the build environment could not reach Open Library). Expect most English titles to match and most Chinese titles to keep spines.
- Hugo is pinned to 0.167.0 in `hugo.yaml` because Blowfish 3.8.0 declares compatibility up to that version. Re-test before upgrading either.
- GitHub pauses scheduled workflows after 60 days without repo activity.

## Working rules

- Never commit secrets. The Notion token lives only in GitHub secrets.
- Keep `public/` and `resources/` out of git (see `.gitignore`).
- Keep changes small and explain them; ask before large redesigns or deleting content.
- Do not add Co-Authored-By or Claude-Session trailers to commit messages.
