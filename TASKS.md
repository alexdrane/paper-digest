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

- [ ] status: claimed | claimed: alex-drane-75 | **`\ensuremath{...}` inside a macro expansion renders as literal text.**
  Reproduce: arXiv:2602.22307 defines `\newcommand{\days}{\ensuremath{\mathrm{days}}\xspace}`
  and uses `\days` in body text (e.g. "10 \days"). Rendered output shows the
  literal text `\ensuremath`, `days`, `\xspace` instead of just "days" — see
  screenshot, §5.2 "Sampling Δt". `\ensuremath` isn't in `texhtml.py`'s
  `SIMPLE` unwrap dict (`textbf`/`mbox`/etc.) or handled elsewhere, and
  something about it surviving expansion suggests the generic
  backslash-command-stripping fallback isn't reliably catching commands that
  arrive via macro expansion (`expand_macros` output) rather than being
  present in the original source text directly - needs tracing through
  `inline()`'s actual order of operations to pin down, not just adding
  `ensuremath` to `SIMPLE` (worth doing regardless, but may not be the whole
  fix if the real issue is expansion-order related). `\mathrm{...}` isn't in
  `SIMPLE` either and is likely part of the same failure.
  Files: `scripts/texhtml.py` (`inline`, `SIMPLE`, `expand_macros`).

- [ ] status: claimed | claimed: alex-drane-21 | **MathJax "Label ... multiply defined" for a label that's only defined once in source.**
  Reproduce: arXiv:2602.22307, the "regularised log-likelihood" equation.
  Confirmed in the cached `fulltext.txt` — `\label{eqn:regularised-log-likelihood}`
  appears exactly **once** as a definition (one `\ref` elsewhere referencing
  it) - this is not a paper-authoring duplicate, it's a rendering bug. See
  screenshot: MathJax renders "Label 'eqn:regularised-log-likelihood' multiply
  defined" in place of the equation.
  Working hypothesis: MathJax's AMS-math label registry is per-page and
  persists across separate `MathJax.typesetPromise()` calls unless explicitly
  reset. `renderPaperDoc` re-typesets the whole `#doc` on every paper switch
  (`MathJax.typesetPromise()`, no scoping) - if a paper containing this label
  gets typeset more than once in one browser session (revisiting it via the
  paper-switcher dropdown, or opening the same citation twice), MathJax
  would see the same `\label{...}` defined a second time and correctly (from
  its own point of view) flag a collision, even though our source only has it
  once. Fix direction: reset MathJax's tex label/tag state before each full
  `#doc` re-typeset (`MathJax.texReset()` or clearing
  `MathJax.startup.document`'s label list - check current MathJax v3 API) so
  revisiting a paper doesn't accumulate stale label state.
  Files: `scripts/viewer.html` (wherever `MathJax.typesetPromise()` is called
  for a full paper render - `renderPaperDoc`).

- [x] Refresh now restores the last-viewed paper. Done by alex-drane-75. **Browser refresh always reloads the launch paper, not whichever you were viewing.**
  Real gap on top of the LIB/FIGDIRS server-side persistence (already fixed):
  that fix means the *server* remembers every paper across a restart, but the
  *initial page load* — `fetch('/paper').then(...)` at the top of
  `viewer.html`, no `?id=` — always resolves to `START_ID` server-side
  (`get_doc(None)` falls back to `START_ID`). So a plain browser refresh while
  looking at a citation-opened paper snaps you back to the paper the process
  launched on, even though that other paper's data was never actually lost.
  Same root cause explains what looks like "the queue disappeared" — the queue
  panel polls `/pending?id=CURRENT`, so once a refresh resets `CURRENT` back
  to `START_ID`, a pending request for the paper you'd switched to just stops
  showing up (it's still on disk in `bridge/queue/`, still answerable via
  `bridge.py list`/`show`/`reply` directly — nothing is deleted).
  Fix: persist the last-viewed paper id client-side — `localStorage`, same
  pattern already used for theme (`pd-theme`) and font size (`pd-fs`) — and on
  load, fetch that id instead of the bare `/paper` (falling back to the bare
  call if that id 404s, e.g. the process was relaunched on a different start
  paper and never restored it — shouldn't happen post-persistence-fix, but
  don't hard-fail on it). Update it wherever `CURRENT` is set
  (`renderPaperDoc`).
  Files: `scripts/viewer.html` only (`renderPaperDoc`, the initial `fetch`).

- [ ] status: open | claimed: — | **Title extraction can capture a `\thanks`/footnote inside `\title{}`.**
  arXiv:0803.4015 (an old COSMOGRAIL paper) renders its title as the telescope
  acknowledgment credits ("Based on observations obtained with the 1.2m EULER
  Swiss Telescope...") instead of the actual paper title — its `\title{}`
  macro has a `\thanks{}`/footnote embedded that `grab("title")` in
  `texhtml.py`'s `render()` isn't stripping before extracting the title text.
  Reproduce: `python3 scripts/arxiv.py fetch 0803.4015 --refresh` then check
  `title` in the output, or open it in the reader.
  Fix: strip `\thanks{...}`/`\footnote{...}` (balanced-brace, like
  `remove_cmd` already does for front-matter commands) from the raw title text
  before running it through `inline()`.
  Files: `scripts/texhtml.py` (`render`, the `grab("title")` path).

- [ ] status: open | claimed: — | **"Why was this cited?" — contextual summary when a citation is opened.**
  Clicking a citation and opening the cited paper currently drops you into a
  generic full render with no framing. The actual reason someone clicks a
  citation is usually narrower: is this foundational, a data source, a
  competing method, or (often) just borrowing one piece of methodology from
  an otherwise-irrelevant paper? The answer should say which, and if it's the
  methodology case, point at the *specific section* responsible rather than
  summarising the whole cited paper.
  - When a citation is opened (the "Open arXiv:X in reader →" flow in the
    popover — `openCitePopover`/`/open` in `scripts/viewer.py`), also capture
    what's already computed client-side but currently unused past that click:
    the citing paper's id, the section the citation appeared in, and the
    passage/selection around the `.cite` span (same data `openCitePopover`
    already has for `/resolve`).
  - Enqueue a bridge request, new `kind: "citation-context"`, carrying: the
    newly-opened (cited) paper's id/title/abstract, and the citing paper's
    id/title/section/passage. The answering session reads the cited paper
    (already fetched — full text is on disk) and writes a short answer:
    what's actually being cited for, and — this is the part worth building
    well — reference the *specific block(s)* of the newly-opened paper with
    `[[bNN]]` (the hover-source marker mechanism already exists and already
    resolves against whatever paper is currently displayed) rather than a
    generic abstract restatement. `bridge.py blocks <id> [term]` is the tool
    for finding the right block to cite here.
  - Render this as a small persistent card at the top of the newly-opened
    paper — right where the abstract box is — so it's the first thing visible
    when the citation-driven paper opens, since "why did I click this" is the
    question at that moment, before anything else.
  Files: `scripts/viewer.html` (`openCitePopover`, `renderPaperDoc` for the
  card placement), `scripts/viewer.py` (`/open` or a new route to enqueue the
  request), `scripts/bridge.py`/`SKILL.md` (document the new request kind,
  same pattern as `question`/`summary`/`quiz`/`grade`).

- [ ] status: open | claimed: — | **Citation web/graph viewer.**
  As citations get opened, build up an actual traversable graph — not just a
  flat "papers I've opened" list. Depends on the durable open-paper tracking
  from the LIB/FIGDIRS persistence task (currently in flight) for stable ids
  across restarts — check that's landed, or coordinate, before starting.
  - Persist a citation-edge list alongside that: `{from: citing_id, to:
    cited_id, section, keys, opened_at}` per citation-driven open (distinct
    from `saved.json`'s `via`, which is a single provenance field, not a full
    edge list — this needs to support a paper citing multiple others, and
    being cited by multiple citing papers, i.e. a real graph, not a tree).
  - A `GET /citation-graph` route returning nodes (papers, from the persisted
    open-paper list + cache metadata) and edges.
  - A viewer for it — doesn't need to be a heavy force-directed graph library;
    a clean nested/list-based view (grouped by "cited by") is a legitimate,
    simpler choice if it reads well. Functional requirement over visual one:
    click a node to jump to/open that paper, see at a glance which paper led
    you to which via which citation.
  Files: `scripts/viewer.py` (persistence + route), `scripts/viewer.html` (the
  view — could be a toggleable panel rather than a permanent UI element, given
  it's not needed every session).

- [x] Paper switch scrolls to top + fade transition. Done by alex-drane-21. **Switching papers doesn't scroll to top or give any indication of the change.**
  `switchPaper`/`renderPaperDoc` swap `#doc`'s content in place — if you were
  scrolled halfway down the old paper, you land at the same scroll offset in
  the new one (often mid-paragraph, disorienting), and there's no visual cue
  a switch even happened beyond the content silently being different.
  Fix: on switch, reset `#paper`'s scrollTop to 0 (smooth-scroll is fine,
  match the existing `behavior:'smooth'` pattern used elsewhere), and add a
  brief visible transition — e.g. a short fade/flash on `#doc`, or reuse the
  `.card.new` flash-on-arrival CSS pattern already in the file — so a switch
  reads as an event, not a silent content swap.
  Files: `scripts/viewer.html` (`renderPaperDoc`/`switchPaper`).

- [x] LIB/FIGDIRS/WORKDIRS now persist across restarts. Done by alex-drane-75.
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
