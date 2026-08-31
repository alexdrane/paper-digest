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
import re
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
REFERENCES = Path.home() / ".local/share/paper-digest/references.bib"
OPEN_PAPERS = Path.home() / ".local/share/paper-digest/open_papers.json"
CITATION_EDGES = Path.home() / ".local/share/paper-digest/citation_edges.json"
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


# --------------------------------------------------------------- citation edges
# Every time a paper is opened by following one of its citations, record the
# edge citing -> cited. open_papers.json is just the node set; this is what
# makes it a traversable graph ("this paper led me to that one, via §X").

def load_edges() -> list[dict]:
    try:
        data = json.loads(CITATION_EDGES.read_text())
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_edge(src: str, dst: str, section: str, keys: list) -> None:
    """One edge per ordered (citing, cited) pair; a repeat click just unions
    the bib keys and keeps the original section and opened_at."""
    if not src or not dst or src == dst:
        return
    edges = load_edges()
    for e in edges:
        if e.get("from") == src and e.get("to") == dst:
            merged = sorted(set(e.get("keys") or []) | set(keys or []))
            if merged != e.get("keys"):
                e["keys"] = merged
                CITATION_EDGES.write_text(json.dumps(edges, indent=2))
            return
    edges.append({"from": src, "to": dst, "section": section or "",
                  "keys": sorted(set(keys or [])), "opened_at": time.time()})
    CITATION_EDGES.parent.mkdir(parents=True, exist_ok=True)
    CITATION_EDGES.write_text(json.dumps(edges, indent=2))


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

def _norm_words(s: str) -> str:
    return " ".join("".join(c.lower() for c in s if c.isalnum() or c.isspace()).split())


def resolve_from_cache(title: str) -> dict | None:
    """A citation whose title matches a paper already in the local fetch cache
    resolves for free: no arXiv round-trip, and none of the arXiv-search
    false-miss / title-collision failure modes. Same similarity threshold as
    the network path."""
    want = _norm_words(title)
    best, score = None, 0.0
    for meta_path in CACHE.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not meta.get("title") or not meta.get("id"):
            continue
        r = difflib.SequenceMatcher(None, want, _norm_words(meta["title"])).ratio()
        if r > score:
            best, score = meta, r
    if best and score >= 0.72:
        return {"arxiv_id": best["id"], "title": best["title"],
                "authors": best.get("authors", []),
                "year": (best.get("published", "") or "")[:4],
                "confidence": round(score, 2), "source": "cache"}
    return None


def resolve_title(title: str) -> dict | None:
    """Resolve a citation's title to an arXiv id: local fetch cache first, then
    an arXiv API title search. Accept only a confident match.

    Citations are frequently books, websites, or pre-arXiv papers with no arXiv
    id at all - returning nothing for those is the correct, common outcome.
    """
    title = title.strip()
    if len(title) < 8:
        return None
    local = resolve_from_cache(title)
    if local:
        return local
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
        return {"arxiv_id": best["id"], "title": best["title"],
                "authors": best.get("authors", []),
                "year": (best.get("published", "") or "")[:4],
                "confidence": round(score, 2), "source": "arxiv"}
    return None


# ------------------------------------------------------------- references.bib
# A real, appendable BibTeX file the reader can point their own paper's
# \bibliography{} at. Every "save reference" click appends one entry, built
# either from resolved arXiv metadata or - for a citation that never resolves
# (books, journal-only, pre-arXiv) - from the structured fields texhtml.py
# recovered from the citing paper's typeset bibliography. Deduped by title.

_BIB_KEY = re.compile(r"@\w+\{\s*([^,\s]+)\s*,")
_BIB_TITLE = re.compile(r"^\s*title\s*=\s*[{\"](.+?)[}\"]\s*,?\s*$", re.I | re.M)


def _norm_title(t: str) -> str:
    return "".join(c.lower() for c in t if c.isalnum())


def read_references() -> tuple[dict, set]:
    """-> ({normalised title: existing key}, {all existing keys})."""
    if not REFERENCES.exists():
        return {}, set()
    text = REFERENCES.read_text()
    keys = set(_BIB_KEY.findall(text))
    titles = {}
    for block in re.split(r"(?=@\w+\{)", text):
        km, tm = _BIB_KEY.search(block), _BIB_TITLE.search(block)
        if km and tm:
            titles[_norm_title(tm.group(1))] = km.group(1)
    return titles, keys


def _surname(author: str) -> str:
    first = re.split(r"\s+and\s+", author.strip())[0].strip()
    if "," in first:
        return first.split(",")[0].strip()
    parts = first.split()
    return parts[-1] if parts else first


def _mint_key(base: str, used: set) -> str:
    base = re.sub(r"[^a-z0-9]", "", base.lower()) or "ref"
    if base not in used:
        return base
    for suffix in "abcdefghijklmnopqrstuvwxyz":
        if base + suffix not in used:
            return base + suffix
    n = 2
    while f"{base}{n}" in used:
        n += 1
    return f"{base}{n}"


def _bibtex(key: str, entry_type: str, fields: dict) -> str:
    lines = [f"@{entry_type}{{{key},"]
    for name, value in fields.items():
        value = re.sub(r"\s+", " ", str(value or "")).strip().replace("{", "").replace("}", "")
        if value:
            lines.append(f"  {name} = {{{value}}},")
    lines.append("}\n")
    return "\n".join(lines)


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
    body = request.get_json(force=True) or {}
    aid = (body.get("id") or "").strip()
    if not aid:
        return jsonify({"error": "missing id"}), 400
    if aid not in LIB:
        try:
            load(aid)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 502
    src = (body.get("from_id") or "").strip()
    if src:
        add_edge(src, aid, (body.get("section") or "").strip(), body.get("keys") or [])
    return jsonify({**LIB[aid], "saved": is_saved(aid)})


@app.get("/citation-graph")
def citation_graph():
    edges = load_edges()
    ids = {i for i in load_open_ids() if i}
    for e in edges:
        ids.update(x for x in (e.get("from"), e.get("to")) if x)
    nodes = [{"id": i, "title": known_title(i) or i, "saved": is_saved(i),
              "start": i == START_ID, "loaded": i in LIB} for i in sorted(ids)]
    return jsonify({"start": START_ID, "nodes": nodes, "edges": edges})


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


@app.get("/references")
def references_list():
    titles, keys = read_references()
    return jsonify({"path": str(REFERENCES), "count": len(keys),
                    "keys": sorted(keys)})


@app.post("/savebib")
def savebib():
    """Append one BibTeX entry for a cited work to references.bib. Works whether
    or not the citation resolved on arXiv - the client passes the resolved match
    when it has one, otherwise we reconstruct from the citing paper's fields."""
    data = request.get_json(force=True) or {}
    doc = get_doc(data.get("from_id"))
    if doc is None:
        return jsonify({"error": "unknown source paper"}), 404
    ckey = (data.get("key") or "").strip()
    if not ckey:
        return jsonify({"error": "missing key"}), 400

    fields = (doc.get("bib_fields") or {}).get(ckey, {}) or {}
    title = (doc.get("bib_titles") or {}).get(ckey, "") or fields.get("title", "")
    display = (doc.get("bib") or {}).get(ckey, ckey)
    match = data.get("match") or None

    existing_titles, used_keys = read_references()
    for cand in (title, (match or {}).get("title", "")):
        nt = _norm_title(cand)
        if nt and nt in existing_titles:
            return jsonify({"ok": True, "already": True, "key": existing_titles[nt]})

    if match and match.get("arxiv_id"):
        aid = match["arxiv_id"]
        authors = match.get("authors") or []
        author = " and ".join(authors) if authors else fields.get("author", "")
        year = str(match.get("year") or fields.get("year") or "")
        entry_type = "article"
        out_fields = {
            "author": author,
            "title": match.get("title") or title,
            "journal": f"arXiv preprint arXiv:{aid}",
            "year": year,
            "eprint": aid,
            "archivePrefix": "arXiv",
        }
        base = (_surname(author) if author else aid.replace("/", "")) + year
    elif fields.get("author") or fields.get("title"):
        entry_type = "article" if fields.get("journal") else "misc"
        out_fields = {
            "author": fields.get("author", ""),
            "title": fields.get("title", "") or title,
            "journal": fields.get("journal", ""),
            "volume": fields.get("volume", ""),
            "pages": fields.get("pages", ""),
            "year": fields.get("year", ""),
        }
        base = (_surname(fields["author"]) if fields.get("author") else "ref") + fields.get("year", "")
    else:
        entry_type = "misc"
        note = re.sub(r"\s+", " ", fields.get("note") or display or ckey).strip()
        out_fields = {"title": note,
                      "howpublished": "Reconstructed from a typeset bibliography; no arXiv match"}
        ym = re.search(r"\b(19|20)\d{2}\b", note)
        nm = re.match(r"([A-Z][A-Za-z'-]+)", note)
        base = (nm.group(1) if nm else "ref") + (ym.group(0) if ym else "")

    key = _mint_key(base, used_keys)
    entry = _bibtex(key, entry_type, out_fields)
    REFERENCES.parent.mkdir(parents=True, exist_ok=True)
    sep = "\n" if REFERENCES.exists() and REFERENCES.stat().st_size else ""
    with REFERENCES.open("a") as fh:
        fh.write(sep + entry)
    return jsonify({"ok": True, "key": key, "path": str(REFERENCES),
                    "resolved": bool(match and match.get("arxiv_id"))})


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
