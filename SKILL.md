---
name: paper-digest
description: Read a paper in a browser reading window driven from this session - fetches the arXiv LaTeX source, renders it with numbered equations and live citations, and answers the reader's questions, section summaries and quizzes as they work through it, then hands the whole reading transcript back here so they can carry straight on into building. Also digests and triages papers they are not going to read closely. Use when the user gives an arXiv ID or link, asks to read/digest a paper, wants quizzing on one, or asks what is new in astro-ph.CO / cs.CL / cs.LG.
---

# Paper digest

Reading tool for cosmology (surveys, time-delay cosmography, inference) and LLM
research. The point is **comprehension and accumulation**, not summarisation —
a generic abstract-restatement is a failure, not an output.

## Fetching

`scripts/arxiv.py` is the only network layer. Never scrape arxiv.org by hand.

```bash
S=~/.claude/skills/paper-digest/scripts/arxiv.py
python3 $S fetch 2602.22307          # id, arXiv:id, or any abs/pdf URL
python3 $S search 'all:"time delay cosmography" AND cat:astro-ph.CO' -n 10
python3 $S feed astro-ph.CO,cs.CL --days 3 -n 60
```

`fetch` prints JSON with `text_path`; read that file for the body. It prefers the
**LaTeX source** (real sections, `\cite` keys, equations, `.bbl` bibliography) and
falls back to PDF text only when source is unavailable — `text_source` says which.
Results are cached under `~/.local/share/paper-digest/cache/<id>/`, so re-fetching
is free; pass `--refresh` only if you need a newer version.

For a paper that is not on arXiv, read the PDF directly and skip to Digesting.

## The session shape

This skill runs one loop, and it moves between two places:

1. **Here**, briefly — launch the window on a paper.
2. **The browser**, for as long as reading takes. The user reads, folds sections,
   asks about passages, inserts quizzes. Every one of those arrives here as a
   bridge request and **you answer it from this session**, with the whole paper
   available. You are serving the window; you are not driving it.
3. **Here again**, when they are done. You now hold the transcript of what they
   asked, their notes, and the quizzes — so "let me test that idea from §4"
   works without them re-explaining anything. Drop the reading behaviour
   entirely and be a normal assistant: write the code, edit the paper, whatever
   they came back for.

The point of step 3 is that reading and building happen in one continuous
session. Do not make them repeat context they already established in the window.

### 1 · Launch

```bash
python3 ~/.claude/skills/paper-digest/scripts/viewer.py 2602.11264
```

Accepts an arXiv id, `arXiv:` form, or any abs/pdf URL, and fetches it if it is
not cached. Say the URL in one line, then start serving. Do not summarise the
paper before they have read it - that is the user's job, and pre-empting it is
the main way this tool can fail them.

### 2 · Serve the window

```bash
B=~/.claude/skills/paper-digest/scripts/bridge.py
python3 $B wait --timeout 600     # blocks until a request arrives
python3 $B reply <job> answer.md  # or pipe the answer on stdin
```

Loop: `wait` → read what it prints → answer → `wait` again. Keep looping until
`wait` reports the session ended or the user says stop. If `wait` times out with
no request, loop again without comment - they are reading, which is the point.

Requests carry `fulltext:` (the paper's path), the section, the highlighted
passage and the works cited in it. Answer against the whole paper, not just the
passage; that context is the reason this path exists rather than a chatbot in
the page.

**Ground your claims in the paper.** When an answer, summary, quiz explanation or
grade makes a claim that rests on a specific passage, cite the block it comes
from with an inline `[[bNN]]` marker (e.g. "the mean can absorb any kernel
signal [[b41]]"). The window post-processes it in `md()` into a small `src` chip
whose hover shows that block's source text and whose click scrolls the paper to
it. Find the id with:

```bash
python3 $B blocks <arxiv_id> [term]   # id | section | raw[:100], optionally grepped
```

Cite blocks you actually used; two or three per answer is usually right. Don't
cite the front matter or a heading block, and don't turn every sentence into a
chip. `[[bNN]]` is for paper blocks only — bibliography references still render
through the paper's own `\cite` numbers.

**Don't hard-wrap prose.** Write each paragraph of an answer as one long line
and separate paragraphs with a blank line. The window renders single newlines
as line breaks, so a paragraph wrapped at a fixed column comes out as a column
of choppy lines. (`md()` now unwraps single newlines defensively, but keep the
source clean — lists, tables and code blocks still depend on real newlines.)

Three kinds arrive:

- `question` — a passage and their question. Answer it directly, in Markdown;
  `$...$` maths is typeset in the page, so write maths normally.
- `summary` — 3-5 sentences: what the section establishes, the mechanism, and
  any assumption it quietly relies on. No preamble.
- `quiz` — see QUIZ FORMAT below. May cover several sections at once.

### 3 · Hand back

When the reader presses **done reading**, `wait` prints `READING SESSION ENDED`.
Then:

```bash
python3 $B log 2602.11264
```

That prints every question and answer from the window, the reader's own notes,
and which sections they folded away. Read it, say in **two lines at most** what
they seemed to be chasing, and ask what they want to build. Then get on with it.

## The reading window

The page is the whole interface - there is no second surface.

- **Sections are blocks.** Hovering a section shows a rail: *fold*, *select*,
  *quiz*, *summary*. Folding leaves the heading and any inserted card visible, so
  a read paper collapses into its own outline.
- **Blocks go between sections.** The `+ insert block` gap opens a menu: quiz on
  this section, quiz on everything so far, a summary, or the reader's own note.
- **Selecting several sections** then *Quiz these* covers them together, which is
  where the useful cross-section questions live.
- Selecting text and pressing *Ask about this* sends the passage with its section
  and citations.
- Everything inserted is saved to `workspace.json` beside the cached paper and
  restored on reload.

Rendering: numbered sections and equations, resolved `\ref` links, the paper's own
citation numbers (hover for the entry), figures (click to zoom), booktabs tables.

**Reporting broken rendering.** Selecting text also shows a red **!** button next
to *Ask about this*. It saves the raw LaTeX for that block, the HTML it rendered
to, the section, and an optional note - for fixing the renderer, not for
answering. It does not go through the bridge and does not need you watching.
Check `bridge.py flags [arxiv_id]` at the start of a session working on this
skill's own code, and when the user asks what's broken.

## Digesting

Read the full text — not just the abstract and conclusions. Then write a digest
with these parts, in this order:

1. **The claim** — one sentence, the actual load-bearing result. Not the topic.
2. **Why it was hard** — what blocked this before; what the paper had to get past.
3. **Mechanism** — how the method works, concretely enough to argue with. Include
   the key equation(s) if there are any; this is the section that earns its length.
4. **Assumptions and where it breaks** — what is assumed, stated or not, and the
   regime where the result stops holding. Papers under-report this; infer it.
5. **What is new vs prior work** — position it against what it cites.
6. **Glossary** — terms, surveys, instruments and methods used as if known. Mark
   anything the user probably has not met with a short definition. This is the
   most valuable section for a paper in an unfamiliar subfield; do not skip it.
7. **Worth your time?** — a direct verdict: read fully, skim §N, or skip, and why.

Be opinionated. If a result is oversold, weakly evidenced, or a minor increment,
say so plainly. Flag anything that contradicts a paper already in the cache.

### Calibrating the delta

The user is a Part III student working on nested sampling and GP time-delay
cosmography with Will Handley. Do not explain nested sampling, Bayesian evidence,
GPs, or `H0` tension to them. Do explain unfamiliar surveys, instrument
specifics, unfamiliar statistical machinery, and anything from LLM research
beyond the widely-known. When unsure whether something is known, ask rather than
padding the digest.

## Quizzing

Quizzes are rendered **inside the reading window**, as a card inserted between
sections — not in latex-panel, not in the terminal. The user asks for one from a
section's rail or the `+ insert block` gap, and the request arrives on the bridge
with `kind: quiz` and the list of sections it covers.

### QUIZ FORMAT

Reply with this and nothing else — no preamble, no closing remark:

```
?? What does the flat-top region of the likelihood imply about the delay posterior?
( ) The delay is unidentifiable below the sampling cadence
(*) The evidence integral is dominated by a volume the sampler rarely visits
( ) Microlensing has been mismodelled
> The flat top is a volume effect, not an identifiability one - see the
> discussion around eq. 14.

?? Why does increasing n_live help here, and what does it cost?
> A good answer connects mode survival to the compression rate, and notes the
> cost is linear in n_live for a fixed number of iterations.
```

- `??` starts a question. `( )` is a wrong option, `(*)` the correct one.
- **Omit the options entirely to make it a free-response question** — the window
  renders a text box and a *show model answer* button. `>` lines are the
  explanation (MCQ) or the model answer (free response).
- Maths in `$...$` works; it is typeset in the card.

### GRADE FORMAT

Free-response questions carry a **Grade my answer** button. It sends the
question, the reader's typed answer, and the model answer (for your reference —
don't just diff against it) as `kind: grade`. Reply with the verdict word on its
own line, then feedback:

```
PARTIAL
Right that the drift and kernel are competing for the same power, but the
answer doesn't say why that makes the split unidentifiable in principle rather
than just numerically fiddly - see the note in §2.1 about the flexknot mean
being able to absorb anything the kernel could explain.
```

First line is exactly one of `CORRECT`, `PARTIAL`, `INCORRECT`. Below it, 2-4
sentences: what the answer got right, what it missed, and - the part that
teaches something - connect the gap back to the mechanism rather than just
naming it missing. No numeric score; a percentage on an open-ended answer is
false precision the reader can't act on.

### Which kind to use

A quiz is 3-6 questions. Write them so they still make sense read cold in three
weeks — they are the seed for spaced repetition. Never quiz on numbers or author
names. Wrong options must be real misconceptions or a right answer to a
different question; never filler.

## Feed triage

For "what's new", run `feed`, then rank — do **not** dump the listing. Rank by:
relevance to the user's active work (time-delay cosmography, nested sampling,
repartitioning, GPs), whether it cites or builds on something already in the
cache, and genuine novelty. Explicitly deprioritise near-duplicates of papers
already read; a filter bubble is the main failure mode here.

Output at most 8 items, each one line of *why they'd care*, grouped by
"read this", "aware of", and a one-line note of what the rest were about.
Volume differs sharply by field: astro-ph.CO is small enough to scan, whereas
cs.CL/cs.LG need aggressive filtering.

## Domain notes

**Cosmology** — build up survey knowledge as you go. When a paper leans on a
survey (Rubin/LSST, DESI, Euclid, SDSS, ACT, HSC, TDCOSMO/H0LiCOW), cover in the
glossary: what it measures, the instrument and cadence, data-release status, and
the systematic that dominates its error budget. That is the accumulating asset.

**LLM research** — anchor on benchmarks, datasets and methods. Be sceptical of
headline numbers: check the baseline, the eval set, and whether the comparison is
compute-matched. Much of this literature is un-reviewed; weight evidence, not venue.

## Notes

- The reading window is self-contained: quizzes, summaries and notes all render
  in the page. Do not route any of it through latex-panel or the terminal.
- Only write into the Obsidian vault when explicitly asked.
- `ls ~/.local/share/paper-digest/cache/` is the list of papers read so far;
  each holds `fulltext.txt`, `figures/`, `session.md` (the reading transcript)
  and `workspace.json` (folds, quizzes, notes).
