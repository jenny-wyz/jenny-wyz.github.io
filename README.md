# jenny-wyz.github.io

Jenny's life capsule. Built with [Hugo](https://gohugo.io) and the [Blowfish](https://blowfish.page) theme, published with GitHub Pages at https://jenny-wyz.github.io/.

## Writing

Everything is a Markdown file under `content/`:

| Section | Folder | Notes |
|---|---|---|
| Journal | `content/journal/` | name files `YYYY-MM-DD-title.md` to keep them sorted |
| Memoir | `content/memoir/` | chapters carry `series: ["Memoir"]` and a `series_order` |
| Brain dump | `content/braindump/` | |
| Reading | `data/books.json` | synced from Notion, see below; optional write-up pages in `content/reading/` |
| Recipes | `content/recipes/` | |
| Notes | `content/notes/<subject>/` | subjects are subfolders: music, tech, literature, philosophy, history, biology |

Each file starts with front matter between `---` lines:

```yaml
---
title: "Something"
date: 2026-10-31
summary: "One line shown in lists."
tags: ["a", "b"]
draft: true          # remove this line to publish
---
```

`hugo new journal/2026-11-01-a-title.md` creates a file from the template in `archetypes/`.

Pages may contain Chinese, German or any other language; nothing else needs changing.

## Reading section (synced from Notion)

The Reading page is not made of Markdown files. It is an interactive shelf built from `data/books.json`, which `scripts/sync_books.py` generates from the Notion databases **Jernier's List** and **Jernier's Notes**. Keep logging books in Notion; the site follows.

How it runs: `.github/workflows/sync-books.yaml` executes every night (03:17 UTC) and on demand from the Actions tab. It writes `data/books.json`, optionally fetches covers, commits only when something changed, and then triggers the Pages deploy.

One-time setup:

1. Create an integration at https://www.notion.so/profile/integrations (type: internal, read content capability is enough). Copy its token.
2. In Notion, open the **Jernier reads** page, click `...` (top right) > **Connections** > add the integration. This gives it access to both databases on that page.
3. In this repo: **Settings > Secrets and variables > Actions**. Add a secret `NOTION_TOKEN` with the token, and (optional) a variable `COVERS` set to `true` or `false`.
4. Run the workflow once by hand from the **Actions** tab to confirm it works.

Covers: `scripts/fetch_covers.py` looks each book up on Open Library and stores a small JPEG in `assets/covers/<id>.jpg`, with a cache in `data/covers.json` so each book is looked up once. Books without a confident match (most Chinese titles, and collections) get a typographic spine colored by category (`data/reading_palette.yaml`). Two switches: the `COVERS` variable decides whether covers are fetched; `params.reading.covers` in `config/_default/params.toml` decides whether they are shown.

Safety: the sync never empties the site. If Notion is unreachable or returns far fewer books than before, the script exits with an error and the old data stays. Add a checkbox column named **Private** to the Notion list and tick it on any book you want kept off the site.

Writing about a book at length: create a page in `content/reading/` with `book: <id>` in the front matter (the id is the `?book=` value in the URL when the book's panel is open on the shelf). The page gets the book's cover and metadata header, and the shelf links to it.

Local run of the sync (needs the token): `NOTION_TOKEN=... python3 scripts/sync_books.py`. Tests: `python3 -I scripts/test_sync_books.py`.

## Previewing locally

Install Hugo extended (https://gohugo.io/installation/), then:

```sh
git clone --recurse-submodules https://github.com/jenny-wyz/jenny-wyz.github.io.git
cd jenny-wyz.github.io
hugo server -D          # -D also shows drafts
```

Open the address it prints (usually http://localhost:1313/). The page reloads as you save.

## Publishing

Commit and push to `main`. The workflow in `.github/workflows/hugo.yaml` builds the site and deploys it. The first time, enable it in the repository: Settings > Pages > Build and deployment > Source: **GitHub Actions**.

## Changing things

- **Sections and menu**: `config/_default/menus.en.toml`. A new section needs `content/<name>/_index.md` plus a menu entry; a color theme in `data/sections.yaml` is optional.
- **Per-section colors**: `data/sections.yaml`. Any single page can borrow a theme with `colors: <section>` in its front matter.
- **Site-wide colors**: `assets/css/schemes/capsule.css`. To use one of Blowfish's built-in schemes instead, set `colorScheme` in `config/_default/params.toml` (options: blowfish, ocean, forest, autumn, slate, noir, neon, fire, avocado, princess, terminal, marvel, congo, bloody, burufugu, github, one-light).
- **Dark or light by default**: `defaultAppearance` in `config/_default/params.toml`.
- **Name, headline, photo, links**: `config/_default/languages.en.toml`; the photo is `assets/img/author.jpg`.
- **Layouts**: `layouts/` holds the few templates that override the theme (section list with subject cards, home page section grid, per-section color injection). Blowfish's full options: https://blowfish.page/docs/configuration/
- **Theme update**: `git submodule update --remote themes/blowfish`, then check the site still builds.
