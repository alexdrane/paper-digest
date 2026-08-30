#!/usr/bin/env python3
"""LaTeX -> structured HTML blocks for the paper viewer.

Not a LaTeX engine. It produces readable HTML while preserving the two things a
PDF loses: which section a passage belongs to, and which references it cites.
Maths is left in TeX form for MathJax; \\newcommand macros are handed over too.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

SECTION_LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}
MATH_ENVS = r"equation\*?|align\*?|gather\*?|eqnarray\*?|multline\*?|displaymath|split"
FLOAT_ENVS = r"figure\*?|table\*?"
LIST_ENVS = r"itemize|enumerate|description"

TEXT_MACROS: dict = {}

SPECIAL = re.compile(
    r"\\(?P<sec>subsubsection|subsection|section|paragraph)\*?\s*\{"
    r"|\\begin\{(?P<env>" + MATH_ENVS + "|" + FLOAT_ENVS + "|" + LIST_ENVS + r")\}"
    r"|\\(?P<app>appendix)\b"
)


# ------------------------------------------------------------------ tex utilities

def match_brace(s: str, i: int) -> int:
    """Index just past the '}' closing the '{' at position i."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def braced(s: str, i: int) -> tuple[str, int]:
    """Read a {...} group starting at i (must point at '{')."""
    end = match_brace(s, i)
    return s[i + 1:end - 1], end


def env_end(s: str, start: int, env: str) -> int:
    """Index just past \\end{env}, honouring nesting of the same environment."""
    open_re = re.compile(r"\\begin\{" + re.escape(env) + r"\}")
    close_re = re.compile(r"\\end\{" + re.escape(env) + r"\}")
    depth, i = 0, start
    while i < len(s):
        mo, mc = open_re.search(s, i), close_re.search(s, i)
        if mc is None:
            return len(s)
        if mo is not None and mo.start() < mc.start():
            depth += 1
            i = mo.end()
        else:
            depth -= 1
            i = mc.end()
            if depth == 0:
                return i
    return len(s)


def mathjax_safe(body: str) -> str:
    r"""Strip text-mode-only control sequences from a \newcommand body.

    A macro like \days -> \ensuremath{\mathrm{days}}\xspace is used in both text
    and maths. In text it flows through inline(), which drops leftover commands
    fine. In maths it is never expanded here (protect_math stashes the whole
    $...$ first) - MathJax expands it later from the macro table, and MathJax
    knows neither \ensuremath nor \xspace, so it renders them as literal text.
    Turn \ensuremath{X} into a plain {X} group and drop \xspace before the body
    reaches the table.
    """
    body = re.sub(r"\\ensuremath\s*(?=\{)", "", body)
    body = re.sub(r"\\xspace\b", "", body)
    return body


def extract_macros(preamble: str) -> dict:
    """\\newcommand definitions -> MathJax macro table."""
    macros: dict[str, object] = {}
    for m in re.finditer(r"\\(?:newcommand|renewcommand|providecommand)\s*\{?\\(\w+)\}?"
                         r"\s*(?:\[(\d+)\])?\s*(?:\[[^\]]*\])?\s*\{", preamble):
        name, nargs = m.group(1), m.group(2)
        body, _ = braced(preamble, preamble.index("{", m.end() - 1))
        body = mathjax_safe(body)
        macros[name] = [body, int(nargs)] if nargs else body
    return macros


def macro_table(preamble: str) -> dict:
    """Same definitions, as {name: (body, nargs)} for text-mode expansion."""
    out = {}
    for name, v in extract_macros(preamble).items():
        out[name] = (v[0], v[1]) if isinstance(v, list) else (v, 0)
    return out


def expand_macros(text: str, table: dict) -> str:
    """Expand user macros in text mode. Maths is left to MathJax."""
    if not table:
        return text
    pat = re.compile(r"\\([a-zA-Z]+)")
    for _ in range(4):
        out, i, changed = [], 0, False
        while True:
            m = pat.search(text, i)
            if not m:
                out.append(text[i:])
                break
            name = m.group(1)
            if name not in table:
                out.append(text[i:m.end()])
                i = m.end()
                continue
            body, nargs = table[name]
            j, args, ok = m.end(), [], True
            for _k in range(nargs):
                while j < len(text) and text[j] in " \t":
                    j += 1
                if j < len(text) and text[j] == "{":
                    a, j = braced(text, j)
                    args.append(a)
                else:
                    ok = False
                    break
            if not ok:
                out.append(text[i:m.end()])
                i = m.end()
                continue
            rep = body
            for k, a in enumerate(args, 1):
                rep = rep.replace(f"#{k}", a)
            if nargs == 0 and text[j:j + 2] == "{}":
                j += 2
            out.append(text[i:m.start()])
            out.append(rep)
            i, changed = j, True
        text = "".join(out)
        if not changed:
            break
    return text


def skip_optional(s: str, i: int) -> int:
    """Index just past the ']' closing the '[' at i, ignoring brackets inside braces."""
    depth_b = depth_c = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth_c += 1
        elif c == "}":
            depth_c -= 1
        elif depth_c == 0 and c == "[":
            depth_b += 1
        elif depth_c == 0 and c == "]":
            depth_b -= 1
            if depth_b == 0:
                return i + 1
        i += 1
    return i


def strip_tex(t: str) -> str:
    t = re.sub(r"\\[a-zA-Z@]+\s*", " ", t)
    t = re.sub(r"\\[^a-zA-Z\s]|\\\s", " ", t)
    t = t.replace("~", " ").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", t).strip(" ,.")


def format_entry(body: str) -> tuple[str, str]:
    """revtex .bbl entries are \\bibinfo field/value pairs; plain ones are not.
    Returns (display string, title alone) - the title is what citation resolution
    searches arXiv with, so it needs to travel separately from the display text."""
    fields: dict[str, str] = {}
    authors: list[str] = []
    for m in re.finditer(r"\\bibinfo\s*\{(\w+)\}\s*\{", body):
        val = strip_tex(braced(body, body.index("{", m.end() - 1))[0])
        if not val:
            continue
        if m.group(1) == "author":
            authors.append(val)
        else:
            fields.setdefault(m.group(1), val)
    if not fields and not authors:
        flat = strip_tex(body)
        return flat, flat
    who = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
    venue = " ".join(x for x in (fields.get("journal", ""), fields.get("volume", "")) if x)
    out = ", ".join(x for x in (who, fields.get("title", ""), venue, fields.get("pages", "")) if x)
    if fields.get("year"):
        out += f" ({fields['year']})"
    return out, fields.get("title", "")


def parse_bbl(bbl: str) -> tuple[dict, dict]:
    """\\bibitem entries -> ({key: readable citation}, {key: title only})."""
    out, titles = {}, {}
    for m in re.finditer(r"\\bibitem\s*", bbl):
        i = m.end()
        if i < len(bbl) and bbl[i] == "[":          # revtex label, may nest braces
            i = skip_optional(bbl, i)
            while i < len(bbl) and bbl[i].isspace():
                i += 1
        if i >= len(bbl) or bbl[i] != "{":
            continue
        key, j = braced(bbl, i)
        nxt = re.search(r"\\bibitem|\\end\{thebibliography\}", bbl[j:])
        display, title = format_entry(bbl[j: j + (nxt.start() if nxt else len(bbl))])
        key = key.strip()
        out[key] = display
        titles[key] = title
    return out, titles


# --------------------------------------------------------------------- inline pass

def protect_math(text: str, store: list) -> str:
    def keep(m: re.Match) -> str:
        store.append(m.group(0))
        return f"\x00M{len(store) - 1}\x00"

    for pat in (r"\$\$[\s\S]*?\$\$", r"\\\[[\s\S]*?\\\]", r"\\\([\s\S]*?\\\)",
                r"(?<!\\)\$(?:[^$\\]|\\.)+?\$"):
        text = re.sub(pat, keep, text)
    return text


def restore_math(text: str, store: list) -> str:
    return re.sub(r"\x00M(\d+)\x00",
                  lambda m: html.escape(store[int(m.group(1))], quote=False), text)


SIMPLE = {"textbf": "strong", "textit": "em", "emph": "em", "texttt": "code",
          "textsc": "span", "underline": "u", "textrm": "span", "mbox": "span"}


def inline(text: str) -> str:
    """LaTeX inline markup -> HTML. Maths is protected across the whole pass."""
    store: list[str] = []
    text = protect_math(text, store)
    text = expand_macros(text, TEXT_MACROS)
    text = protect_math(text, store)   # macro bodies may themselves contain maths
    text = re.sub(r"\\ensuremath\s*(?=\{)", "", text)   # \ensuremath{X} -> {X}
    text = re.sub(r"\\(?:label|index|vspace|hspace|noindent|centering|small|footnotesize)"
                  r"\s*\*?(?:\{[^{}]*\})?", "", text)
    text = html.escape(text, quote=False)

    # citations become clickable spans carrying their bib keys
    def cite(m: re.Match) -> str:
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        return (f'<span class="cite" data-keys="{html.escape(",".join(keys), quote=True)}">'
                f'[{len(keys)} ref{"s" if len(keys) > 1 else ""}]</span>')

    text = re.sub(r"\\(?:cite[a-zA-Z]*)\s*(?:\[[^\]]*\])*\{([^}]*)\}", cite, text)
    text = re.sub(r"\\(?:eq)?ref\s*\{([^}]*)\}", r'<span class="xref">\1</span>', text)
    text = re.sub(r"\\href\s*\{([^}]*)\}\s*\{([^}]*)\}", r'<a href="\1" target="_blank">\2</a>', text)
    text = re.sub(r"\\url\s*\{([^}]*)\}", r'<a href="\1" target="_blank">\1</a>', text)
    text = re.sub(r"\\footnote\s*\{", "(", text).replace("\\@", "")

    for cmd, tag in SIMPLE.items():
        text = re.sub(r"\\" + cmd + r"\s*\{([^{}]*)\}", rf"<{tag}>\1</{tag}>", text)

    text = re.sub(r"\\(?:%|&|_|#)", lambda m: m.group(0)[1], text)
    text = re.sub(r"\\xspace\b\s*", " ", text)             # keeps the space it stands for
    text = re.sub(r"\\[a-zA-Z]+\s*", "", text)          # drop leftover commands
    text = re.sub(r"\\\s|\\[,;!:]", " ", text)          # spacing control sequences
    text = text.replace("~", " ").replace("{", "").replace("}", "")
    text = re.sub(r"``(.*?)\'\'", "\u201c" + r"\1" + "\u201d", text, flags=re.S)
    text = text.replace("---", "\u2014").replace("--", "\u2013")
    text = re.sub(r"[ \t]+", " ", text)
    return restore_math(text, store).strip()


# ---------------------------------------------------------------------- block pass

def render_tabular(body: str) -> str | None:
    """booktabs/plain tabular -> HTML table. First \\midrule splits off the header."""
    m = re.search(r"\\begin\{tabular\}\s*(?:\[[^\]]*\])?\s*\{", body)
    if not m:
        return None
    _, j = braced(body, body.index("{", m.end() - 1))
    end = env_end(body, m.start(), "tabular")
    inner = body[j: end - len("\\end{tabular}")]
    inner = re.sub(r"\\(?:toprule|bottomrule|hline|cmidrule)\b\s*(?:\([^)]*\))?(?:\{[^}]*\})?",
                   "", inner)

    def cells(row: str, tag: str, cls: str = "") -> str:
        row = row.strip()
        if not row:
            return ""
        out = []
        for c in re.split(r"(?<!\\)&", row):
            span = ""
            mc = re.match(r"\s*\\multicolumn\s*\{(\d+)\}", c)
            if mc:
                span = f' colspan="{mc.group(1)}"'
                parts = re.findall(r"\{([^{}]*)\}", c)
                c = parts[-1] if parts else c
            out.append(f"<{tag}{span}>{inline(c)}</{tag}>")
        return f'<tr class="{cls}">' + "".join(out) + "</tr>"

    def rows(chunk: str, tag: str, cls: str = "") -> str:
        got = [cells(r, tag, cls) for r in re.split(r"\\\\\s*(?:\[[^\]]*\])?", chunk)]
        return "".join(r for r in got if r and "<td></td>" not in r or tag == "th")

    groups = re.split(r"\\midrule\b", inner)
    if len(groups) > 1:
        head = f"<thead>{rows(groups[0], 'th')}</thead>"
        body_html = "".join(rows(g, "td", "group" if n else "") for n, g in enumerate(groups[1:]))
    else:
        head, body_html = "", rows(groups[0], "td")
    return f'<table>{head}<tbody>{body_html}</tbody></table>'


def render_float(env: str, body: str, figdir: str | None,
                 arxiv_id: str | None = None) -> dict:  # noqa: keep body as .raw at call site
    cap = ""
    m = re.search(r"\\caption\s*\{", body)
    if m:
        cap = inline(braced(body, body.index("{", m.end() - 1))[0])
    wide = " wide" if env.endswith("*") else ""
    imgs = [Path(g).name for g in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^}]*)\}", body)]

    if env.startswith("table"):
        inner = render_tabular(body)
        content = inner or '<div class="placeholder">[table not rendered]</div>'
        return {"type": "float", "raw": body.strip(),
                "html": f'<figure class="tbl{wide}"><figcaption>{cap}</figcaption>{content}</figure>'}

    if imgs and figdir:
        # /figure resolves the folder from ?id=; without it the server falls
        # back to the launch paper and every other paper's figures 404.
        q = f"?id={html.escape(arxiv_id, quote=True)}" if arxiv_id else ""
        tags = ('<div class="panels">'
                + "".join(f'<img src="/figure/{html.escape(i, quote=True)}{q}" alt="{html.escape(i)}">'
                          for i in imgs) + "</div>")
    else:
        tags = '<div class="placeholder">[figure not rendered]</div>'
    return {"type": "float", "raw": body.strip(),
            "html": f'<figure class="fig{wide}">{tags}<figcaption>{cap}</figcaption></figure>'}


def render_list(env: str, body: str) -> dict:
    items = [inline(x) for x in re.split(r"\\item\b", body)[1:]]
    tag = "ol" if env == "enumerate" else "ul"
    lis = "".join(f"<li>{i}</li>" for i in items if i)
    return {"type": "list", "html": f"<{tag}>{lis}</{tag}>", "raw": body.strip()}


def paragraphs(text: str) -> list[dict]:
    out = []
    for chunk in re.split(r"\n\s*\n", text):
        h = inline(chunk)
        if h and re.search(r"\w", re.sub(r"<[^>]+>", "", h)):
            out.append({"type": "para", "html": f"<p>{h}</p>", "raw": chunk.strip()})
    return out



def parse_body(body: str, figdir: str | None,
               arxiv_id: str | None = None) -> tuple[list[dict], dict]:
    """Blocks plus a {label: (number, anchor)} table for cross-references."""
    blocks: list[dict] = []
    path: list[str] = []
    nums = [0, 0, 0, 0]
    labels: dict[str, tuple[str, str]] = {}
    eq = 0
    appendix = False
    i = 0

    def add(new: list[dict]) -> None:
        sec = " \u203a ".join(path) or "(front matter)"
        for b in new:
            b["section"] = sec
        blocks.extend(new)

    def number(level: int) -> str:
        nums[level - 1] += 1
        for k in range(level, len(nums)):
            nums[k] = 0
        head = chr(64 + nums[0]) if appendix else str(nums[0])
        return ".".join([head] + [str(n) for n in nums[1:level]])

    while i < len(body):
        m = SPECIAL.search(body, i)
        if m is None:
            add(paragraphs(body[i:]))
            break
        add(paragraphs(body[i:m.start()]))

        if m.group("app"):
            appendix, nums[:] = True, [0, 0, 0, 0]
            i = m.end()
            continue

        if m.group("sec"):
            level = SECTION_LEVEL[m.group("sec")]
            raw_title, i = braced(body, m.end() - 1)
            starred = body[m.start():m.end()].rstrip("{").rstrip().endswith("*")
            num = "" if starred else number(level)
            anchor = f"sec-{num or len(blocks)}"
            title = inline(raw_title)
            path[:] = path[:level - 1] + [re.sub(r"<[^>]+>", "", title)]
            lab = re.match(r"\s*\\label\s*\{([^}]*)\}", body[i:])
            if lab:
                labels[lab.group(1).strip()] = (num, anchor)
                i += lab.end()
            tag = f"h{min(level + 1, 6)}"
            pre = f'<span class="secnum">{num}</span>' if num else ""
            add([{"type": "heading", "level": level, "title": title, "raw": raw_title,
                  "html": f'<{tag} id="{anchor}">{pre}{title}</{tag}>'}])
        else:
            env = m.group("env")
            end = env_end(body, m.start(), env)
            inner = body[m.end(): end - len(f"\\end{{{env}}}")]
            if re.fullmatch(FLOAT_ENVS, env):
                add([render_float(env, inner, figdir, arxiv_id)])
            elif re.fullmatch(LIST_ENVS, env):
                add([render_list(env, inner)])
            else:
                tex = body[m.start():end]
                anchor = ""
                if not env.endswith("*") and env != "split":
                    # amsmath numbers every row of align/gather/eqnarray
                    multi = env.rstrip("*") in ("align", "gather", "eqnarray", "flalign")
                    rows = re.split(r"\\\\", inner) if multi else [inner]
                    for row in rows:
                        if not row.strip() or re.search(r"\\(?:nonumber|notag)\b", row):
                            continue
                        eq += 1
                        anchor = anchor or f"eq-{eq}"
                        for lb in re.findall(r"\\label\s*\{([^}]*)\}", row):
                            labels[lb.strip()] = (str(eq), f"eq-{eq}")
                idattr = f' id="{anchor}"' if anchor else ""
                add([{"type": "math", "raw": tex.strip(),
                      "html": f'<div class="eq"{idattr}>'
                              f'{html.escape(tex, quote=False)}</div>'}])
            i = end

    for n, b in enumerate(blocks):
        b["id"] = f"b{n}"
    return blocks, labels


def remove_cmd(s: str, cmd: str) -> str:
    """Delete \\cmd[opt]{arg} wherever it appears, brace-matching the argument."""
    out, i = [], 0
    pat = re.compile(r"\\" + cmd + r"\s*\*?")
    while True:
        m = pat.search(s, i)
        if not m:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:m.start()])
        j = m.end()
        if j < len(s) and s[j] == "[":
            j = skip_optional(s, j)
        while j < len(s) and s[j].isspace():
            j += 1
        if j < len(s) and s[j] == "{":
            _, j = braced(s, j)
        i = j


def resolve_refs(blocks: list[dict], labels: dict, bib: dict) -> None:
    """Turn \\ref placeholders into links and citations into the paper's own numbers."""
    order = {k: n + 1 for n, k in enumerate(bib)}

    def xref(m: re.Match) -> str:
        num, anchor = labels.get(m.group(1), ("", ""))
        if not anchor:
            return f'<span class="xref">{m.group(1)}</span>'
        shown = f"({num})" if anchor.startswith("eq-") else num
        return f'<a class="xref" href="#{anchor}">{shown}</a>'

    def cite(m: re.Match) -> str:
        keys = m.group(1).split(",")
        nums = [order.get(k) for k in keys]
        shown = ", ".join(str(n) for n in nums if n) or "?"
        return (f'<span class="cite" data-keys="{m.group(1)}">[{shown}]</span>')

    for b in blocks:
        h = re.sub(r'<span class="xref">([^<]*)</span>', xref, b["html"])
        h = re.sub(r'<span class="cite" data-keys="([^"]*)">\[[^\]]*\]</span>', cite, h)
        b["html"] = h


# -------------------------------------------------------------------------- driver

def render(tex: str, figdir: str | None = None, arxiv_id: str | None = None) -> dict:
    bib_split = re.split(r"% ---- bibliography \(\.bbl\) ----", tex)
    bib, bib_titles = parse_bbl(bib_split[1]) if len(bib_split) > 1 else ({}, {})
    tex = bib_split[0]

    split = re.search(r"\\begin\{document\}", tex)
    preamble = tex[:split.start()] if split else ""
    body = tex[split.end():] if split else tex
    body = re.split(r"\\end\{document\}", body)[0]

    if not bib:
        m = re.search(r"\\begin\{thebibliography\}[\s\S]*", body)
        if m:
            bib, bib_titles = parse_bbl(m.group(0))
            body = body[:m.start()]

    def grab(cmd: str) -> str:
        m = re.search(r"\\" + cmd + r"\s*\{", body)
        return inline(braced(body, body.index("{", m.end() - 1))[0]) if m else ""

    TEXT_MACROS.clear()
    TEXT_MACROS.update(macro_table(preamble))
    title = grab("title")
    authors = []
    for m in re.finditer(r"\\author\s*\{", body):
        raw, _ = braced(body, body.index("{", m.end() - 1))
        name = re.sub(r"\s+", " ", inline(re.sub(r"\$[^$]*\$", "", raw))).strip()
        if name and name not in authors:
            authors.append(name)
    abstract = ""
    ma = re.search(r"\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}", body)
    if ma:
        abstract = inline(ma.group(1))
        body = body[:ma.start()] + body[ma.end():]
    for cmd in ("preprint", "title", "author", "affiliation", "altaffiliation",
                "collaboration", "email", "date", "thanks", "keywords", "pacs"):
        body = remove_cmd(body, cmd)
    body = re.sub(r"\\(?:maketitle|tableofcontents)\b", "", body)

    blocks, labels = parse_body(body, figdir, arxiv_id)
    resolve_refs(blocks, labels, bib)
    return {"title": title, "authors": authors, "abstract": abstract,
            "macros": extract_macros(preamble), "bib": bib, "bib_titles": bib_titles,
            "blocks": blocks}


if __name__ == "__main__":
    src = Path(sys.argv[1])
    figs = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(render(src.read_text(), figs), indent=2)[:4000])
