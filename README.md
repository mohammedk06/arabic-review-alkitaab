# Arabic — Al-Kitaab Part One, Lessons 1–13

A static study site built from my Obsidian review notes: all 13 lesson write-ups — the complete book —
a cross-lesson grammar overview, a searchable vocab bank, and a 352-card flashcard deck.

## Publish it (GitHub Pages)

```bash
git init && git add -A && git commit -m "Arabic review site"
gh repo create arabic-review --public --source=. --push
```

Then: **repo → Settings → Pages → Source: `main` branch, `/docs` folder → Save.**
Live at `https://<your-username>.github.io/arabic-review/` in about a minute.
Share that link with the class.

## Preview locally

```bash
cd docs && python3 -m http.server 8000
```

Open <http://localhost:8000>. (Use the server — the flashcards `fetch()` a JSON
deck, which browsers block on bare `file://` URLs.)

## Rebuild after editing the notes

The Obsidian vault stays the source of truth. After changing a note:

```bash
python3 build.py
```

`docs/` is fully regenerated each run — don't hand-edit anything in there, your
changes will be overwritten. Edit the notes, or edit `build.py`.

Point it at a different vault location with `--vault /path/to/Arabic`.

**Adding a lesson needs no edit here.** Drop a new `Lessons/L## — ….md` note in the
vault and rerun; the build discovers it, adds its page, nav chip, home tile and
flashcards, and bumps every “Lessons 1–N” label automatically.

## What the build does

- Lesson notes are already raw HTML (`format: html-tiles`), so they pass through
  with Obsidian-only syntax (`[[wikilinks]]`, `![[embeds]]`) rewritten to real links.
- The Vocab and Grammar banks are markdown; `build.py` has a small converter for
  the subset used (tables, callouts, headings, `:::` card lines).
- A **depersonalize** pass strips the private plumbing before publishing:
  spaced-repetition scheduling comments, `#flashcard` deck tags, references to my
  `arabic-drill` skill and personal Error Log, and dated "fresh set" markers.
  Self-check items I'd already ticked are reset to unticked.
- **Not published:** `Practice/Error Log.md`, `Practice/Cumulative Drill.md`,
  `Practice/Fill-in-the-Blank — Verbs in Context.md`. To publish one, add it to
  `slug_for()` and give it a page in `main()`.

## Credits

Study notes on *Al-Kitaab fii Taʿallum al-ʿArabiyya, Part One* (3rd ed.).
Unofficial student-made review material — not affiliated with the authors or publisher.
Picture cards are [OpenMoji](https://openmoji.org) (CC BY-SA 4.0).
