# jenny-wyz.github.io

Jenny's life capsule. Built with [Hugo](https://gohugo.io) and the [Blowfish](https://blowfish.page) theme, published with GitHub Pages at https://jenny-wyz.github.io/.

## Writing

Everything is a Markdown file under `content/`:

| Section | Folder | Notes |
|---|---|---|
| Journal | `content/journal/` | name files `YYYY-MM-DD-title.md` to keep them sorted |
| Memoir | `content/memoir/` | chapters carry `series: ["Memoir"]` and a `series_order` |
| Brain dump | `content/braindump/` | |
| Reading list | `content/reading/` | one page per book; author, year, status in front matter |
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
