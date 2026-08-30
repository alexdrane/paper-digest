#!/usr/bin/env python3
"""File bridge between the reading window and a Claude Code window.

The viewer never calls an LLM itself. It drops requests here; a Claude session
that has the paper open picks them up and writes answers back. That keeps the
work on the interactive session (with the whole paper in context) instead of
spawning separately-billed `claude -p` subprocesses.

    bridge.py list                 pending requests, oldest first
    bridge.py show <job>           the full request
    bridge.py reply <job> [file]   answer from a file, or stdin
    bridge.py wait [--timeout N]   block until a request arrives, then print it
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
    s = sub.add_parser("show"); s.add_argument("job"); s.set_defaults(func=cmd_show)
    r = sub.add_parser("reply"); r.add_argument("job")
    r.add_argument("file", nargs="?"); r.set_defaults(func=cmd_reply)
    w = sub.add_parser("wait"); w.add_argument("--timeout", type=int, default=300)
    w.set_defaults(func=cmd_wait)
    g = sub.add_parser("log"); g.add_argument("arxiv_id"); g.set_defaults(func=cmd_log)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
