#!/usr/bin/env python3
"""
Extract a research study / journal article PDF into structured Markdown.

Detects IMRaD section headings, pulls metadata from the first page
(title, authors, journal, year, DOI), and produces a clean Markdown file
with a metadata header + section structure + preserved references.

Usage:
    python extract_study_pdf.py <pdf_path> [-o output.md] [--dry-run] [--layout]
"""

import argparse
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*FontBBox.*")
warnings.filterwarnings("ignore", category=UserWarning)

import pdfplumber

# Canonical section names and the aliases that map to them.
SECTION_ALIASES = [
    ("Abstract",     [r"abstract", r"summary"]),
    ("Introduction", [r"introduction", r"background"]),
    ("Methods",      [r"methods", r"materials and methods", r"methodology",
                      r"patients and methods", r"study design", r"methods and materials",
                      r"subjects and methods", r"experimental procedures"]),
    ("Results",      [r"results", r"findings"]),
    ("Discussion",   [r"discussion"]),
    ("Conclusion",   [r"conclusion", r"conclusions", r"concluding remarks"]),
    ("References",   [r"references", r"bibliography", r"literature cited",
                      r"works cited"]),
]

# Build a single regex for heading detection.
# Matches lines that are JUST a heading (optional numbering, optional trailing colon/period).
HEADING_PATTERNS = []
for canonical, aliases in SECTION_ALIASES:
    for a in aliases:
        HEADING_PATTERNS.append((canonical, re.compile(
            rf"^\s*(?:\d+\.?\s*)?{a}\s*[:.]?\s*$", re.IGNORECASE)))

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PMID_RE = re.compile(r"\bPMID[:\s]*(\d{6,9})\b", re.IGNORECASE)
PMCID_RE = re.compile(r"\bPMC\d{6,9}\b", re.IGNORECASE)


def extract_pages(pdf_path: str, use_layout: bool = False) -> list[str]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if use_layout:
                text = (page.extract_text(layout=True) or "").replace('\x00', '')
            else:
                text = (page.extract_text() or "").replace('\x00', '')
            pages.append(text)
    return pages


def clean_text(text: str) -> str:
    """Light cleanup: drop standalone page numbers, collapse blank lines."""
    lines = text.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if re.match(r"^\d{1,4}$", s):
            continue
        if re.match(r"^page\s+\d+\s+of\s+\d+$", s, re.IGNORECASE):
            continue
        out.append(line.rstrip())
    # Collapse 3+ blank lines to 2
    joined = "\n".join(out)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined


def extract_metadata(pages: list[str]) -> dict:
    """Pull best-guess metadata from the first 2 pages."""
    head = "\n".join(pages[:2])
    meta = {
        "title": None,
        "authors": None,
        "journal": None,
        "year": None,
        "doi": None,
        "pmid": None,
        "pmcid": None,
    }

    # DOI
    m = DOI_RE.search(head)
    if m:
        meta["doi"] = m.group(0).rstrip(".,;)")

    # PMID / PMCID
    m = PMID_RE.search(head)
    if m:
        meta["pmid"] = m.group(1)
    m = PMCID_RE.search(head)
    if m:
        meta["pmcid"] = m.group(0)

    # Year (first 4-digit year on page 1)
    m = YEAR_RE.search(pages[0] if pages else "")
    if m:
        meta["year"] = m.group(0)

    # Title: longest non-trivial line in the first ~15 lines of page 1
    # that isn't a journal header, DOI, or copyright
    if pages:
        first_lines = [l.strip() for l in pages[0].split("\n")[:25] if l.strip()]
        candidates = []
        for line in first_lines:
            lower = line.lower()
            if len(line) < 15 or len(line) > 250:
                continue
            if any(skip in lower for skip in [
                "doi", "copyright", "©", "http", "www.", "issn",
                "received", "accepted", "published", "volume", "license",
                "open access", "original article", "review article",
            ]):
                continue
            if DOI_RE.search(line):
                continue
            candidates.append(line)
        if candidates:
            # Title is usually the first long-ish line, possibly spanning 2.
            # Take the first candidate and any immediately following candidates
            # that look like a continuation (start lowercase or are short).
            meta["title"] = candidates[0]
            # Try to glue wrapped title lines
            for nxt in candidates[1:3]:
                if nxt and (nxt[0].islower() or len(nxt) < 60) and len(meta["title"]) < 120:
                    meta["title"] = meta["title"] + " " + nxt
                else:
                    break

    return meta


def find_sections(full_text: str) -> list[tuple[str, int]]:
    """Return [(canonical_name, line_index), ...] sorted by position."""
    lines = full_text.split("\n")
    hits = []
    seen = set()
    for i, line in enumerate(lines):
        for canonical, pat in HEADING_PATTERNS:
            if pat.match(line):
                # Only take the FIRST occurrence of each canonical section
                if canonical in seen:
                    continue
                # Abstract must appear early; Methods/Results/Discussion after Abstract
                hits.append((canonical, i))
                seen.add(canonical)
                break
    hits.sort(key=lambda x: x[1])
    return hits


def build_markdown(pdf_path: str, pages: list[str]) -> tuple[str, dict, list]:
    meta = extract_metadata(pages)
    full = clean_text("\n".join(pages))
    sections = find_sections(full)

    # Build header
    lines_out = []
    title = meta["title"] or Path(pdf_path).stem
    lines_out.append(f"# {title}")
    lines_out.append("")
    if meta["authors"]:
        lines_out.append(f"**Authors:** {meta['authors']}")
    if meta["journal"]:
        lines_out.append(f"**Journal:** {meta['journal']}")
    if meta["year"]:
        lines_out.append(f"**Year:** {meta['year']}")
    if meta["doi"]:
        lines_out.append(f"**DOI:** {meta['doi']}")
    if meta["pmid"]:
        lines_out.append(f"**PMID:** {meta['pmid']}")
    if meta["pmcid"]:
        lines_out.append(f"**PMCID:** {meta['pmcid']}")
    lines_out.append("**Study design:** _fill in manually_")
    lines_out.append("")
    lines_out.append("## Key Findings")
    lines_out.append("")
    lines_out.append("- _fill in after reading_")
    lines_out.append("")
    lines_out.append("---")
    lines_out.append("")

    # Body: if we found sections, slice; otherwise dump flat
    body_lines = full.split("\n")
    if sections:
        # Prepend anything before first section as "Front matter"
        first_idx = sections[0][1]
        if first_idx > 0:
            front = "\n".join(body_lines[:first_idx]).strip()
            if front:
                lines_out.append("<!-- Front matter (title page, abstract header, etc.) -->")
                lines_out.append("")
                lines_out.append(front)
                lines_out.append("")
        for i, (name, start) in enumerate(sections):
            end = sections[i + 1][1] if i + 1 < len(sections) else len(body_lines)
            chunk = "\n".join(body_lines[start + 1:end]).strip()
            lines_out.append(f"## {name}")
            lines_out.append("")
            lines_out.append(chunk)
            lines_out.append("")
            if name != "References" and i + 1 < len(sections):
                pass  # no extra divider between sections
        lines_out.append("")
    else:
        lines_out.append("<!-- No IMRaD sections detected — flat extraction -->")
        lines_out.append("")
        lines_out.append(full)

    return "\n".join(lines_out), meta, sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="Path to study PDF")
    ap.add_argument("-o", "--output", help="Output .md path (default: alongside PDF)")
    ap.add_argument("--dry-run", action="store_true", help="Print detected metadata + sections without writing")
    ap.add_argument("--layout", action="store_true", help="Use pdfplumber layout=True mode for column-heavy PDFs")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    pages = extract_pages(str(pdf_path), use_layout=args.layout)
    md, meta, sections = build_markdown(str(pdf_path), pages)

    if args.dry_run:
        print("=" * 60)
        print(f"File: {pdf_path.name}")
        print(f"Pages: {len(pages)}")
        print("-" * 60)
        print("METADATA:")
        for k, v in meta.items():
            print(f"  {k:10s}: {v}")
        print("-" * 60)
        print(f"SECTIONS DETECTED ({len(sections)}):")
        for name, idx in sections:
            print(f"  line {idx:5d}: {name}")
        print("=" * 60)
        return

    out_path = Path(args.output) if args.output else pdf_path.with_suffix(".md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path} ({len(md):,} chars, {len(sections)} sections)")


if __name__ == "__main__":
    main()
