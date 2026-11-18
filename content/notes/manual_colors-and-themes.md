---
title: "Colors and themes on this site"
date: 2026-11-03
summary: "Where every color lives, and how to change it."
subjects: ["tech"]
---

Each layer is more specific than the one before it: the site scheme sets the defaults, a section block overrides them for that section, and a page can borrow another section’s block.

## Quick reference

| I want to change... | File | What to edit |
|---|---|---|
| One section’s colors | `data/sections.yaml` | that section’s block |
| One page’s colors | the page’s `.md` file | `colors: <section>` in front matter |
| The site-wide default colors | `assets/css/schemes/capsule.css` | the `--color-*` variables |
| The whole scheme | `config/_default/params.toml` | `colorScheme` |
| Dark or light by default | `config/_default/params.toml` | `defaultAppearance`, `autoSwitchAppearance` |
| Book spine colors | `data/reading_palette.yaml` | hue per category |
| The “Reading” status green | `assets/css/reading.css` | `--rd-reading` |
| Notes bubble colors | `assets/css/custom.css` | the bubble palette |

## Section colors

File: `data/sections.yaml`. This is the one I’ll use most. Every section (journal, essays, braindump, reading, recipes, notes) has a block like this:

```yaml
journal:
  tagline: "week by week"      # shown on the home card
  icon: "pen-nib"              # Font Awesome name, shown on the home card
  primary:                     # accent ramp, 50 = lightest, 900 = darkest
    50: "250, 245, 255"
    # ... 100 to 800 ...
    900: "88, 28, 135"
  dark_bg: "30, 20, 44"        # page background, dark mode
  dark_deep: "20, 12, 32"      # panels and code blocks, dark mode
  dark_edge: "58, 44, 82"      # borders and card outlines, dark mode
  light_bg: "252, 249, 255"    # page background, light mode
```

- Values are RGB written as `"r, g, b"`, not hex.
- `primary` colors links, buttons, tags and highlights. In dark mode the 300 to 400 shades are what shows most; in light mode, 600 to 700.
- Every field is optional. Leave one out and the site default from `capsule.css` is used.
- A section with no block at all just uses the site default.
- To swap two sections’ looks, swap everything from `primary:` down. Keep the tagline and icon.
- For a new ramp, copy a Tailwind palette (tailwindcss.com/docs/colors) and convert each hex to RGB.
- Keep `dark_bg`, `dark_deep` and `dark_edge` in the same hue, from mid-dark (edge) to darkest (deep), so text stays readable.

## One page

Any page can wear another section’s colors:

```yaml
---
title: "Something"
colors: essays
---
```

Subject pages under /notes/ always use the Notes block.

## Site-wide default

File: `assets/css/schemes/capsule.css`. The base palette for the home page and anything without its own block:

- `--color-neutral-*`: the navy grays. 800 is the dark-mode page background, 900 the deeper panels, 700 the borders.
- `--color-primary-*`: sky blue, the default accent.
- `--color-secondary-*`: warm sand, used for contrast (for example, the rating stars on the Reading shelf).

Same `r, g, b` format as the YAML.

## Scheme and appearance

File: `config/_default/params.toml`.

- `colorScheme = "capsule"`: this site’s own scheme. Blowfish built-ins: blowfish, ocean, forest, autumn, slate, noir, neon, fire, avocado, princess, terminal, marvel, congo, bloody, burufugu, github, one-light. Section blocks still apply on top of any of them.
- `defaultAppearance = "dark"`: `dark` or `light`.
- `autoSwitchAppearance = false`: `true` follows the visitor’s system setting instead.

## Smaller color spots

- **Book spines** (`data/reading_palette.yaml`): a hue from 0 to 360 per category, for books without a cover. 0 is red, 120 green, 240 blue. The book’s first listed category decides.
- **Reading status** (`assets/css/reading.css`): `--rd-reading` is the green of “Reading”, set separately for light and dark. It ignores the section accent on purpose.
- **Notes bubbles** (`assets/css/custom.css`): the pastel palette under the “Subject bubbles” comment.

## How it’s wired

`layouts/partials/extend-head-uncached.html` reads `sections.yaml` and injects that section’s colors as CSS variables into each page. No need to touch it when changing colors.

## Checking a change

1. `hugo server -D`, then open http://localhost:1313/. The page reloads on save.
2. Flip dark and light with the switch in the footer to check both.
3. Commit and push to `main` to publish.
