---
title: "Yarn manual"
date: 2026-11-11
subjects: ["tech"]
notion_id: 415ef088fb8b81429708d84ff2297a8a
---

Everything that shapes the ball of yarn on `/journal/`, and where to change it. Two files hold it all:
- `layouts/journal/list.html`: behaviour, layout and shape (a script with a knob block at the top).
- `assets/css/custom.css`: looks (thickness, colours, shadows), in the block headed *Journal landing page: the ball of yarn*.

After any change: commit, push, wait for the deploy. To try things first, run `hugo server` locally (no password there).

### How it works, in one paragraph

The newest week is the tip of the loose end. Clicking the ball pays out more yarn; the ball turns by exactly the length it gives (angle = length / radius) and shrinks a little. The loose yarn slides along a fixed path, so older weeks come out next to the ball. Each week is one stretch of yarn; hovering it shows its dates, clicking opens the entry. On screens at least 700 px wide the path is the traced sketch; narrower screens use a generated path.

### The knobs (`layouts/journal/list.html`, object `Y` at the top of the script)

#### Pulling

| Knob | Now | What it does |
|---|---|---|
| `FIRST` | 2 | Weeks lying out when the page opens. Also where “aufwickeln” winds back to. |
| `STEP` | 4 | Weeks released per click on the ball. |
| `PULL_MS` | 1100 | Duration of one pull, in milliseconds. |
| `SEG` | 92 | Length of one week of yarn, in px. Longer = fewer weeks fit on the sketch. |
| `SEG_NARROW` | 70 | The same on phones (under 560 px). |

#### Ball

| Knob | Now | What it does |
|---|---|---|
| `BALL_MAX` | 74 | Ball radius with every week still wound up. |
| `BALL_MIN` | 54 | Ball radius with every past week unrolled. It never goes smaller: the rest is yarn for weeks to come. The radius in between follows the wound-off area (r² falls linearly). |
| `LIFT` | 5 | How far above the table the yarn leaves the ball. Smaller = lower. Keep it above about 2, or the yarn’s end can peek out under the ball. |

On phones the ball is drawn at 72 % of these sizes.

#### Generated path (phones only)

These only matter below 700 px wide; on desktop the sketch decides the shape.

| Knob | Now | What it does |
|---|---|---|
| `LANE` | 150 | Vertical distance between two passes across the screen. |
| `BEND_EVERY` | 430 | On average one feature (an S-bend or a curl) per this many px of yarn. Bigger = calmer. |
| `CURL_SHARE` | 0.15 | Fraction of features that are full curls; the rest are S and Z bends. 0 = no curls. |
| `LOOP_R` | [12, 52] | Curl size range, roughly the radius in px. |
| `BEND` | [0.55, 1.25] | How far an S-bend swings off course, in radians. Around 1.2 reads as a lazy Z. |
| `SEED` | 7 | Any other whole number gives a different, but stable, arrangement. Also reshuffles the ball’s windings (all sizes). |

`THICK` is a leftover and does nothing; thickness lives in the CSS (below).

### The desktop shape: the traced sketch

The constant `SKETCH = [...]` holds the traced drawing as x,y pairs about 7 px apart, in the sketch’s own pixel coordinates (1920 × 1372, ball at 299,170). It is scaled to the page width and starts just right of the ball. If the yarn gets longer than the sketch (about 75 weeks at desktop width), a second copy continues further down.

To change the shape, draw a new sketch and send it to Claude to trace; replacing the numbers by hand is not practical. If the new sketch is longer or shorter, the total length used in `sketchPath` (`made += 10925 * sx`) has to match it; Claude updates that together with the points.

The 700 px switch between sketch and generated path is the line `table = W >= 700 ? sketchPath(need) : buildPath(need);`.

### Looks (`assets/css/custom.css`)

#### Thickness of the loose yarn

One number: `--yarn-w` on `.yarn` (now `5px`). The band, the pale core (52 % of it), the shadow and the hover glow all follow. The ball’s windings do not.

#### Loose yarn
- `.yarn-body`: the band. Colour `--color-primary-600`.
- `.yarn-sheen`: the pale core. Colour `--color-primary-200`, `opacity` 0.6.
- `.yarn-shadow`: soft shadow. `transform` moves it, `filter: blur(...)` softens it, the `rgba` alpha darkens it.

#### Ball
- `.yarn-ball-base`: the colour showing between windings (`--color-primary-700`).
- `.yarn-strand-edge`: the darker band of each winding (`stroke-width` 8px).
- `.yarn-strand`: the pale core of each winding (`stroke-width` 3.2px, `opacity` 0.6).
- `.is-under` variants: the lower layer of windings.
- `.yarn-ball-shadow`: shadow on the table.
- How many windings: `var n = layer ? 44 : 30;` in the script (top layer, lower layer).
- Sphere shading: the stops of the gradient `yarn-shade` in the script (`buildBall`): first stop = highlight strength, the last two = darkness at the rim.

#### Hover
- `.yarn-glow`  `opacity` (0.4): how much a hovered stretch lights up.
- `.yarn-hit`  `stroke-width` (24px): how far from the yarn the mouse still counts as “on” it.
- `.yarn-label`: the dates. Size via `font-size`; they are invisible until hover (`opacity: 0`, then 1). To show them always, delete `opacity: 0;` there. Distance of the dates from the yarn: the two `16` values in `nx * 16` / `ny * 16` in the script.

#### Colours in general

All `--color-primary-*` values come from the Journal palette in `data/sections.yaml` (key `journal`). Changing that palette recolours the whole yarn, the calendar and the section at once.

### Texts

In `layouts/journal/list.html`, top of the page:
- “Am Knäuel ziehen: ältere Wochen” and “aufwickeln”: the two buttons under the yarn.
- The date format on each stretch (e.g. `25-31.10.`) is built in the `data-label` part of the list.

Note: the CSS currently contains `.yarn-hint { display: none; }` followed later by `.yarn-hint { ... display: flex; ... }`. The later one wins, so the buttons show. To hide them, delete `display: flex;` from the second rule.

### Good to know
- Visitors with “reduce motion” switched on get no animation; the yarn just appears at its new length.
- Without JavaScript the page shows a plain list of weeks instead.
- The page is password-protected with the rest of Journal; the yarn appears after the password.
- If a change breaks the page, the quickest check is the browser console (F12) on `hugo server`.
