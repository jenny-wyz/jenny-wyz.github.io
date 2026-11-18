---
title: "gitty hubby"
date: 2026-11-08
subjects: ["tech"]
---

## Pull Push

The bots commit every night, so always start with `git pull` before applying a patch. You can also tell Git to put your commits on top of the bots’ commits instead of creating a merge:

```git config pull.rebase true```

Run that once and every future git pull in this repo will behave that way.


## Sync

Edit the time and frequency of Notion syncing in `.github\workflows\sync-[smth].yaml`