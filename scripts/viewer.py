#!/usr/bin/env python3
"""Reading window: rendered paper on the left, Claude on the right.

Selecting text asks a question about that passage. The selection is sent with the
section path it came from and the resolved bibliography entries for any citations
inside it - context a PDF highlight cannot carry.

Multiple papers can be open at once. Clicking a citation resolves it to an arXiv
id by title search and opens it alongside the current paper; a dropdown in the
sidebar switches between everything open in this session.

    python3 viewer.py 2602.11264
"""
from __future__ import annotations

import difflib
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
BRIDGE = Path.home() / ".local/share/paper-digest/bridge"
SAVED = Path.home() / ".local/share/paper-digest/saved.json"
OPEN_PAPERS = Path.home() / ".local/share/paper-digest/open_papers.json"
app = Flask(__name__)

LIB: dict[str, dict] = {}       # arxiv_id -> rendered doc
FIGDIRS: dict[str, Path] = {}   # arxiv_id -> figures/
WORKDIRS: dict[str, Path] = {}  # arxiv_id -> cache dir (workspace.json, flags/)
START_ID: str = ""              # the paper this process was launched on


def load(aid: str) -> dict:
    """Fetch (if needed), render, and register a paper in the library."""
    d = CACHE / aid.replace("/", "_")
    if not (d / "fulltext.txt").exists():
        script = Path(__file__).parent / "arxiv.py"
        print(f"fetching {aid} ...")
        subprocess.run([sys.executable, str(script), "fetch", aid], check=True,
                       stdout=subprocess.DEVNULL)
    meta = json.loads((d / "meta.json").read_text())
    doc = texhtml.render((d / "fulltext.txt").read_text(), "figures", meta["id"])
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
    LIB[doc["arxiv_id"]] = doc
    FIGDIRS[doc["arxiv_id"]] = d / "figures"
    WORKDIRS[doc["arxiv_id"]] = d
    remember_open(doc["arxiv_id"])
    return doc


def get_doc(explicit_id: str | None) -> dict | None:
    aid = explicit_id or START_ID
    return LIB.get(aid)


# ------------------------------------------------------------------- saved papers
# A "save" is a deliberate keep-for-later, persisted across restarts - distinct
# from the fetch cache (fetched once, no intent) and the in-memory LIB (open in
# this session only). `via` records which paper you were reading when you saved
# this one, so a saved list doubles as a citation-rabbit-hole trail.

def load_saved() -> list[dict]:
    try:
        data = json.loads(SAVED.read_text())
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_saved(items: list[dict]) -> None:
    SAVED.parent.mkdir(parents=True, exist_ok=True)
    SAVED.write_text(json.dumps(items, indent=2))


def is_saved(aid: str) -> bool:
    return any(s.get("arxiv_id") == aid for s in load_saved())


def known_title(aid: str) -> str:
    if aid in LIB:
        return LIB[aid]["title"]
    meta = CACHE / aid.replace("/", "_") / "meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text()).get("title", "")
        except json.JSONDecodeError:
            pass
    return ""


# -------------------------------------------------------------------- open papers
# LIB / FIGDIRS / WORKDIRS are process-local, so after a restart the server has
# forgotten every paper opened via a citation click - the switcher dropdown
# loses them and, worse, /figure 404s for them (FIGDIRS.get miss) even though
# the cache on disk is intact. Persist the id list and rehydrate on startup;
# load() is cheap when fulltext.txt is already cached.

def load_open_ids() -> list[str]:
    try:
        data = json.loads(OPEN_PAPERS.read_text())
        return [x for x in data if isinstance(x, str)] if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def remember_open(aid: str) -> None:
    ids = load_open_ids()
    if aid in ids:
        return
    ids.append(aid)
    OPEN_PAPERS.parent.mkdir(parents=True, exist_ok=True)
    OPEN_PAPERS.write_text(json.dumps(ids, indent=2))


def restore_open() -> None:
    """Re-register every previously-opened paper before the server starts."""
    for aid in load_open_ids():
        if aid in LIB:
            continue
        if not (CACHE / aid.replace("/", "_") / "fulltext.txt").exists():
            continue  # cache gone - don't trigger a network re-fetch on startup
        try:
            load(aid)
        except Exception as exc:  # a stale/corrupt cache entry shouldn't block startup
            print(f"  could not restore {aid}: {exc}")


# ------------------------------------------------------------------------- bridge

def enqueue(doc: dict, kind: str, question: str, selection: str, section: str,
            refs: dict, sections: list | None = None) -> str:
    """Drop a request for the Claude window to pick up. No LLM is called here."""
    job = uuid.uuid4().hex
    (BRIDGE / "queue").mkdir(parents=True, exist_ok=True)
    (BRIDGE / "answers").mkdir(parents=True, exist_ok=True)
    (BRIDGE / "queue" / f"{job}.json").write_text(json.dumps({
        "job": job, "kind": kind, "question": question, "selection": selection,
        "section": section, "sections": sections or [], "refs": refs,
        "arxiv_id": doc["arxiv_id"], "title": doc["title"], "text_path": doc["text_path"],
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


# ---------------------------------------------------------------- citation resolve

def resolve_title(title: str) -> dict | None:
    """Search arXiv for a citation's title; accept only a confident match.

    Citations are frequently books, websites, or pre-arXiv papers with no arXiv
    id at all - returning nothing for those is the correct, common outcome.
    """
    title = title.strip()
    if len(title) < 8:
        return None
    script = Path(__file__).parent / "arxiv.py"
    query = 'ti:"' + title.replace('"', "") + '"'
    try:
        out = subprocess.run([sys.executable, str(script), "search", query, "-n", "3"],
                             capture_output=True, text=True, timeout=30, check=True).stdout
        hits = json.loads(out)
    except Exception:
        hits = []
    if not hits:
        try:
            out = subprocess.run([sys.executable, str(script), "search", title, "-n", "3"],
                                 capture_output=True, text=True, timeout=30, check=True).stdout
            hits = json.loads(out)
        except Exception:
            return None
    best, score = None, 0.0
    norm = lambda s: "".join(c.lower() for c in s if c.isalnum() or c.isspace()).split()
    for h in hits:
        r = difflib.SequenceMatcher(None, " ".join(norm(title)), " ".join(norm(h["title"]))).ratio()
        if r > score:
            best, score = h, r
    if best and score >= 0.72:
        return {"arxiv_id": best["id"], "title": best["title"], "confidence": round(score, 2)}
    return None


# ------------------------------------------------------------------------- routes

@app.get("/")
def index():
    return send_file(Path(__file__).parent / "viewer.html")


@app.get("/paper")
def paper():
    doc = get_doc(request.args.get("id"))
    if not doc:
        return jsonify({"error": "not open"}), 404
    return jsonify({**doc, "saved": is_saved(doc["arxiv_id"])})


@app.get("/library")
def library():
    return jsonify({"start": START_ID,
                    "papers": [{"id": d["arxiv_id"], "title": d["title"],
                                "saved": is_saved(d["arxiv_id"])} for d in LIB.values()]})


@app.get("/saved")
def saved_list():
    return jsonify({"saved": load_saved()})


@app.post("/save")
def save_paper():
    data = request.get_json(force=True) or {}
    aid = (data.get("id") or "").strip()
    if not aid:
        return jsonify({"error": "missing id"}), 400
    items = load_saved()
    if any(s.get("arxiv_id") == aid for s in items):
        return jsonify({"ok": True, "saved": True, "already": True})
    via = (data.get("via") or "").strip() or None
    if via == aid:
        via = None
    items.append({"arxiv_id": aid,
                  "title": (data.get("title") or "").strip() or known_title(aid) or aid,
                  "saved_at": time.time(), "via": via})
    write_saved(items)
    return jsonify({"ok": True, "saved": True})


@app.post("/unsave")
def unsave_paper():
    aid = ((request.get_json(force=True) or {}).get("id") or "").strip()
    write_saved([s for s in load_saved() if s.get("arxiv_id") != aid])
    return jsonify({"ok": True, "saved": False})


@app.post("/open")
def open_paper():
    aid = (request.get_json(force=True) or {}).get("id", "").strip()
    if not aid:
        return jsonify({"error": "missing id"}), 400
    if aid not in LIB:
        try:
            load(aid)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 502
    return jsonify(LIB[aid])


@app.post("/resolve")
def resolve():
    data = request.get_json(force=True)
    doc = get_doc(data.get("from_id"))
    if doc is None:
        return jsonify({"error": "unknown source paper"}), 404
    titles = doc.get("bib_titles", {})
    out = {}
    for key in data.get("keys", []):
        t = titles.get(key, "")
        out[key] = {"display": doc["bib"].get(key, key), "match": resolve_title(t) if t else None}
    return jsonify(out)


@app.post("/flag")
def flag():
    # Deliberately local-only: a browser click on someone else's machine should
    # never silently invoke their authenticated `gh` to post public content on
    # their behalf. Filing to GitHub, if wanted, is a separate opt-in step a
    # person runs themselves - see bridge.py flags.
    data = request.get_json(force=True)
    doc = get_doc(data.get("id"))
    if doc is None:
        return jsonify({"error": "unknown paper"}), 404
    d = WORKDIRS[doc["arxiv_id"]] / "flags"
    d.mkdir(parents=True, exist_ok=True)
    fid = uuid.uuid4().hex[:10]
    (d / f"{fid}.json").write_text(json.dumps({
        "id": fid, "arxiv_id": doc["arxiv_id"], "title": doc["title"],
        "section": data.get("section", ""), "block_id": data.get("block_id", ""),
        "raw": data.get("raw", ""), "html": data.get("html", ""),
        "note": data.get("note", "").strip(), "created": time.time(),
    }, indent=2))
    return jsonify({"ok": True, "id": fid})


@app.get("/figure/<path:name>")
def figure(name: str):
    figdir = FIGDIRS.get(request.args.get("id") or START_ID)
    if figdir is None:
        return "", 404
    src = figdir / Path(name).name
    for cand in (src, src.with_suffix(".png"), src.with_suffix(".jpg"),
                 src.with_suffix(".pdf"), src.with_suffix(".eps"), src.with_suffix(".ps")):
        if cand.exists() and cand.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
            return send_file(cand)
        if cand.exists() and cand.suffix.lower() == ".pdf":
            png = cand.with_suffix(".conv.png")
            if not png.exists():
                subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile",
                                str(cand), str(png.with_suffix(""))], check=False)
            if png.exists():
                return send_file(png)
        if cand.exists() and cand.suffix.lower() in (".eps", ".ps"):
            # Ghostscript renders both directly; -dEPSCrop keeps an EPS's real
            # bounding box instead of an oversized/blank page around the figure.
            png = cand.with_suffix(".conv.png")
            if not png.exists():
                args = ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
                        "-sDEVICE=png16m", "-r150", f"-sOutputFile={png}"]
                if cand.suffix.lower() == ".eps":
                    args.append("-dEPSCrop")
                args.append(str(cand))
                subprocess.run(args, check=False, capture_output=True)
            if png.exists():
                return send_file(png)
    return "", 404


@app.get("/state")
def get_state():
    doc = get_doc(request.args.get("id"))
    if doc is None:
        return jsonify({"inserts": [], "folded": []})
    f = WORKDIRS[doc["arxiv_id"]] / "workspace.json"
    return jsonify(json.loads(f.read_text()) if f.exists() else {"inserts": [], "folded": []})


@app.post("/state")
def set_state():
    body = request.get_json(force=True)
    doc = get_doc(body.get("id"))
    if doc is None:
        return jsonify({"ok": False, "reason": "unknown paper"}), 404
    (WORKDIRS[doc["arxiv_id"]] / "workspace.json").write_text(json.dumps(body, indent=2))
    return jsonify({"ok": True})


@app.post("/done")
def done():
    doc = get_doc((request.get_json(force=True) or {}).get("id"))
    if doc is None:
        return jsonify({"ok": False}), 404
    enqueue(doc, "end", "Reading session finished.", "", "", {})
    return jsonify({"ok": True})


@app.post("/ask")
def ask():
    data = request.get_json(force=True)
    doc = get_doc(data.get("id"))
    if doc is None:
        return jsonify({"error": "unknown paper"}), 404
    keys = data.get("cite_keys") or []
    refs = {k: doc["bib"][k] for k in keys if k in doc["bib"]}
    job = enqueue(doc, data.get("kind", "question"),
                  data.get("question", "").strip(),
                  data.get("selection", "").strip(),
                  data.get("section", ""), refs,
                  data.get("sections") or [])
    return jsonify({"job": job})


@app.get("/pending")
def pending():
    doc = get_doc(request.args.get("id"))
    aid = doc["arxiv_id"] if doc else None
    items = []
    qdir = BRIDGE / "queue"
    for f in sorted(qdir.glob("*.json"), key=lambda x: x.stat().st_mtime) if qdir.exists() else []:
        r = json.loads(f.read_text())
        if aid is not None and r.get("arxiv_id") != aid:
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
    doc = load(sys.argv[1])
    START_ID = doc["arxiv_id"]
    print(f"{doc['title']} - {len(doc['blocks'])} blocks, "
          f"{len(doc['bib'])} refs, source={doc['source']}")
    restore_open()
    if len(LIB) > 1:
        print(f"restored {len(LIB) - 1} other paper(s) opened earlier")
    port = free_port()
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    app.run(port=port, threaded=True)
