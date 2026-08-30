# paper-digest — open questions and next steps

Status: arXiv fetch (LaTeX source), LaTeX→HTML renderer, and a reading window with
select-to-ask all work. The skill covers digest / quiz / feed triage.

## The undecided one: what is the reading window actually for?

The demo supports "highlight a passage, ask about it". Plausible alternatives,
not yet chosen — worth using the demo on a real paper before picking:

- [x] ~~Collapsible sections~~ and ~~per-section summaries~~ — done; summaries stay
      visible when the section is collapsed, so the paper folds into an outline.
- [ ] **Margin annotations** — answers pin next to the passage, not in a side log.
      Better for a paper you return to; worse for a running conversation.
- [ ] **Progressive digest** — a persistent per-section summary column that fills in
      as you read, so the digest is a by-product of reading rather than a separate step.
- [ ] **Confusion log** — every question you ask is recorded against its section;
      at the end you get "here is what tripped you up", which feeds quiz generation.
      This is the one that connects reading to the quizzing loop.
- [ ] **Inline quizzing** — finish a section, get 2 MCQs on it before moving on.
- [ ] Does the conversation persist across sessions per paper? Currently no.

## Renderer gaps

- [x] ~~Tables~~ — `tabular` parsed, booktabs rules become row groups.
- [x] ~~`\ref`/`\eqref` linking~~ — resolved to numbers, click scrolls to target.
- [x] ~~Equation numbering~~ — non-starred display maths numbered, `\label` mapped.
- [x] ~~Text-mode macros~~ — `\newcommand` expanded with arguments before rendering.
- [x] ~~Citations~~ — now show the paper's own reference numbers, hover for the entry.
- [ ] `\multicolumn` sets colspan but ignores its alignment argument.
- [ ] Column alignment from the `tabular` spec (`lcr`) is ignored; all cells left-align.
- [ ] Footnotes render as an inline "(" with no closing marker.
- [ ] Two-column `reprint` layout is rendered single-column by choice — reconsider
      only if side-by-side comparison with the PDF turns out to matter.
- [ ] Multi-file papers resolve `\input`, but not `\subimport` or `\import`.
- [ ] No handling of `subfigure`/`minipage`; multi-panel figures render as separate images.

## Fetch / corpus

- [ ] No citation graph yet. INSPIRE-HEP for astro/hep, OpenAlex for LLM work —
      this gates the reading-plan loop entirely.
- [ ] `.bbl` gives citation *strings*, not arXiv IDs, so "open the paper this cites"
      needs a resolution step (title search against the arXiv API).
- [ ] Cache has no index — no way to ask "what have I read?" beyond `ls`.
- [ ] Non-arXiv papers: local PDFs work via `pdf-reader`, not through this pipeline.
- [ ] Versions: fetch pins whatever is current; no notification when a v2 appears.

## Knowledge base (deferred deliberately)

- [ ] Survey cards (LSST, DESI, Euclid, ACT, TDCOSMO) accumulated across papers —
      the stated goal for the cosmology side, but only worth building once the
      digest loop has been used enough to know what should accumulate.
- [ ] Decide: does this become a front-end to LLMtree (claim graph, TMS
      invalidation, citation constraint) or keep its own store? Deciding late is
      cheap right now because the cache is plain files.
- [ ] Cross-paper contradiction flagging depends on whichever store wins.

## Smaller

- [ ] Viewer is single-paper per process; no library view or paper switcher.
- [ ] Feed triage has no persistent interest model — it re-derives relevance each run.
- [ ] Quiz results are not recorded, so nothing tracks what you actually retained.
- [x] ~~`claude -p` subprocess~~ — replaced by the file bridge, so answering happens
      in the interactive session (no separate API billing, whole paper in context).
- [ ] The bridge has no notification: the Claude window only learns of a request by
      polling `bridge.py list` or blocking on `bridge.py wait`.
- [ ] Answers are not persisted per paper — the discussion log dies with the tab.
- [ ] Summaries are regenerated on every click; they are not cached to disk.
