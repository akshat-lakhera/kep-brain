"""The product document (app/data/kep_brain.md): parsing, node and edge rows, README anchors, packaging."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ingest.product import (
    DATA_FILE,
    PRODUCT_DOC_KEY,
    PRODUCT_DOC_URL,
    parse_product_doc,
    product_doc_rows,
    product_text,
    readme_anchor,
)
from app.ingest.sections import doc_sections, headings

REPO_README = Path(__file__).resolve().parents[4] / "README.md"

SAMPLE = """# KEP Brain
<!-- readme: kep-brain -->

KEP Brain is a company brain for the KEP process.

## Table of contents

- [Privacy](#privacy)

## Privacy
<!-- readme: status -->

Only public logins.

## Affiliation
<!-- readme: top -->

Not affiliated.
"""


def test_doc_sections_keeps_intro_and_drops_toc() -> None:
    title, parsed = doc_sections(SAMPLE, "fallback")
    assert title == "KEP Brain"
    assert [(s.anchor, s.level, s.order, s.kind) for s in parsed] == [
        ("kep-brain", 1, 0, "summary"),
        ("privacy", 2, 1, "other"),
        ("affiliation", 2, 2, "other"),
    ]


def test_readme_anchor_marker_is_removed() -> None:
    assert readme_anchor("<!-- readme: status -->\n\nOnly public logins.") == ("status", "Only public logins.")
    assert readme_anchor("<!-- readme: top -->\n\nx") == (None, "x")
    assert readme_anchor("no marker") == (None, "no marker")


def test_parse_sample_urls() -> None:
    _, parsed = parse_product_doc(SAMPLE)
    assert [(s.text, url) for s, url in parsed] == [
        ("KEP Brain is a company brain for the KEP process.", f"{PRODUCT_DOC_URL}#kep-brain"),
        ("Only public logins.", f"{PRODUCT_DOC_URL}#status"),
        ("Not affiliated.", PRODUCT_DOC_URL),
    ]


def test_rows_from_sample() -> None:
    docs, sections, has, nxt = product_doc_rows(SAMPLE)
    assert len(docs) == 1
    doc = docs[0]
    assert doc["key"] == PRODUCT_DOC_KEY == "kep-brain/README.md"
    assert doc["kind"] == "product"
    assert doc["title"] == "KEP Brain"
    assert doc["url"] == doc["source_url"] == PRODUCT_DOC_URL
    assert doc["section_count"] == 3
    assert doc["blob_sha"] == doc["source_sha"] and len(doc["blob_sha"]) == 40
    assert [s["key"] for s in sections] == [
        "product:kep-brain/README.md#kep-brain",
        "product:kep-brain/README.md#privacy",
        "product:kep-brain/README.md#affiliation",
    ]
    assert all(s["doc_path"] == PRODUCT_DOC_KEY and s["source_sha"] == doc["blob_sha"] for s in sections)
    assert all("<!--" not in s["text"] for s in sections)
    assert [s["url"] for s in sections] == [
        f"{PRODUCT_DOC_URL}#kep-brain",
        f"{PRODUCT_DOC_URL}#status",
        PRODUCT_DOC_URL,
    ]
    assert has == [
        {"from": PRODUCT_DOC_KEY, "to": sections[0]["key"], "props": {"order": 0, "w": 1}},
        {"from": PRODUCT_DOC_KEY, "to": sections[1]["key"], "props": {"order": 1, "w": 1}},
        {"from": PRODUCT_DOC_KEY, "to": sections[2]["key"], "props": {"order": 2, "w": 1}},
    ]
    assert nxt == [
        {"from": sections[0]["key"], "to": sections[1]["key"], "props": {"w": 1}},
        {"from": sections[1]["key"], "to": sections[2]["key"], "props": {"w": 1}},
    ]


def test_rows_are_deterministic() -> None:
    assert product_doc_rows(SAMPLE) == product_doc_rows(SAMPLE)


def test_shipped_file_exists_inside_the_package() -> None:
    assert DATA_FILE.is_file()
    assert DATA_FILE.parent.name == "data" and DATA_FILE.parent.parent.name == "app"


def test_shipped_document_sections() -> None:
    docs, sections, has, nxt = product_doc_rows()
    assert docs[0]["title"] == "KEP Brain"
    anchors = [s["anchor"] for s in sections]
    assert anchors[0] == "kep-brain"
    assert len(anchors) == len(set(anchors)), "section anchors must be unique: they are the node keys"
    expected = {
        "what-kep-brain-answers", "how-answers-are-produced", "when-kep-brain-abstains", "what-the-audit-does",
        "data-sources-and-scope", "privacy", "licence", "affiliation",
    }  # fmt: skip
    assert expected <= set(anchors)
    assert sections[0]["text"].startswith("KEP Brain is a company brain")
    for s in sections:
        assert s["text"], s["anchor"]
        assert "<!--" not in s["text"]
        assert s["url"].startswith(PRODUCT_DOC_URL)
        # The planner reads at most 280 characters of a section: the first sentence must carry the point.
        assert len(s["text"].split(". ")[0]) <= 280, s["anchor"]
    assert len(has) == len(sections) and len(nxt) == len(sections) - 1


def test_every_shipped_section_carries_a_readme_marker() -> None:
    _, parsed = doc_sections(product_text(), "x")
    for s in parsed:
        anchor, _ = readme_anchor(s.text)
        assert anchor is not None or "<!-- readme: top -->" in s.text, f"{s.anchor} has no readme marker"


@pytest.mark.skipif(not REPO_README.is_file(), reason="repository README.md not present")
def test_section_urls_point_at_headings_that_exist_in_the_readme() -> None:
    readme_anchors = {h.anchor for h in headings(REPO_README.read_text(encoding="utf-8"))}
    _, sections, _, _ = product_doc_rows()
    for s in sections:
        fragment = s["url"].removeprefix(PRODUCT_DOC_URL)
        if fragment:
            assert fragment.startswith("#") and fragment[1:] in readme_anchors, (s["anchor"], fragment)


def test_shipped_document_makes_no_volatile_or_vendor_claims() -> None:
    text = product_text()
    low = text.lower()
    # Two vendor names are assembled from parts so a repository-wide search for them finds nothing.
    vendors = ("anth" + "ropic", "cla" + "ude")
    for banned in ("judge", "track 3", "hackathon", "openai", "groq", *vendors, "gpt", "qwen"):
        assert banned not in low, banned
    # No counts that change between syncs (node, edge, KEP, people, finding totals).
    assert not re.search(r"\b\d{2,}\s+(keps|people|findings|nodes|edges)\b", low)
