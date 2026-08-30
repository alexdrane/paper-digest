#!/usr/bin/env python3
"""Reading window: rendered paper on the left, Claude on the right.

Selecting text asks a question about that passage. The selection is sent with the
section path it came from and the resolved bibliography entries for any citations
inside it - context a PDF highlight cannot carry.

    python3 viewer.py 2602.11264
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, stream_with_context

sys.path.insert(0, str(Path(__file__).parent))
import texhtml  # noqa: E402

CACHE = Path.home() / ".local/share/paper-digest/cache"
app = Flask(__name__)

PAPER: dict = {}
FIGDIR: Path | None = None
WORKDIR: Path | None = None


def load(aid: str) -> dict:
    d = CACHE / aid.replace("/", "_")
    if not (d / "fulltext.txt").exists():
        script = Path(__file__).parent / "arxiv.py"
        print(f"fetching {aid} ...")
        subprocess.run([sys.executable, str(script), "fetch", aid], check=True,
                       stdout=subprocess.DEVNULL)
    meta = json.loads((d / "meta.json").read_text())
    doc = texhtml.render((d / "fulltext.txt").read_text(), "figures")
    doc["arxiv_id"] = meta["id"]
    doc["abs_url"] = meta["abs_url"]
    doc["source"] = meta.get("text_source", "?")
    doc["text_path"] = str(d / "fulltext.txt")
    if not doc["title"]:
        doc["title"] = meta["title"]
    if not doc["authors"]:
        doc["authors"] = meta["authors"]
    if not doc["abstract"]:
        doc["abstract"] = meta["abstract"]
    globals()["FIGDIR"] = d / "figures"
    globals()["WORKDIR"] = d
    return doc


# ------------------------------------------------------------------------- bridge

BRIDGE = Path.home() / ".local/share/paper-digest/bridge"


def enqueue(kind: str, question: str, selection: str, section: str, refs: dict,
            sections: list | None = None) -> str:
    """Drop a request for the Claude window to pick up. No LLM is called here."""
    job = uuid.uuid4().hex
    (BRIDGE / "queue").mkdir(parents=True, exist_ok=True)
    (BRIDGE / "answers").mkdir(parents=True, exist_ok=True)
    (BRIDGE / "queue" / f"{job}.json").write_text(json.dumps({
        "job": job, "kind": kind, "question": question, "selection": selection,
        "section": section, "sections": sections or [], "refs": refs,
        "arxiv_id": PAPER["arxiv_id"],
        "title": PAPER["title"], "text_path": PAPER["text_path"],
        "created": time.time(),
    }, indent=2))
    return job


def await_answer(job: str, timeout: float = 1800.0):
    """Yield SSE frames while waiting for the answer file to appear."""
    path = BRIDGE / "answers" / f"{job}.json"
    md = BRIDGE / "answers" / f"{job}.md"
    deadline = time.time() + timeout
    waited = 0
    while time.time() < deadline:
        if md.exists():
            yield f"data: {json.dumps({'text': md.read_text()})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        if path.exists():
            yield f"data: {json.dumps({'text': path.read_text()})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        time.sleep(0.5)
        waited += 1
        if waited % 20 == 0:
            yield f"event: waiting\ndata: {json.dumps({'seconds': waited // 2})}\n\n"
    yield ("data: " + json.dumps({"text": "_No answer yet. Is a Claude window "
                                          "watching the bridge?_"}) + "\n\n")
    yield "event: done\ndata: {}\n\n"


# ------------------------------------------------------------------------- routes

@app.get("/")
def index():
    return send_file(Path(__file__).parent / "viewer.html")


@app.get("/paper")
def paper():
    return jsonify(PAPER)


@app.post("/flag")
def flag():
    data = request.get_json(force=True)
    d = WORKDIR / "flags"
    d.mkdir(parents=True, exist_ok=True)
    fid = uuid.uuid4().hex[:10]
    (d / f"{fid}.json").write_text(json.dumps({
        "id": fid, "arxiv_id": PAPER.get("arxiv_id"), "title": PAPER.get("title"),
        "section": data.get("section", ""), "block_id": data.get("block_id", ""),
        "raw": data.get("raw", ""), "html": data.get("html", ""),
        "note": data.get("note", "").strip(), "created": time.time(),
    }, indent=2))
    return jsonify({"ok": True, "id": fid})


@app.get("/figure/<path:name>")
def figure(name: str):
    if FIGDIR is None:
        return "", 404
    src = FIGDIR / Path(name).name
    for cand in (src, src.with_suffix(".png"), src.with_suffix(".jpg"),
                 src.with_suffix(".pdf")):
        if cand.exists() and cand.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
            return send_file(cand)
        if cand.exists() and cand.suffix.lower() == ".pdf":
            png = cand.with_suffix(".conv.png")
            if not png.exists():
                subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile",
                                str(cand), str(png.with_suffix(""))], check=False)
            if png.exists():
                return send_file(png)
    return "", 404


@app.get("/state")
def get_state():
    f = WORKDIR / "workspace.json"
    return jsonify(json.loads(f.read_text()) if f.exists() else {"inserts": [], "folded": []})


@app.post("/state")
def set_state():
    (WORKDIR / "workspace.json").write_text(json.dumps(request.get_json(force=True), indent=2))
    return jsonify({"ok": True})


@app.post("/done")
def done():
    enqueue("end", "Reading session finished.", "", "", {})
    return jsonify({"ok": True})


@app.post("/ask")
def ask():
    data = request.get_json(force=True)
    keys = data.get("cite_keys") or []
    refs = {k: PAPER["bib"][k] for k in keys if k in PAPER["bib"]}
    job = enqueue(data.get("kind", "question"),
                  data.get("question", "").strip(),
                  data.get("selection", "").strip(),
                  data.get("section", ""), refs,
                  data.get("sections") or [])
    return jsonify({"job": job})


@app.get("/pending")
def pending():
    items = []
    for f in sorted((BRIDGE / "queue").glob("*.json"), key=lambda x: x.stat().st_mtime) \
            if (BRIDGE / "queue").exists() else []:
        r = json.loads(f.read_text())
        if r.get("arxiv_id") != PAPER.get("arxiv_id"):
            continue
        items.append({"job": r["job"], "kind": r.get("kind", "question"),
                      "section": r.get("section", ""), "sections": r.get("sections", []),
                      "question": r.get("question", ""), "created": r.get("created", 0)})
    return jsonify({"pending": len(items), "items": items})


@app.post("/cancel/<job>")
def cancel(job: str):
    f = BRIDGE / "queue" / f"{job}.json"
    if f.exists():
        f.unlink()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "reason": "already answered or unknown"}), 404


@app.get("/stream/<job>")
def stream(job: str):
    return Response(stream_with_context(await_answer(job)), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def free_port(pref: int = 5177) -> int:
    for p in range(pref, pref + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: viewer.py <arxiv-id>")
    PAPER = load(sys.argv[1])
    print(f"{PAPER['title']} - {len(PAPER['blocks'])} blocks, "
          f"{len(PAPER['bib'])} refs, source={PAPER['source']}")
    port = free_port()
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    app.run(port=port, threaded=True)
