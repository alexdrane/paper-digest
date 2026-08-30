#!/usr/bin/env python3
"""File bridge between the reading window and a Claude Code window.

The viewer never calls an LLM itself. It drops requests here; a Claude session
that has the paper open picks them up and writes answers back. That keeps the
work on the interactive session (with the whole paper in context) instead of
spawning separately-billed `claude -p` subprocesses.

    bridge.py list                 pending requests, oldest first
    bridge.py papers               every cached paper: fetched when, read?, flags, cards
    bridge.py show <job>           the full request
    bridge.py reply <job> [file]   answer from a file, or stdin
    bridge.py wait [--timeout N]   block until a request arrives, then print it
    bridge.py blocks <id> [term]   list a cached paper's blocks (id | section | raw)
    bridge.py saved                papers saved for later, with provenance
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / ".local/share/paper-digest/bridge"
QUEUE = ROOT / "queue"
ANSWERS = ROOT / "answers"
DONE = ROOT / "done"


def setup() -> None:
    for d in (QUEUE, ANSWERS, DONE):
        d.mkdir(parents=True, exist_ok=True)


def pending() -> list[Path]:
    setup()
    return sorted(QUEUE.glob("*.json"), key=lambda p: p.stat().st_mtime)


def describe(p: Path) -> str:
    r = json.loads(p.read_text())
    out = [f"job:      {r['job']}",
           f"paper:    {r.get('title','?')} (arXiv:{r.get('arxiv_id','?')})",
           f"kind:     {r.get('kind','question')}",
           f"section:  {r.get('section') or '-'}"]
    if r.get("sections"):
        out.append("sections: " + ", ".join(r["sections"]))
    out.append(f"fulltext: {r.get('text_path','?')}")
    if r.get("selection"):
        out += ["", "highlighted passage:", "---", r["selection"], "---"]
    if r.get("refs"):
        out += ["", "works cited in that passage:"]
        out += [f"  [{k}] {v}" for k, v in r["refs"].items()]
    out += ["", f"request: {r['question']}"]
    return "\n".join(out)


def cmd_list(args) -> None:
    ps = pending()
    if not ps:
        print("no pending requests")
        return
    for p in ps:
        r = json.loads(p.read_text())
        when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S")
        q = r["question"].replace("\n", " ")
        print(f"{r['job'][:8]}  {when}  [{r.get('kind','question')}]  "
              f"{r.get('section') or '-'}  |  {q[:70]}")


def resolve(job: str) -> Path:
    hits = [p for p in pending() if p.stem.startswith(job)]
    if not hits:
        sys.exit(f"no pending request matching {job!r}")
    if len(hits) > 1:
        sys.exit(f"ambiguous: {', '.join(p.stem[:8] for p in hits)}")
    return hits[0]


def cmd_show(args) -> None:
    print(describe(resolve(args.job)))


def transcript(arxiv_id: str) -> Path:
    d = Path.home() / ".local/share/paper-digest/cache" / arxiv_id.replace("/", "_")
    d.mkdir(parents=True, exist_ok=True)
    return d / "session.md"


def cmd_reply(args) -> None:
    p = resolve(args.job)
    text = Path(args.file).read_text() if args.file else sys.stdin.read()
    if not text.strip():
        sys.exit("refusing to write an empty answer")
    setup()
    (ANSWERS / f"{p.stem}.md").write_text(text)

    r = json.loads(p.read_text())
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = [f"\n## {stamp} · {r.get('kind','question')}"]
    if r.get("sections"):
        entry.append(f"*sections: {', '.join(r['sections'])}*")
    elif r.get("section"):
        entry.append(f"*section: {r['section']}*")
    if r.get("selection"):
        entry.append("\n> " + r["selection"].replace("\n", "\n> "))
    entry += [f"\n**{r['question']}**", "", text.rstrip(), ""]
    with transcript(r.get("arxiv_id", "unknown")).open("a") as fh:
        fh.write("\n".join(entry) + "\n")

    p.rename(DONE / p.name)
    print(f"answered {p.stem[:8]}")


def cmd_wait(args) -> None:
    """Return the oldest pending request at once; block only on an empty queue."""
    setup()
    deadline = time.time() + args.timeout
    while True:
        for p in pending():
            r = json.loads(p.read_text())
            if r.get("kind") == "end":
                p.rename(DONE / p.name)
                print("READING SESSION ENDED by the reader.\n"
                      f"Run: bridge.py log {r.get('arxiv_id','')}")
                return
            print(describe(p))
            return
        if time.time() >= deadline:
            print("no new request")
            return
        time.sleep(1.0)


def flag_files(arxiv_id: str | None):
    root = Path.home() / ".local/share/paper-digest/cache"
    rows = []
    for d in root.glob("*/flags"):
        for f in d.glob("*.json"):
            rows.append((f, json.loads(f.read_text())))
    rows.sort(key=lambda x: x[1].get("created", 0), reverse=True)
    if arxiv_id:
        rows = [x for x in rows if x[1].get("arxiv_id") == arxiv_id]
    return rows


def cmd_flags(args) -> None:
    """Broken-rendering reports saved from the reading window, newest first.
    Local-only, always - a browser click never touches GitHub. --file-issues
    opts in to filing them as issues, using *your own* `gh` session on *this*
    machine, one at a time with a confirmation - never automatic."""
    rows = flag_files(args.arxiv_id)
    if not rows:
        print("no flags")
        return
    if not args.file_issues:
        for _, r in rows:
            when = datetime.fromtimestamp(r["created"]).strftime("%Y-%m-%d %H:%M")
            print(f"{r['id']}  {when}  {r.get('arxiv_id','?')}  [{r.get('section') or '-'}]"
                  + ("  (filed)" if r.get("issue_url") else ""))
            if r.get("note"):
                print(f"    note: {r['note']}")
            print(f"    raw:  {r.get('raw','')[:140].replace(chr(10),' ')}")
        return

    import shutil
    import subprocess
    if shutil.which("gh") is None:
        sys.exit("gh CLI not found - install it to file issues, or drop --file-issues "
                 "to just review flags locally")
    for f, r in rows:
        if r.get("issue_url"):
            continue
        where = r.get("section") or r.get("block_id") or "unknown location"
        print(f"\n{r['id']}  {r.get('arxiv_id')}  [{where}]")
        if r.get("note"):
            print(f"  note: {r['note']}")
        print(f"  raw:  {r.get('raw','')[:200].replace(chr(10),' ')}")
        ans = input("  file as a GitHub issue on alexdrane/paper-digest? [y/N/q] ").strip().lower()
        if ans == "q":
            break
        if ans != "y":
            continue
        title = f"[{r.get('arxiv_id')}] broken render: {where}"
        body = (f"**Section:** {r.get('section') or '-'}\n\n"
                + (f"**Note:** {r['note']}\n\n" if r.get("note") else "")
                + (f"**Raw LaTeX:**\n```latex\n{r.get('raw','')[:3000]}\n```\n\n" if r.get("raw") else "")
                + f"*Flag `{r['id']}`, filed from bridge.py flags --file-issues.*")
        res = subprocess.run(["gh", "issue", "create", "--repo", "alexdrane/paper-digest",
                              "--title", title, "--body", body], capture_output=True, text=True)
        if res.returncode == 0:
            url = res.stdout.strip().splitlines()[-1]
            print(f"  filed: {url}")
            r["issue_url"] = url
            f.write_text(json.dumps(r, indent=2))
        else:
            print(f"  failed: {res.stderr.strip() or 'unknown gh error'}")


def cmd_papers(args) -> None:
    """Every paper in the local cache: what's been fetched, and what was done
    with it. Read-only - just walks ~/.local/share/paper-digest/cache/*/."""
    root = Path.home() / ".local/share/paper-digest/cache"
    dirs = sorted(d for d in root.glob("*/") if (d / "meta.json").exists())
    if not dirs:
        print("no papers cached")
        return
    for d in dirs:
        meta = json.loads((d / "meta.json").read_text())
        arxiv_id = meta.get("id", d.name.replace("_", "/"))
        title = meta.get("title", "?").replace("\n", " ")
        fetched = datetime.fromtimestamp(
            (d / "meta.json").stat().st_mtime).strftime("%Y-%m-%d %H:%M")

        sess = d / "session.md"
        read = sess.exists() and sess.read_text().strip() != ""

        n_flags = len(list((d / "flags").glob("*.json"))) if (d / "flags").is_dir() else 0

        cards: dict[str, int] = {}
        ws = d / "workspace.json"
        if ws.exists():
            st = json.loads(ws.read_text())
            for ins in st.get("inserts", []):
                cards[ins.get("kind", "?")] = cards.get(ins.get("kind", "?"), 0) + 1

        print(f"{arxiv_id}  {title[:66]}")
        bits = [f"fetched {fetched}",
                "read/discussed" if read else "fetched only"]
        if n_flags:
            bits.append(f"{n_flags} flag" + ("s" if n_flags != 1 else ""))
        if cards:
            bits.append(", ".join(f"{v} {k}" for k, v in sorted(cards.items())))
        print("    " + "  |  ".join(bits))


def cmd_saved(args) -> None:
    """Papers deliberately saved for later from the reading window, newest
    first. `via` shows which paper was open when this one was saved - a saved
    list read as a citation trail. Read-only; reads saved.json."""
    f = Path.home() / ".local/share/paper-digest/saved.json"
    try:
        items = json.loads(f.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        items = []
    if not items:
        print("no saved papers")
        return
    for s in sorted(items, key=lambda x: x.get("saved_at", 0), reverse=True):
        when = datetime.fromtimestamp(s.get("saved_at", 0)).strftime("%Y-%m-%d %H:%M")
        title = (s.get("title") or "?").replace("\n", " ")
        print(f"{s.get('arxiv_id','?')}  {title[:66]}")
        bits = [f"saved {when}"]
        if s.get("via"):
            bits.append(f"via arXiv:{s['via']}")
        print("    " + "  |  ".join(bits))


def cmd_blocks(args) -> None:
    """Render a cached paper's fulltext and list its blocks so an answering
    session can cite one by id with a `[[bNN]]` marker (post-processed in the
    reading window into a hover-source chip). Optional `term` filters blocks
    whose source text or section contains it (case-insensitive)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import texhtml

    d = Path.home() / ".local/share/paper-digest/cache" / args.arxiv_id.replace("/", "_")
    tex = d / "fulltext.txt"
    if not tex.exists():
        sys.exit(f"no cached fulltext for {args.arxiv_id!r} - run arxiv.py fetch first")
    figdir = str(d / "figures") if (d / "figures").is_dir() else None
    blocks = texhtml.render(tex.read_text(), figdir)["blocks"]

    term = (args.term or "").lower()
    shown = 0
    for b in blocks:
        raw = " ".join((b.get("raw") or "").split())
        sec = b.get("section", "-")
        if term and term not in raw.lower() and term not in sec.lower():
            continue
        shown += 1
        print(f"{b['id']:>5} | {sec[:45]:45} | {raw[:100]}")
    if not shown:
        print(f"no blocks matching {args.term!r}" if term else "no blocks")


def cmd_log(args) -> None:
    """Everything that happened while reading, for picking the work back up."""
    d = Path.home() / ".local/share/paper-digest/cache" / args.arxiv_id.replace("/", "_")
    t = d / "session.md"
    if t.exists():
        print(t.read_text())
    else:
        print("no questions were asked in this reading session")
    ws = d / "workspace.json"
    if ws.exists():
        st = json.loads(ws.read_text())
        notes = [i for i in st.get("inserts", []) if i.get("kind") == "note" and i.get("raw")]
        if notes:
            print("\n# Reader's own notes\n")
            for n in notes:
                print(f"- ({', '.join(n.get('sections') or [])}) {n['raw'].strip()}")
        folded = st.get("folded") or []
        if folded:
            print(f"\n*folded away while reading: {len(folded)} section(s)*")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("papers").set_defaults(func=cmd_papers)
    sub.add_parser("saved").set_defaults(func=cmd_saved)
    s = sub.add_parser("show"); s.add_argument("job"); s.set_defaults(func=cmd_show)
    r = sub.add_parser("reply"); r.add_argument("job")
    r.add_argument("file", nargs="?"); r.set_defaults(func=cmd_reply)
    w = sub.add_parser("wait"); w.add_argument("--timeout", type=int, default=300)
    w.set_defaults(func=cmd_wait)
    g = sub.add_parser("log"); g.add_argument("arxiv_id"); g.set_defaults(func=cmd_log)
    bl = sub.add_parser("blocks"); bl.add_argument("arxiv_id")
    bl.add_argument("term", nargs="?"); bl.set_defaults(func=cmd_blocks)
    fl = sub.add_parser("flags"); fl.add_argument("arxiv_id", nargs="?")
    fl.add_argument("--file-issues", action="store_true",
                    help="opt in to filing unfiled flags as GitHub issues, one at a "
                         "time with a y/N prompt, using your own gh session")
    fl.set_defaults(func=cmd_flags)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
