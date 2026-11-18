---
title: "Tuning text, fonts and the Brain dump"
date: 2026-11-18
summary: "Which fonts the site uses and how to swap them, where text size and spacing live, and every Brain dump knob."
subjects: ["tech"]
---

Almost everything here is in one file: `assets/css/custom.css`. Search (Ctrl+F) for the quoted section names to jump to the right place. Preview with `hugo server -D` before pushing.

## Fonts at a glance

| Where | Font | Comes from |
|---|---|---|
| Whole site (menus, titles, notes, recipes, reading, …) | **Satoshi** | Fontshare (linked) |
| Essays pages | **Newsreader** | self-hosted, `static/fonts/newsreader/` |
| Brain dump pages | **Erode** | Fontshare (linked) |
| Journal entry text | a system book serif: Palatino Linotype (Windows), Iowan Old Style (Mac, iPhone) | the device |
| Book spines on the Reading shelf | Georgia; Songti for Chinese titles | the device |
| Chinese text, everywhere | Microsoft YaHei (Windows), PingFang (Apple): none of the fonts above has Chinese | the device |
| Country flags | Twemoji Country Flags | self-hosted, `static/fonts/` |

Three places decide this:

1. **`assets/css/custom.css`, section “Fonts”** (at the top): the three font lists `--font-sans` (site), `--font-essays` and `--font-braindump`, and the `@font-face` blocks of the self-hosted Newsreader.
2. **`layouts/partials/extend-head-uncached.html`**, at the top: the Fontshare link (which fonts and weights are loaded) and a small map saying which section uses which list:
   `dict "essays" "--font-essays" "braindump" "--font-braindump"`.
3. **The Journal**: its own rule in `custom.css`, section “Journal entries”, `.journal-entry > p, .journal-entry > blockquote`.

A font list names several fonts: the browser uses the first one it can, so the later ones are fallbacks in case a font fails to load. Keep `"Twemoji Country Flags"` first (it only draws flags) and end with `serif` or `sans-serif`.

## Swap a font

**Another Fontshare font** (fontshare.com, free):

1. In the Fontshare link in `extend-head-uncached.html`, add or replace it as `f[]=<name>@<weights>`. Weights: `400` regular, `500` medium, `600` semibold, `700` bold; add 1 for italic (`401` = italic, `701` = bold italic). The name is the one in the font’s Fontshare address, e.g. `general-sans`.
2. In the font list in `custom.css`, write its name as shown on Fontshare, e.g. `"General Sans"`.

**A Google font**, self-hosted like Newsreader:

1. Get the `.woff2` files (e.g. from fontsource.org, “Download”) and put them in `static/fonts/<name>/`.
2. Copy one of the Newsreader `@font-face` blocks per file and change the name and path.
3. Use the name in a font list.

**A font already on most devices** needs no files: `Georgia`, `"Palatino Linotype"`, `"Segoe UI"`, `Arial`.

## Give another section its own font

1. Add a list in `:root` in the “Fonts” section of `custom.css`, e.g. `--font-notes: "Twemoji Country Flags", "Erode", Georgia, serif;`
2. Add the section to the map in `extend-head-uncached.html`: `dict "essays" "--font-essays" "braindump" "--font-braindump" "notes" "--font-notes"`.

The section names are the folder names under `content/`: `journal`, `reading`, `notes`, `essays`, `braindump`, `recipes`. The section font covers everything below the menu; menu and footer stay in the site font.

## Change the font in one smaller place

Add a `font-family` to that area’s rule at the end of `custom.css` (later rules win):

| Area | Rule |
|---|---|
| Only the text of an open Brain dump entry | `.dump-body .prose { font-family: …; }` |
| Only the one-line glimpses | `.dump-peek { font-family: …; }` |
| Journal entry text | `.journal-entry > p, .journal-entry > blockquote` (and `.journal-entry .callout-body > p`) |
| All headings of the site | `h1, h2, h3 { font-family: …; }` |

You can reuse a list: `font-family: var(--font-essays);`.

## Text size and spacing, site-wide

Article text (notes, essays, recipes) uses the theme’s defaults: size `1rem`, line height `1.75`, `1.25em` between paragraphs. To change them, add to the end of `custom.css`:

```css
.article-content { font-size: 1.05rem; line-height: 1.7; }
.article-content p { margin-top: 1em; margin-bottom: 1em; }
```

To scale everything on the site at once (text, spacing, menus), change the base size:

```css
html { font-size: 17px; }   /* browsers default to 16px */
```

Journal text has its own size and line height in its rule: `font-size: 1.12rem; line-height: 1.75;`.

## Brain dump: the knobs

Section “Knobs: tune the Brain dump page here”. Values as of this note.

| Knob | Value | What it does |
|---|---|---|
| `--dump-size` | `1.09rem` | text size of the whole stream; month, day number, weekday and time scale with it |
| `--dump-time-w` | `3.7rem` | width of the time column = space between a time and the start of its entry |
| `--dump-entry-gap` | `0.88rem` | space above and below each entry line (two neighbors sit 2× this apart); also the space above and below an open entry’s text |
| `--dump-day-pad` | `0.5rem` | extra space on each side of the line between days; at `0` days are spaced like entries |
| `--dump-day-line` | `0.3` | strength of the line between days (0 invisible, 1 solid) |
| `--dump-entry-line` | `0.2` | strength of the thin line between entries of one day (0 = none) |
| `--dump-fade-from` | `7%` | where along the line the glimpse starts to fade |
| `--dump-fade-mid` | `0.44` | how visible the glimpse is halfway along |
| `--dump-fade-end` | `0.05` | … and at the right end |
| `--dump-hover-mid` | `0.7` | the same two while the mouse is on the line (higher = darker) |
| `--dump-hover-end` | `0.25` | |
| `--dump-others` | `0.45` | while one entry is open, how visible the other lines stay (1 = no dimming) |

On phones the time column is narrower: `.dump { --dump-time-w: 2.9rem; }` inside `@media (max-width: 640px)` at the end of the Brain dump section.

## Brain dump: text inside an open entry

Section “Text inside an open entry. Knobs:”.

| In Notion | Knob | Value |
|---|---|---|
| Line break without Enter (Shift+Enter) | `--dump-text-lh` (line height) | `1.62` |
| One Enter (new paragraph) | `--dump-para` | `0.7em` |
| Two Enters (an empty line) | `--dump-para-blank` | `1.45em` |

The empty line reaches the site as an invisible marker written by `scripts/sync_braindump.py`, so it only shows after the next sync. Three or more Enters look like two.

## Brain dump: names in Notion

| Name | Result |
|---|---|
| `20261116` | dated, no time |
| `20261116-1` | no time; the number orders entries within the day |
| `20261116 01:20` or `20261116-0120` | shows 01:20 |
| any name ending with an apostrophe, `20261116-0659’` | hidden from the site |

## Dark mode text

Section “Dark mode text: softer, grayer, less contrast”. The five `--color-neutral…` lines under `html.dark` set how bright text is in dark mode, from titles (first line) to body text (last line). Lower numbers are dimmer. Dates, the table of contents and bold text have their own lines right below. Colors of sections are covered in the note “Colors and themes on this site”.

## Units

| Unit | Means | Use for |
|---|---|---|
| `rem` | relative to the site’s base size (16px) | sizes that should not depend on their surroundings |
| `em` | relative to the text size of that element | spacing that should grow with the text |
| a plain number, as in `line-height: 1.62` | a multiple of the text size | line height |
| `%`, or `0` to `1` | a share or a strength | fades, line strengths |

## If a change does not show

1. Save the file and check the terminal running `hugo server -D` for an error.
2. Reload with Ctrl+F5.
3. Make sure the rule is not overridden further down in `custom.css`: the later rule wins.

## Jernier's picks

- Satoshi  *(https://fontshare.com)*
- Erode
- Gambetta
- Neco
- Recia
- Outfit
- Karma
- Crimson Pro
- Alpino
- Clash Display
- Newsreader
- Source Serif 4
