# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""Searches the documentation that ships with the user's own STAR-CCM+ installation.

Nothing from the documentation is stored in this repository: the user guide and the Java API reference are
read from the local install, and the text index is cached in the user's cache folder.
"""
from __future__ import annotations

import difflib
import html
import json
import os
import re
import threading
from pathlib import Path

from . import paths

_LOCK = threading.Lock()
_MANUAL: list[dict] | None = None
_JAVADOC: dict[str, list[str]] | None = None


def _html_text(s: str) -> tuple[str, str]:
    t = re.search(r"<title>(.*?)</title>", s[:5000], re.S)
    m = re.search(r"<main[^>]*>(.*)</main>", s, re.S) or re.search(r"<article[^>]*>(.*)</article>", s, re.S)
    b = m.group(1) if m else s[s.find("<body"):]
    b = re.sub(r"<(script|style|nav)[^>]*>.*?</\1>", " ", b, flags=re.S)
    b = re.sub(r"</(p|li|tr|h\d|div|pre|dt|dd)>", "\n", b)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", b))
    txt = re.sub(r"[ \t\r\f\v]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt).strip()
    return (html.unescape(t.group(1)).strip() if t else ""), txt


def _manual() -> list[dict]:
    global _MANUAL
    with _LOCK:
        if _MANUAL is not None:
            return _MANUAL
        src = paths.manual_dir()
        cache = paths.cache_dir() / f"manual-{paths.install_dir().name}.jsonl"
        if not cache.exists():
            tmp = cache.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as out:
                for f in sorted(src.glob("*.html")):
                    title, text = _html_text(f.read_text(encoding="utf-8", errors="replace"))
                    out.write(json.dumps({"id": f.stem, "title": title, "text": text}, ensure_ascii=False) + "\n")
            os.replace(tmp, cache)
        with open(cache, encoding="utf-8") as f:
            _MANUAL = [json.loads(line) for line in f]
        return _MANUAL


def search_manual(query: str, limit: int = 10, regex: bool = False, context: int = 220) -> dict:
    """All words must appear (case-insensitive); pages with words in the title rank first."""
    if not query.strip():
        raise ValueError("empty query")
    pages = _manual()
    if regex:
        pats = [re.compile(query, re.I)]
    else:
        pats = [re.compile(re.escape(w), re.I) for w in query.split()]
    hits = []
    for p in pages:
        if not all(pat.search(p["text"]) or pat.search(p["title"]) for pat in pats):
            continue
        score = sum(50 * bool(pat.search(p["title"])) + min(20, len(pat.findall(p["text"][:20000]))) for pat in pats)
        m = pats[0].search(p["text"])
        snippet = p["text"][max(0, m.start() - context): m.end() + context] if m else p["text"][: 2 * context]
        hits.append((score, {"id": p["id"], "title": p["title"], "snippet": re.sub(r"\s+", " ", snippet)}))
    hits.sort(key=lambda h: -h[0])
    return {"total": len(hits), "results": [h for _, h in hits[:limit]]}


def read_page(page_id: str, start: str | None = None, offset: int = 0, max_chars: int = 6000) -> dict:
    page_id = Path(page_id).stem
    match = next((p for p in _manual() if p["id"] == page_id), None)
    if not match:
        raise KeyError(f"No manual page {page_id!r}. Use starccm_docs_search to find page ids.")
    text = match["text"]
    if start:
        i = text.lower().find(start.lower())
        if i >= 0:
            text = text[i:]
    chunk = text[offset: offset + max_chars]
    return {"id": page_id, "title": match["title"], "offset": offset, "chars": len(chunk),
            "has_more": offset + max_chars < len(text), "text": chunk}


# ---- Java API reference -----------------------------------------------------------------------------
def _javadoc() -> dict[str, list[str]]:
    global _JAVADOC
    with _LOCK:
        if _JAVADOC is not None:
            return _JAVADOC
        root = paths.javadoc_dir()
        cache = paths.cache_dir() / f"javadoc-{paths.install_dir().name}.json"
        if cache.exists():
            _JAVADOC = json.loads(cache.read_text(encoding="utf-8"))
            return _JAVADOC
        idx: dict[str, list[str]] = {}
        for dirpath, dirnames, files in os.walk(root / "star"):
            dirnames[:] = [d for d in dirnames if d != "class-use"]
            for f in files:
                if f.endswith(".html") and f[0].isupper():
                    idx.setdefault(f[:-5], []).append(os.path.relpath(os.path.join(dirpath, f), root))
        cache.write_text(json.dumps(idx), encoding="utf-8")
        _JAVADOC = idx
        return idx


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment.replace("<wbr>", "")))).strip()


def _class_page(rel: str) -> dict:
    s = (paths.javadoc_dir() / rel).read_text(encoding="utf-8", errors="replace")
    qualified = rel[:-5].replace(os.sep, ".").replace("/", ".")
    chain = [_clean(x) for x in re.findall(r'<div class="inheritance"[^>]*>(.*?)(?=<div class="inheritance"|</div>)', s, re.S)]
    sigs = [_clean(x) for x in re.findall(r'<div class="member-signature">(.*?)</div>', s, re.S)]
    inherited = {}
    for owner, block in re.findall(r'<h3[^>]*>Methods inherited from [^<]*<a[^>]*>([\w.]+)</a>.*?<code>(.*?)</code>', s, re.S):
        for name in re.findall(r">(\w+)</a>", block):
            inherited.setdefault(name, owner)
    return {"class": qualified, "inheritance": [c for c in chain if c], "signatures": sigs, "inherited": inherited}


def option_names(option_class: str) -> list[str] | None:
    """Labels of <Option>.Type in declaration order, e.g. FlowDirectionOption -> Boundary-Normal, Components, Angles.

    In .sim files an option is stored as 'Selected': <index>. On FlowDirectionOption the index matched this order
    (Components on a Free Stream with an angle-of-attack vector, Boundary-Normal on a stagnation inlet).
    """
    try:
        idx = _javadoc()
    except paths.NotFound:
        return None
    rel = (idx.get(option_class + ".Type") or [None])[0]
    if not rel:
        return None
    s = (paths.javadoc_dir() / rel).read_text(encoding="utf-8", errors="replace")
    labels = []
    for sig in (_clean(x) for x in re.findall(r'<div class="member-signature">(.*?)</div>', s, re.S)):
        m = re.match(r'@StarField\("([^"]*)"\)\s+public static final \S+ (\w+)$', sig)
        if m:
            labels.append(m.group(1) or m.group(2))
    return labels or None


def api_lookup(name: str, contains: str | None = None, limit: int = 40, _depth: int = 0) -> dict:
    """`Class`, `Class.method` or `Outer.Inner` (for example FlowDirectionOption.Type)."""
    idx = _javadoc()
    if name in idx or "." not in name:
        cls, member = name, None
    else:
        cls, member = name.rsplit(".", 1)
    if cls not in idx:
        close = difflib.get_close_matches(cls, list(idx), n=10, cutoff=0.6)
        return {"query": name, "found": False, "similar_classes": close}
    out = []
    for rel in idx[cls]:
        page = _class_page(rel)
        entry = {"class": page["class"], "inheritance": page["inheritance"]}
        if member:
            pat = re.compile(r"(^|\s)" + re.escape(member) + r"(\(|$)")
            found = [s for s in page["signatures"] if pat.search(s)]
            entry["member"] = member
            if found:
                entry["signatures"] = found
            elif member in page["inherited"] and _depth < 8:
                owner = page["inherited"][member]
                entry["inherited_from"] = owner
                entry["owner_lookup"] = api_lookup(owner.rsplit(".", 1)[-1] + "." + member, _depth=_depth + 1)
            else:
                entry["signatures"] = []
                entry["note"] = "member not found on this class page"
        else:
            sigs = [s for s in page["signatures"] if not contains or contains.lower() in s.lower()]
            entry["members_total"] = len(page["signatures"])
            entry["signatures"] = sigs[:limit]
            entry["has_more"] = len(sigs) > limit
        out.append(entry)
    return {"query": name, "found": True, "pages": out}
