"""The product document: what KEP Brain itself is, as a `Document` with `Section`s.

`app/data/kep_brain.md` ships inside the package. `sync_docs` stores it as `Document {kind: 'product'}`
with one `Section` per heading, so "what is KEP Brain" is answered from a cited record exactly like
"what is a KEP" is answered from the process documents. Each `##` heading is followed by an HTML comment
`<!-- readme: <anchor> -->` naming the heading of the public README the section is cited at (`top` for the
README itself); the section's URL is the README URL plus that anchor.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.ingest.sections import ParsedSection, doc_sections

PRODUCT_REPO = "akshat-lakhera/kep-brain"
PRODUCT_DOC_PATH = "README.md"
PRODUCT_DOC_KEY = "kep-brain/README.md"
PRODUCT_DOC_TITLE = "KEP Brain"
PRODUCT_DOC_URL = f"https://github.com/{PRODUCT_REPO}/blob/main/{PRODUCT_DOC_PATH}"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "kep_brain.md"

_README_RE = re.compile(r"^[ \t]*<!--\s*readme:\s*([A-Za-z0-9_-]+)\s*-->[ \t]*$", re.M)


def product_text() -> str:
    return DATA_FILE.read_text(encoding="utf-8")


def readme_anchor(section_text: str) -> tuple[str | None, str]:
    """(anchor or None, text without the marker). `top` means the README itself, without a fragment."""
    m = _README_RE.search(section_text)
    if not m:
        return None, section_text
    anchor = m.group(1)
    text = (section_text[: m.start()] + section_text[m.end() :]).strip()
    return (None if anchor == "top" else anchor), text


def section_url(anchor: str | None) -> str:
    return PRODUCT_DOC_URL if anchor is None else f"{PRODUCT_DOC_URL}#{anchor}"


def parse_product_doc(text: str) -> tuple[str, list[tuple[ParsedSection, str]]]:
    """Title and (section, url) pairs; the readme marker is removed from each section's text."""
    title, parsed = doc_sections(text, PRODUCT_DOC_TITLE)
    out: list[tuple[ParsedSection, str]] = []
    for s in parsed:
        anchor, body = readme_anchor(s.text)
        clean = ParsedSection(anchor=s.anchor, heading=s.heading, level=s.level, order=s.order, text=body, kind=s.kind)
        out.append((clean, section_url(anchor)))
    return title, out


def _blob_sha(text: str) -> str:
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # a git-style content id, not a secret


def product_doc_rows(
    text: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(documents, sections, HAS_SECTION rows, NEXT rows) for the shipped product document, same shape as the
    process documents of `app.ingest.docs`. Keys are deterministic, so every sync MERGEs the same nodes."""
    text = product_text() if text is None else text
    title, parsed = parse_product_doc(text)
    blob = _blob_sha(text)
    docs = [
        {
            "key": PRODUCT_DOC_KEY,
            "kind": "product",
            "repo": PRODUCT_REPO,
            "path": PRODUCT_DOC_PATH,
            "title": title,
            "blob_sha": blob,
            "byte_size": len(text.encode("utf-8")),
            "section_count": len(parsed),
            "url": PRODUCT_DOC_URL,
            "source_url": PRODUCT_DOC_URL,
            "source_repo": PRODUCT_REPO,
            "source_path": PRODUCT_DOC_PATH,
            "source_sha": blob,
        }
    ]
    sections: list[dict[str, Any]] = []
    has: list[dict[str, Any]] = []
    nxt: list[dict[str, Any]] = []
    prev: str | None = None
    for s, url in parsed:
        s_key = f"product:{PRODUCT_DOC_KEY}#{s.anchor}"
        sections.append(
            {
                "key": s_key,
                "doc_path": PRODUCT_DOC_KEY,
                "anchor": s.anchor,
                "heading": s.heading,
                "level": s.level,
                "order": s.order,
                "text": s.text,
                "char_count": s.char_count,
                "kind": s.kind,
                "url": url,
                "source_url": url,
                "source_repo": PRODUCT_REPO,
                "source_path": PRODUCT_DOC_PATH,
                "source_sha": blob,
            }
        )
        has.append({"from": PRODUCT_DOC_KEY, "to": s_key, "props": {"order": s.order, "w": 1}})
        if prev:
            nxt.append({"from": prev, "to": s_key, "props": {"w": 1}})
        prev = s_key
    return docs, sections, has, nxt
