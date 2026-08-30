# paper-digest

A Claude Code skill for reading research papers — pulls the real LaTeX source
from arXiv (not the PDF), renders it in a browser with numbered sections and
equations, live citations, tables and figures, and lets you ask questions,
generate summaries, and quiz yourself as you read — all answered by a Claude
Code session running alongside you, not a separate API-billed call.

Click a citation and it resolves against the arXiv API and opens right in the
same window, so you can follow a citation trail without losing your place.

## Requirements

- **Claude Code**, with an active subscription/API access
- **Python 3.10+**, with Flask (`pip install flask`)
- **Poppler** (`pdftoppm`) and **Ghostscript** (`gs`, `ps2pdf`) — for
  converting PDF/EPS/PS figures to images. On Debian/Ubuntu:
  ```bash
  sudo apt install poppler-utils ghostscript
  ```
  On macOS: `brew install poppler ghostscript`
- **`gh` (GitHub CLI)** — optional, only needed if you want to file a broken-
  render report as a GitHub issue yourself (`bridge.py flags --file-issues`);
  everything else works without it.

## Install

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/alexdrane/paper-digest.git ~/.claude/skills/paper-digest
```

Then **restart Claude Code** — skills load at session start, so a session
already running won't see it.

## Using it

In a fresh Claude Code session, either invoke the skill directly:

```
/paper-digest 2602.11264
```

or just paste an arXiv link/ID and ask to read it — the skill's description
matches on that too.

What happens next:

1. Claude fetches the paper (LaTeX source from `arxiv.org/e-print/<id>`,
   falling back to a PDF-text extraction if no source is available) and
   launches a local reading window in your browser.
2. You read there — fold sections, select text and ask questions, insert
   quizzes and summaries between sections, click citations to pull in and
   read the papers they reference.
3. Claude answers everything from the terminal session, in the background,
   while you read. You don't drive that part.
4. When you're done, hit **done reading** in the browser. Claude gets the
   full transcript — every question, your notes, what you flagged as
   broken — and you carry straight on into whatever you want to build or
   discuss next, in the same conversation.

### Manual use (without the skill)

Everything also works as plain scripts, if you'd rather drive it by hand:

```bash
cd ~/.claude/skills/paper-digest/scripts

# fetch a paper's LaTeX source and cache it
python3 arxiv.py fetch 2602.11264

# launch the full reading window (fetches if not cached)
python3 viewer.py 2602.11264

# serve it — answer whatever's queued from the browser
python3 bridge.py wait          # blocks until a question/summary/quiz arrives
python3 bridge.py reply <job> answer.md    # or pipe an answer on stdin

# other useful commands
python3 bridge.py list          # what's currently pending
python3 bridge.py papers        # everything you've cached: read? flagged? quizzed?
python3 bridge.py saved         # papers you've starred, with citation provenance
python3 bridge.py log <id>      # full transcript of a reading session
python3 bridge.py flags         # broken-LaTeX reports (never auto-filed anywhere)
```

## How it's built

- `scripts/arxiv.py` — fetches LaTeX source (or falls back to PDF text),
  searches arXiv, pulls recent listings by category. The only network layer.
- `scripts/texhtml.py` — a from-scratch LaTeX → HTML renderer: sections,
  equations (correctly numbered, including `align` blocks), tables, figures,
  citations resolved against the `.bbl`, custom `\newcommand` macros.
- `scripts/viewer.py` — the Flask server behind the reading window. Never
  calls an LLM itself — every question, summary and quiz request goes onto a
  file-based bridge queue for a Claude Code session to pick up and answer.
- `scripts/viewer.html` — the reading window itself: one file, no build step.
- `scripts/bridge.py` — the CLI a Claude session uses to serve the reading
  window (`list`/`show`/`reply`/`wait`) and to inspect what's accumulated
  (`papers`/`saved`/`flags`/`log`/`blocks`).

Cache lives at `~/.local/share/paper-digest/cache/<id>/` — the LaTeX source,
figures, your reading transcript, and everything you've inserted into the
page (quizzes, summaries, notes, folds). Nothing here is billed separately;
answering happens on whatever Claude Code session is serving the bridge.

## Known gaps

See `TASKS.md` for the current, honest list of what's broken or missing —
it's kept up to date as things land, not a stale wishlist.

## Contributing

`TASKS.md` doubles as a lightweight task pool for parallel work via git
worktrees — see the top of that file for the claim-by-commit protocol if
you want to pick something up.
