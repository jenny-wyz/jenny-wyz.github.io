---
title: "Journal workflow"
date: 2026-11-06
subjects: ["tech"]
notion_id: 410ef088fb8b815781fdf3cd65449707
---

How a week gets from the paper notebook to the website. Everything lives in Notion; the site follows.

### 1. Write, then photograph
1. Write the week in the notebook as usual: entry text on top, a line, vocabulary below.
2. Photograph the pages. One photo per page, straight on, good light.

### 2. Get it transcribed
1. Send the photos to Claude in a chat with the project open, and say which week they belong to if the page has no date.
2. Claude creates one page per week in the Notion database **Jernier’s Tagebuch**, using the corrected version of each sentence (the green/blue ink wins), with Publish ticked.
3. Skim the page in Notion. Fix anything misread. Done.

No photos go on the site. If a page was transcribed wrongly, edit the Notion page; never the repo.

### 3. The sync
- Every night at 03:47 UTC the workflow **Sync journal from Notion** writes every entry with Publish ticked into `content/journal/` and triggers a deploy.
- To see it sooner: GitHub → Actions → Sync journal from Notion → Run workflow. The log ends with “N published in total”.
- The site is live about two minutes after that.

### Page format (what Claude follows, and what to keep if you type an entry yourself)
- **Name**: the week in words, e.g. `20. bis 26. September 2026`; across a month boundary `27. September bis 3. Oktober 2026`.
- **Week**: the date range, start to end. The start date becomes the entry’s URL (`/journal/2026-09-20/`).
- **Publish**: ticked = on the site; unticked = stays in Notion only (and is removed from the site on the next sync).
- Body, in this order:
  1. The entry text as plain paragraphs. Quotes from books or songs as quote blocks.
  2. Optional themed sections for notes that are not diary text, as a heading 2 with a short title (e.g. `Sein und Zeit`). Use a bulleted list for branching notes and a two-column table for definitions; both are styled to match the glossary.
  3. `Wörter der Woche` as a heading 2, followed by one two-column table: Deutsch | Englisch. Nouns with article (`die Spur`), verbs with their case (`warten auf + Akkusativ`), an example sentence in brackets when the notebook has one.

Headings are rendered as small spaced labels and tables as a quiet glossary, so keep to those two block types for anything after the entry text.

### Privacy

The Journal section is password-protected. The deploy encrypts every entry; the password is the `PAGE_PASSWORD` repository secret. Three wrong tries lock a visitor out for 24 hours and send them to `/shabi/`. Nothing from the section reaches search, feeds or link previews.

### If something goes wrong
- Sync fails with HTTP 404: the integration `website sync` lost access to the database. Database page → ••• → Connections → add it again.
- An entry shows on the site but not the latest edit: the nightly run has not happened yet; run the workflow by hand.
- An entry should disappear: untick Publish in Notion and run the sync.
