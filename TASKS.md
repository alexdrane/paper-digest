# Task pool

A lightweight backlog for parallel worktree sessions on this skill. No Jira —
this file *is* the board, tracked in git so every session sees the same state.

## How to claim one

1. `EnterWorktree` (or say "start a worktree") — forks from `origin/master`.
2. Pick an **open** task below whose file list doesn't overlap one already
   `claimed`. Prefer tasks nobody else is touching.
3. Edit its line here to `claimed: <your session name>`, commit *just that
   one-line change*, and push your worktree branch immediately — that's the
   signal to everyone else that it's taken. (`ListAgents` names your session;
   use that.)
4. Do the work. Syntax-check JS with `node --check` and Python with
   `python3 -c "import ast; ast.parse(open(f).read())"` before restarting the
   shared dev server — someone may be using `http://127.0.0.1:5177` live.
5. Commit, push your branch, then message `alex-drane-2a` (master) with the
   branch name to merge. Don't merge into `master` yourself — avoids two
   people racing a fast-forward.
6. Mark the line `done` in your last commit on the branch.

Master will not edit a file a task below claims, to keep merges clean.

## Open

- [ ] status: open | claimed: — | **Bug: LIB/FIGDIRS/WORKDIRS reset on every server restart.**
  Same root cause behind two separate user-visible symptoms: (1) the
  paper-switcher dropdown only ever shows the paper the process launched on
  after any restart — every paper opened via a citation click is gone from
  `/library`, even though its cache on disk is fully intact; (2) worse, every
  figure for a paper not in the *current process's* `FIGDIRS` 404s outright —
  `/figure` looks up `FIGDIRS.get(id)` which is populated only by `load()`,
  and `load()` only runs for a paper actually opened in this run. Confirmed:
  reopening the paper via `/open` immediately fixes its figures again, so the
  image files and conversions are fine — it's purely that the server forgot
  the paper existed. This has been happening on every worktree-branch merge
  this session (each merge needs a restart to pick up the code), so it's not
  a rare edge case in practice.
  Fix direction: persist which arXiv ids have been opened (a small JSON list
  next to `saved.json`, e.g. `open_papers.json` — NOT the full render, just
  the id list) and on startup, restore `LIB`/`FIGDIRS`/`WORKDIRS` for each one
  by re-running `load()` before the server starts serving. Cheap since
  `load()` only re-fetches if `fulltext.txt` is missing — everything else is
  already cached on disk.
  Files: `scripts/viewer.py` (`load`, startup, a small persistence helper next
  to the existing `load_saved`/`write_saved` pattern for saved papers).

- [x] Save/star a paper — done by alex-drane-75. **Save/star a paper — a real "collect interesting references" list.**
  Distinct from both "cached" (fetched once, no intent attached) and "open in
  this session" (`/library`, lives in server memory, resets on every restart —
  see the earlier lost-papers issue). A save is a deliberate action: keep a
  small persisted list of papers the reader actually wants to come back to.
  - Storage: a simple JSON list, e.g.
    `~/.local/share/paper-digest/saved.json` — `[{arxiv_id, title, saved_at,
    via}]`, where `via` is provenance (e.g. the arXiv id of the paper you were
    reading when you saved it, or `null` if saved directly) — that's what
    makes this useful as a citation-rabbit-hole collector, not just a list.
  - Server: `POST /save` and `POST /unsave` (`{id, via}` / `{id}`), and thread
    a `saved: bool` into whatever already reports on a paper so the UI can
    show the right star state — `/library`'s entries and/or `/paper`.
  - UI: a save/star action in two places — the citation popover (next to "Open
    arXiv:X in reader →", so a reference can be *collected* without switching
    reading focus to it, which is the whole point) and somewhere in the main
    toolbar for the paper currently open.
  - `bridge.py saved` — list the saved papers, each with its `via` provenance
    if any, similar style to `bridge.py papers`.
  Files: `scripts/viewer.py` (routes + storage), `scripts/viewer.html` (star
  UI), `scripts/bridge.py` (new command).

- [x] Word-wrapped prose rendering. Done by alex-drane-21.
  `md()` calls `marked.parse(text,{breaks:true})`, which turns every single
  `\n` into a `<br>`. That's fine for genuinely short lines, but any answer
  authored with mid-paragraph line wrapping (very easy to do by hand when
  writing a `bridge.py reply` file at a fixed column width) renders as one
  choppy line per wrap instead of a flowing paragraph — happened with a real
  answer in this session, looked broken though the content was fine.
  Two independent fixes, ideally both: (1) in `md()`, collapse single
  newlines that aren't inside a list/code block into spaces before parsing
  (a paragraph is separated by a *blank* line, not fixed manually) so the
  renderer is robust to how the text was authored; (2) add a line to
  `SKILL.md`'s answering guidance telling an answering session not to
  hard-wrap prose in an answer — one paragraph, one line, let the browser wrap
  it. Do (1) regardless, since (2) alone doesn't fix content already written
  wrong or a future session that forgets.
  Files: `scripts/viewer.html` (`md()`), `SKILL.md`.

- [ ] status: open | claimed: — | **Bug: a lost answer can never be recovered, even by refreshing.**
  `addCard()` calls `saveState()` immediately on creation, while the card still
  says "queued for your Claude window" and `el.dataset.raw` is empty — so an
  empty placeholder gets written to `workspace.json` right away. If the SSE
  stream that's supposed to deliver the real answer then gets stranded (e.g. a
  server restart while it's mid-retry, or the tab loses the connection for any
  other reason) and the retry logic in `streamJob()` eventually gives up, the
  card is left holding empty content — and because that was already persisted,
  even reloading the page just restores the same empty card. The answer is
  often still recoverable (it exists on disk in
  `~/.local/share/paper-digest/bridge/answers/<job>.md` until something cleans
  that directory), but nothing in the running app re-checks for it once a
  card's initial `saveState()` has fired.
  Fix direction: don't persist an insert's empty/placeholder state at all (skip
  `saveState()` in `addCard` until real content or a terminal error arrives),
  and/or have `streamJob`'s give-up path do one last check against
  `/pending`+the bridge answers dir before declaring the connection lost, so a
  stray answer that arrived after the last retry isn't stranded forever.
  Files: `scripts/viewer.html` (`addCard`, `streamJob`).

- [x] UI polish: title truncation + figure loading spinner. Done by alex-drane-75.
  Two reported issues: (1) long paper/section titles render unbounded and look
  bad — the `#paperSelect` dropdown options show the full title (native
  `<select>` doesn't support CSS ellipsis, so truncate the string itself, e.g.
  `trunc(title, 52)`), and `.card>h6` headers (`Quiz · <long name>`) have no
  width constraint on the title text, pushing the remove button around — wrap
  it in a span with `overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  min-width:0`, `title=` attr for the full text on hover. (2) figures with no
  loading indicator — the first view of a PDF/EPS/PS figure triggers an
  on-demand `pdftoppm`/`ghostscript` conversion server-side (see `/figure` in
  `scripts/viewer.py`) that can take a couple of seconds, during which the
  `<img>` just sits blank/broken. Wrap each `.panels img` (client-side, after
  `$('doc').innerHTML=...` in `renderPaperDoc` — no `texhtml.py` changes
  needed) in a container that shows a spinner until the image's `load`/`error`
  event fires, matching the `.spin` pattern already used for the citation-open
  button.
  Files: `scripts/viewer.html` only.

- [x] status: done | claimed: alex-drane-75 | **Hover-source citations in answers.**
  Claude's markdown answers (questions/summaries/grades) should ground claims
  in the paper: define an inline marker like `[[bNN]]` referencing a block id,
  post-process it in `md()` into a hoverable/clickable span whose tooltip
  shows that block's source text (`PAPER.blocks` already carries `raw` and
  `html` per block — see the `[[keys]]` handling in `.cite` spans for the
  existing pattern to extend, not copy verbatim). Add a `bridge.py blocks
  <arxiv_id> [term]` command so the answering session can find the right id
  to cite (render the cached `fulltext.txt` via `texhtml.render`, optionally
  filter blocks by a grep term, print `id | section | raw[:100]`). Update
  `SKILL.md`'s answer-writing guidance to use it.
  Files: `scripts/viewer.html` (`md()`, `.qz`/`.cardbody`/chat rendering),
  `scripts/bridge.py` (new command), `SKILL.md`.

- [ ] status: open | claimed: — | **Table rendering: alignment.**
  `render_tabular` in `texhtml.py` parses the `tabular` column spec (`{lcr}` /
  `{@{}ll@{}}` etc.) but ignores it — every cell renders left-aligned.
  `\multicolumn{n}{c}{...}` also sets `colspan` but drops its own alignment
  argument. Parse the spec, apply `text-align` per column (and honour a
  multicolumn cell's own alignment over the column default).
  Files: `scripts/texhtml.py` (`render_tabular`), CSS in `viewer.html` if a
  per-column class is cleaner than inline `style=`.

- [ ] status: open | claimed: — | **Footnotes render broken.**
  `inline()` in `texhtml.py` does `text.replace(r"\footnote{", "(")` — the
  footnote body isn't closed off (no matching `)`, content just runs into the
  paragraph) and it isn't distinguishable from parenthetical text. Fix: render
  as a small superscript marker with a hover tooltip carrying the footnote
  body (same interaction pattern as `.cite`), not inline parenthesised text.
  Files: `scripts/texhtml.py` (`inline`), CSS/JS in `viewer.html` for the
  hover marker (a distinct class from `.cite` so the two don't collide).

- [ ] status: open | claimed: — | **Citation resolution caching.**
  `/resolve` re-runs an arXiv title search every time the same citation is
  clicked — slow (politeness throttle in `arxiv.py`) and wasteful on a
  well-cited paper you reopen often. Cache resolved `{key: match}` pairs in
  that paper's `WORKDIR` (e.g. `resolved.json` next to `workspace.json`), keyed
  by bib key; check the cache before calling `resolve_title`.
  Files: `scripts/viewer.py` (`resolve()` route).

- [x] `bridge.py papers` — cache index. Done by alex-drane-21.

## Done

- [x] `bridge.py papers` cache index — title, fetched-when, read/discussed vs
      fetched-only, flag count, quiz/summary/note card counts
- [x] Multi-paper mode (citation resolution, `/open`, paper-switcher dropdown)
- [x] Quiz grading via the bridge (free-response `Grade my answer`)
- [x] Subsection (h3) insert gaps, not just top-level sections
- [x] TOC badges for inserted blocks, SSE retry-on-drop, flag-broken-LaTeX
      reporting (local-only by design — see `viewer.py`'s `/flag` comment)
