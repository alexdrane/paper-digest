#!/usr/bin/env python3
"""arXiv access layer for the paper-digest skill.

Prefers LaTeX source over PDF extraction: real section structure, \\cite keys and
equations instead of two-column soup. Falls back to PyMuPDF text when a paper has
no usable source (withdrawn, PDF-only submissions, scanned old papers).

Subcommands:
  fetch <id|url> [--pdf] [--refresh]    metadata + full text -> cache, prints JSON
  search <query> [-n N]                 arXiv API search, prints JSON
  feed <cats> [--days N] [-n N]         recent submissions in categories
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

CACHE = Path.home() / ".local/share/paper-digest/cache"
API = "http://export.arxiv.org/api/query"
UA = "paper-digest/0.1 (personal research reading tool)"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".pdf", ".eps", ".gif")
ATOM = "{http://www.w3.org/2005/Atom}"
ARX = "{http://arxiv.org/schemas/atom}"

_last_call = 0.0


def polite_get(url: str, timeout: int = 60) -> bytes:
    """arXiv asks for >=3s between programmatic requests."""
    global _last_call
    wait = 3.0 - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    finally:
        _last_call = time.monotonic()
    return data


def normalize_id(s: str) -> str:
    """Accept bare ids, arXiv:..., and abs/pdf/e-print URLs. Keeps version if given."""
    s = s.strip().rstrip("/")
    m = re.search(r"arxiv\.org/(?:abs|pdf|e-print)/(.+?)(?:\.pdf)?$", s, re.I)
    if m:
        s = m.group(1)
    return re.sub(r"^arxiv:", "", s, flags=re.I).strip()


def cache_dir(aid: str) -> Path:
    return CACHE / aid.replace("/", "_")


# --------------------------------------------------------------------------- meta

def parse_entry(e: ET.Element) -> dict:
    def txt(tag: str) -> str:
        n = e.find(ATOM + tag)
        return " ".join(n.text.split()) if n is not None and n.text else ""

    raw_id = txt("id")
    aid = normalize_id(raw_id)
    prim = e.find(ARX + "primary_category")
    doi = e.find(ARX + "doi")
    comment = e.find(ARX + "comment")
    jref = e.find(ARX + "journal_ref")
    return {
        "id": re.sub(r"v\d+$", "", aid),
        "version_id": aid,
        "title": txt("title"),
        "abstract": txt("summary"),
        "authors": [
            " ".join(a.find(ATOM + "name").text.split())
            for a in e.findall(ATOM + "author")
            if a.find(ATOM + "name") is not None
        ],
        "published": txt("published"),
        "updated": txt("updated"),
        "primary_category": prim.get("term") if prim is not None else "",
        "categories": [c.get("term") for c in e.findall(ATOM + "category")],
        "doi": doi.text.strip() if doi is not None and doi.text else "",
        "journal_ref": jref.text.strip() if jref is not None and jref.text else "",
        "comment": " ".join(comment.text.split()) if comment is not None and comment.text else "",
        "abs_url": f"https://arxiv.org/abs/{aid}",
    }


def api_query(params: dict) -> list[dict]:
    url = API + "?" + urllib.parse.urlencode(params)
    root = ET.fromstring(polite_get(url))
    return [parse_entry(e) for e in root.findall(ATOM + "entry")]


def fetch_meta(aid: str) -> dict:
    hits = api_query({"id_list": aid, "max_results": 1})
    if not hits:
        raise SystemExit(f"no arXiv entry for {aid!r}")
    return hits[0]


# --------------------------------------------------------------------- latex source

def strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*$", "", tex, flags=re.MULTILINE)


def pick_main(texs: dict[str, str]) -> str | None:
    docs = [n for n, t in texs.items() if "\\documentclass" in t]
    pool = docs or list(texs)
    return max(pool, key=lambda n: len(texs[n])) if pool else None


def inline_inputs(name: str, texs: dict[str, str], seen: set[str] | None = None) -> str:
    """Resolve \\input / \\include one level at a time, guarding against cycles."""
    seen = seen or set()
    if name in seen:
        return ""
    seen.add(name)
    body = texs.get(name, "")

    def sub(m: re.Match) -> str:
        target = m.group(1).strip()
        for cand in (target, target + ".tex", target.lstrip("./"), target.lstrip("./") + ".tex"):
            if cand in texs:
                return inline_inputs(cand, texs, seen)
        return m.group(0)

    return re.sub(r"\\(?:input|include)\{([^}]+)\}", sub, body)


def fetch_source_text(aid: str, assets_dir: Path | None = None) -> str | None:
    """Download the e-print tarball and reassemble the main .tex."""
    try:
        blob = polite_get(f"https://arxiv.org/e-print/{aid}")
    except Exception as exc:
        print(f"[source unavailable: {exc}]", file=sys.stderr)
        return None
    if not blob:
        return None

    texs: dict[str, str] = {}
    bbl: list[str] = []
    try:
        with tarfile.open(fileobj=BytesIO(blob), mode="r:*") as tf:
            for m in tf.getmembers():
                if not m.isfile() or m.size > 8_000_000:
                    continue
                low = m.name.lower()
                fh = tf.extractfile(m)
                if fh is None:
                    continue
                if low.endswith(IMAGE_EXT):
                    if assets_dir is not None:
                        dest = assets_dir / Path(m.name).name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(fh.read())
                    continue
                if not low.endswith((".tex", ".bbl")):
                    continue
                content = fh.read().decode("utf-8", "replace")
                if low.endswith(".bbl"):
                    bbl.append(content)
                else:
                    texs[m.name] = content
    except tarfile.ReadError:
        # single gzipped .tex, not a tarball
        try:
            texs["main.tex"] = gzip.decompress(blob).decode("utf-8", "replace")
        except Exception:
            return None

    if not texs:
        return None
    main = pick_main(texs)
    if main is None:
        return None
    out = strip_comments(inline_inputs(main, texs))
    if bbl:
        out += "\n\n% ---- bibliography (.bbl) ----\n" + strip_comments("\n".join(bbl))
    return out


def fetch_pdf_text(aid: str) -> str | None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[PyMuPDF not installed; cannot fall back to PDF]", file=sys.stderr)
        return None
    try:
        blob = polite_get(f"https://arxiv.org/pdf/{aid}")
        doc = fitz.open(stream=blob, filetype="pdf")
    except Exception as exc:
        print(f"[pdf unavailable: {exc}]", file=sys.stderr)
        return None
    return "\n\n".join(
        f"--- page {i + 1} ---\n{p.get_text()}" for i, p in enumerate(doc)
    )


# ------------------------------------------------------------------------ commands

def cmd_fetch(args) -> None:
    aid = normalize_id(args.id)
    d = cache_dir(aid)
    meta_p, text_p = d / "meta.json", d / "fulltext.txt"

    if meta_p.exists() and text_p.exists() and not args.refresh:
        meta = json.loads(meta_p.read_text())
        source = meta.get("text_source", "cache")
    else:
        meta = fetch_meta(aid)
        d.mkdir(parents=True, exist_ok=True)
        text = None if args.pdf else fetch_source_text(aid, d / "figures")
        source = "latex"
        if not text or len(text) < 500:
            text, source = fetch_pdf_text(aid), "pdf"
        if not text:
            raise SystemExit(f"could not retrieve text for {aid}")
        d.mkdir(parents=True, exist_ok=True)
        text_p.write_text(text)
        meta["text_source"] = source
        meta_p.write_text(json.dumps(meta, indent=2))

    print(json.dumps({
        "id": meta["id"],
        "title": meta["title"],
        "authors": meta["authors"],
        "published": meta["published"],
        "categories": meta["categories"],
        "abstract": meta["abstract"],
        "abs_url": meta["abs_url"],
        "text_source": source,
        "text_path": str(text_p),
        "chars": text_p.stat().st_size,
    }, indent=2))


def cmd_search(args) -> None:
    hits = api_query({
        "search_query": args.query,
        "start": 0,
        "max_results": args.n,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    print(json.dumps(hits, indent=2))


def cmd_feed(args) -> None:
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    window = f"[{since:%Y%m%d}0000 TO {datetime.now(timezone.utc):%Y%m%d}2359]"
    cats = " OR ".join(f"cat:{c.strip()}" for c in args.cats.split(","))
    hits = api_query({
        "search_query": f"({cats}) AND submittedDate:{window}",
        "start": 0,
        "max_results": args.n,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    print(json.dumps(hits, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="metadata + full text into the cache")
    f.add_argument("id")
    f.add_argument("--pdf", action="store_true", help="skip LaTeX source, use PDF text")
    f.add_argument("--refresh", action="store_true", help="ignore cached copy")
    f.set_defaults(func=cmd_fetch)

    s = sub.add_parser("search", help="arXiv API search")
    s.add_argument("query", help='e.g. "all:time delay cosmography AND cat:astro-ph.CO"')
    s.add_argument("-n", type=int, default=15)
    s.set_defaults(func=cmd_search)

    d = sub.add_parser("feed", help="recent submissions by category")
    d.add_argument("cats", help="comma-separated, e.g. astro-ph.CO,cs.CL")
    d.add_argument("--days", type=int, default=2)
    d.add_argument("-n", type=int, default=60)
    d.set_defaults(func=cmd_feed)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
