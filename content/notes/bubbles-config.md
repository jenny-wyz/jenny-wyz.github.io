---
title: "Where to tune bubble movements"
date: 2026-11-02
subjects: ["tech"]
---

File `layouts/partials/bubbles.html`, right at the top of the `<script>` block, there’s a box labeled **TUNING KNOBS** with an object called `T`. Every number has a comment. The ones you’ll most likely touch:

- `SPEED` (95): how strongly each bubble’s current pushes it. Raise for faster, lower for lazier.
- `MAX_SPEED` (110): the ceiling in px/s. Nothing exceeds this no matter what.
- `DRAG` (0.975): how much velocity survives each frame. Closer to 1 means longer glides; 0.9 feels like moving through honey.
- `TURN` (0.35) and `TURN_SPREAD` (0.3): how fast the currents change heading. Higher = twistier, more erratic paths; lower = long sweeping arcs.
- `AGILITY` (150): how much more small bubbles move than big ones.
- `CENTER_PULL` (0.08): the pull toward the middle. Set 0 to let them wander to the edges freely.
- `MOUSE_PUSH` (420) and `MOUSE_REACH` (110): cursor repulsion; 0 disables it.
- `CLICK_SHOVE` (120): the scatter on a click; 0 disables it.
- `WALL_BOUNCE` (0.8): speed kept when hitting an edge.
- `FIELD_VH` (0.7) and `FIELD_AREA` (4): how tall the field is.
- `SIZE_MIN` (84) and `SIZE_MAX` (200): bubble diameters in px.