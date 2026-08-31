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

- [ ] status: claimed | claimed: alex-drane-75 | **Replace the citation graph panel with a real force-directed node graph.**
  The nested-list `#graphpanel` from the citation-graph task works but isn't
  what the user actually wanted: an Obsidian-style graph view - nodes that
  physically repel each other (force simulation), connected by lines for
  citation edges, draggable/interactive, click a node to open/switch to that
  paper. Data is already there (`GET /citation-graph` returns `{nodes, edges}`
  unchanged - this is a rendering-layer swap, not a backend change).
  Placement: a persistent panel in the **top-right** of the layout, not a
  toggleable dropdown off a toolbar button like the current one - visible
  alongside the paper, not hidden behind a click. Reasonable to keep it
  collapsible/resizable, but default to visible.
  Implementation is open - a small vanilla force simulation (a handful of
  nodes/edges, doesn't need to be fast) or a lightweight force-layout library
  is fine, whichever is less code to get right. No CDN/artifact restrictions
  apply here (this is a locally-served Flask page, not a Claude artifact).
  Files: `scripts/viewer.html` (replaces the current `#graphpanel` rendering
  in `refreshGraph`/`toggleGraph`, plus layout CSS for the new panel position).

- [ ] status: claimed | claimed: alex-drane-21 | **Search the local cache before hitting the arXiv API for citation resolution.**
  `resolve_title` in `viewer.py` always calls out to the arXiv API. Cached
  papers accumulate over a reading session (currently 14 on disk) - if a
  citation's title matches one already fetched, that's a free, instant,
  correct resolution with no network round-trip and no risk of the
  false-miss/title-collision issues already logged for the arXiv-search path.
  Check local cache metadata (`~/.local/share/paper-digest/cache/*/meta.json`)
  for a title match (same similarity-threshold approach as the existing
  arXiv-search path) before falling through to `resolve_title`'s network call.
  Files: `scripts/viewer.py` (`resolve_title` or the `/resolve` route).

- [ ] status: open | claimed: — | **Narrower discussion (chat) column.**
  `#side` is too wide relative to the paper. Reduce its default width (and/or
  its min/max drag-resize bounds) - exact numbers are a judgement call, but
  noticeably narrower than current, without breaking the resize handle.
  Files: `scripts/viewer.html` CSS (`#side`, `#grip`-related bounds).

- [x] status: done | claimed: alex-drane-21 | **Collect a real, growing `.bib` file from citations - resolved or not.**
  The user wants to collect references for their own paper while reading,
  including ones that never resolve on arXiv (older papers, books, journal
  articles with no preprint). We can't recover the author's actual `.bib`
  source - it doesn't exist anywhere accessible - but we already parse enough
  structured data to *reconstruct* a solid synthetic entry either way.
  - **Groundwork**: `format_entry` in `texhtml.py` extracts a `fields` dict
    (author/title/journal/volume/pages/year, from `\bibinfo{field}{value}` in
    revtex-style `.bbl` entries) purely to build the human-readable "display"
    string, then discards it. Thread those fields through instead of
    discarding them - add a `bib_fields: {key: {field: value}}` to `render()`'s
    return dict, alongside the existing `bib`/`bib_titles`. For plain (non-
    revtex) `.bbl` entries where only a flat string is available, `fields`
    will be empty/partial - that's fine, handle it as a lower-quality fallback
    (an `@misc{}` with the flat text in a `note` field, per below).
  - **Storage**: a real, appendable `.bib` file -
    `~/.local/share/paper-digest/references.bib` - not a one-off export. Each
    save appends a `@article{...}` (or `@misc{...}` for the flat-text
    fallback) entry. Generate a citation key (e.g. `firstauthorYEAR`,
    de-duplicated against existing keys in the file - two different papers'
    citations can collide) and dedupe by matching title, not by re-adding the
    same reference twice if saved from two different citing papers.
  - **Two sources for the entry**, both should produce a usable one:
    - Resolved on arXiv: build from the real arXiv metadata (title, authors,
      id) - `journal = {arXiv preprint arXiv:XXXX.XXXXX}`, `eprint`,
      `archivePrefix = {arXiv}` fields, standard shape.
    - Not resolved: build from the *citing* paper's own `bib_fields` for that
      key (the groundwork above) - clearly a reconstruction from a typeset
      bibliography, not the original submission, but the same underlying
      bibliographic data.
  - **UI**: a "save reference" / "☆ bib" action in the citation popover -
    available in *both* the resolved and "not found on arXiv" states (this is
    the whole point: it should work for citations that don't resolve, which
    is the case the user actually asked about).
  - `bridge.py bib` (or similar) to show what's collected so far / the file
    path, matching the style of `bridge.py saved`.
  Files: `scripts/texhtml.py` (`format_entry`, `render` - the groundwork),
  `scripts/viewer.py` (BibTeX construction + `references.bib` read/write +
  a route), `scripts/viewer.html` (the popover action), `scripts/bridge.py`
  (new command).

- [x] Figure spinner race fixed (load/error firing before listeners attach). Done by alex-drane-21 — code-reasoned, not visually confirmed (no browser access). Alex needs to actually check in-browser.
- [ ] status: open | claimed: — | **Follow-up: `.panels .figwrap img{width:100%}` force-upscales small figures.** Flagged by alex-drane-21 as a possibly separate cosmetic regression from the old `flex:1 1 340px;max-width:100%` sizing — not the same bug as the stuck spinner, needs someone with a browser to confirm before fixing. Files: `scripts/viewer.html` CSS.
  alex-drane-75 confirmed server-side is clean: curled every figure of all 8
  loaded papers against the live server, 100% return 200. So this is a
  separate, client-side bug in `wrapFigures()`/`.figspin`.
  Diagnosis (alex-drane-75's, unverified in an actual browser - do that
  first): `.figspin` is an *opaque* overlay
  (`position:absolute;inset:0;background:var(--card)`), removed only by the
  `img`'s `load` event. Most figures already have a cached `.conv.png`, so the
  server responds near-instantly - if `wrapFigures` runs `img.replaceWith(w)`
  (detaching and reattaching the `<img>` into a new wrapper) while that image
  is mid-load, some browsers abort/never re-fire `load`, so neither `load` nor
  `error` ever fires and the opaque spinner sits forever over a perfectly
  loaded image underneath. Matches the exact symptom: figure fine, spinner
  stuck.
  Suggested fix, needs the actual visual symptom confirmed first (stuck
  spinner? "figure failed to render" text? broken-image icon? - these have
  different causes): after attaching both listeners, add a fallback check -
  `if(img.complete) (img.naturalWidth>0 ? s.remove() : showFail());` - to
  catch the case where the load/error event already fired (or never will)
  before the listeners were attached. Also worth checking:
  `.panels .figwrap img{width:100%}` force-upscales every figure regardless of
  its natural size, vs the pre-wrapping `flex:1 1 340px;max-width:100%` -
  possibly a separate, smaller regression from the same change.
  Files: `scripts/viewer.html` (`wrapFigures`, `.figspin`/`.figwrap` CSS).

- [x] URGENT bug fixed: figure src now embeds ?id=. Done by alex-drane-75.
  Confirmed against real server access logs (not synthetic tests) - every
  `/figure/<name>` request from the browser carries no `?id=` at all. Server's
  `/figure` route does `figdir = FIGDIRS.get(request.args.get("id") or
  START_ID)` - so with no id sent, it *always* looks in `START_ID`'s figures
  folder, for every paper. Any paper other than the one the server happened
  to launch on has 100% of its figures 404 forever, regardless of whether
  they're actually on disk (this is bigger than, and mostly subsumes, the
  earlier stale-cache-figures fix - that fix was real but doesn't matter if
  the URL never reaches the right paper's folder in the first place).
  Root cause: `render_float` in `texhtml.py` hard-codes `src="/figure/{name}"`
  with no id - and `texhtml.render()` never receives the paper's arxiv_id in
  the first place, so it has no way to embed one even if it wanted to.
  Fix: thread the arxiv_id through to `render()`/`render_float` (it's known
  at every call site in `viewer.py`'s `load()`) and embed it in the `src`
  URL - `src="/figure/{name}?id={arxiv_id}"`. HTML is regenerated fresh on
  every `load()` call (not cached to disk), so this fix applies immediately
  on restart with no data migration needed.
  This has been reported three times this session and is still broken -
  treat as priority over anything else in the pool.
  Files: `scripts/texhtml.py` (`render`, `render_float`), `scripts/viewer.py`
  (the `render()` call site in `load()`).

- [ ] status: open | claimed: — | **New paper load is slow — decouple figures from getting text on screen.**
  Current pipeline for a fresh (uncached) paper: `viewer.py`'s `load()` shells
  out to `arxiv.py fetch` as a **blocking subprocess** (`subprocess.run`,
  `check=True`) that downloads the whole e-print tarball, and - in one pass,
  inside `fetch_source_text` - both writes every figure file to disk *and*
  assembles the `.tex`. Only once that whole subprocess returns does `load()`
  read `fulltext.txt` and run `texhtml.render()`, and only after *that*
  completes does `/open`/`/paper` send anything to the browser. So the reader
  waits for figure bytes to be downloaded and written to disk (these papers'
  tarballs are frequently multi-MB, dominated by figure PDF size - one in
  today's session was 5.5MB) before seeing a single word of text, even though
  individual figure *conversion* to PNG is already lazy per-request.
  The network download of the tarball itself can't be split (arXiv's e-print
  endpoint returns the whole thing in one response, text and figures
  together) - but everything downstream of having those bytes in memory can
  be reordered. Fix direction: in `fetch_source_text`, do the fast pass first
  - assemble and return the `.tex`/`.bbl` content immediately once the tarball
  is parsed - and defer the actual figure disk-writes to a background
  thread that doesn't block the caller. Server-side, `load()`/`/open`/`/paper`
  should return the rendered doc as soon as text parsing is done, not wait on
  every figure being written to `figures/` first. Individual `<img>` requests
  hitting `/figure` before their file has landed should either wait briefly
  or 202/retry rather than 404ing during that window.
  Files: `scripts/arxiv.py` (`fetch_source_text`), `scripts/viewer.py`
  (`load`, and the `/open`/`/paper` routes' relationship to it).

- [x] Cache-hit check now detects missing figures and re-fetches. Done by alex-drane-75.
  Found and fixed live for one paper (arXiv:2602.22307 — real bug, confirmed:
  its tarball genuinely contains 8 figure PDFs at full size, but its cached
  `figures/` dir had zero files; `arxiv.py fetch --refresh` fixed it
  immediately, and re-running `fetch_source_text` in isolation just now
  extracted all 8 cleanly, so the extraction code itself is fine - this paper
  was almost certainly fetched early in this project, before figure
  extraction existed at all, and the cache has been silently stale since).
  The actual gap: `cmd_fetch`'s cache-hit check only looks at whether
  `meta.json`/`fulltext.txt` exist, never whether `figures/` is consistent
  with what the cached `fulltext.txt` actually references via
  `\includegraphics`. So any paper fetched by an older code version, or one
  whose figure extraction silently failed for any reason, stays broken
  forever with no signal beyond a reader noticing "figure failed to render"
  by eye - swept the rest of the cache manually this session and only found
  the one instance, but that was luck, not a guarantee.
  Fix: in `cmd_fetch`, when serving a cache hit, cheaply check whether any
  `\includegraphics` reference in the cached `fulltext.txt` has no
  corresponding file (by basename) in `figures/` - if so, treat it like
  `--refresh` for that paper rather than serving the stale cache silently.
  Files: `scripts/arxiv.py` (`cmd_fetch`).

- [ ] status: open | claimed: — | **Citation resolution: real misses, and a silent-wrong-match risk.**
  Ran a real batch test against arXiv:2602.11264's bibliography (10 citations):
  9/10 resolved correctly at 0.98-1.0 confidence. Two distinct problems in the
  remaining case and a near-miss:
  1. **False miss.** `shen2011catalog` ("A catalog of quasar properties from
     sloan digital sky survey data release 7") genuinely exists on arXiv as
     `1006.5178`, but `resolve_title`'s `ti:"..."` field query returns zero
     hits for it - arXiv's title-field search is apparently stricter than a
     human reader's notion of "same title" (case, punctuation, or word-order
     sensitivity, or our `.bbl`-extracted text differing subtly from the real
     arXiv title). The plain-text fallback then returns completely unrelated
     garbage (particle physics, gravitational-wave papers), which the 0.72
     similarity threshold correctly rejects - so this fails safe (a clean
     miss, not a wrong match) but still fails.
  2. **More concerning: a real title-collision risk.** `ulrich1997variability`
     and `peterson2001variability` - two *different* citations, generically
     titled "Variability of active galactic nuclei" - both resolved to the
     exact same arXiv id (`astro-ph/0109495`, published 2001) at confidence
     1.0. Ulrich et al. is a 1997 review; if it's not on arXiv at all (quite
     plausible for an older ARAA review), this is a **silent wrong match**,
     not a safe miss - title-only matching with no author/year cross-check
     can't tell two same-titled papers apart, and unlike case 1, this doesn't
     visibly fail, it just opens the wrong paper confidently.
  Fix directions: for (1), try a less strict tier before the unconstrained
  plain-text fallback - e.g. a `ti:` query without quotes, or the first ~6
  words only. For (2), add a secondary check using data already available -
  the bib entry string has the first author's surname; compare it against the
  arXiv result's author list before accepting a match, not just title
  similarity. Do (2) regardless of (1)'s outcome - it's the more important
  fix since it's a silent-failure mode, not a visible one.
  Files: `scripts/viewer.py` (`resolve_title`).

- [x] `\ensuremath`/`\xspace` in macro bodies fixed. Done by alex-drane-75.
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

- [x] MathJax label/tag state reset on re-typeset. Done by alex-drane-21.
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

- [x] Title extraction no longer captures \thanks/\footnote. Done by alex-drane-75.
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

- [ ] status: claimed | claimed: alex-drane-7a | **"Why was this cited?" — contextual summary when a citation is opened.**
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

- [x] Citation web/graph viewer done. Done by alex-drane-75.
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
