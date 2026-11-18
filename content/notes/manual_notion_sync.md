---
title: "Syncing from Notion"
date: 2026-11-07
subjects: ["tech"]
---

### Init sync

On Notion page, ••• → More → Connections → type `website sync`. Then run it once manually.

### Manually

In Github repo, Actions  → Sync ... from Notion → Run workflow  → Run workflow. Wait until it finishes. Refresh website to check.

### Automatically

Edit the time and frequency of Notion syncing in `.github\workflows\sync-[smth].yaml`