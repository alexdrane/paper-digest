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

- [ ] status: claimed | claimed: alex-drane-21 | **`bridge.py papers` — cache index.**
  No way to ask "what have I read?" beyond `ls ~/.local/share/paper-digest/cache/`.
  Add a command listing every cached paper: title, when fetched, whether it
  has a `session.md` (was actually read/discussed), how many flags, how many
  quiz/summary/note cards in `workspace.json`. This is the missing piece for
  reading-plan / "what do I know" questions the skill's brainstorm wanted.
  Files: `scripts/bridge.py` (new command). Read-only against existing cache
  structure — no server changes needed, safe to build fully standalone.

## Done

- [x] Multi-paper mode (citation resolution, `/open`, paper-switcher dropdown)
- [x] Quiz grading via the bridge (free-response `Grade my answer`)
- [x] Subsection (h3) insert gaps, not just top-level sections
- [x] TOC badges for inserted blocks, SSE retry-on-drop, flag-broken-LaTeX
      reporting (local-only by design — see `viewer.py`'s `/flag` comment)
