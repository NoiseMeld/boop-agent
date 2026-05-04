#!/usr/bin/env python3
"""
Extract and format a PDF book into structured Markdown.

Uses pdfplumber to extract text, detects chapter boundaries via multiple
strategies (text markers, empty pages, TOC matching), and builds a
well-structured Markdown file.

With --render-images, renders empty/near-empty pages as PNG images for
Claude Code to read and fill in during a vision pass.

Usage:
    python tools/extract_book_pdf.py <pdf_path> [--output <output_path>] [--dry-run]
    python tools/extract_book_pdf.py <pdf_path> --render-images [--images-dir <dir>]

If --output is not specified, saves as the PDF filename with .md extension
in the same directory. Use --dry-run to preview detected chapters without writing.
"""

import argparse
import re
import sys
import warnings
from pathlib import Path

# Suppress harmless FontBBox warnings from pdfplumber/pdfminer
warnings.filterwarnings("ignore", message=".*FontBBox.*")
warnings.filterwarnings("ignore", category=UserWarning)

import pdfplumber

MIN_CHARS = 10  # Pages with fewer stripped chars are considered "empty"
IMAGE_PAGE_THRESHOLD = 50  # Pages with fewer chars get rendered as images


# ---------------------------------------------------------------------------
# Page extraction
# ---------------------------------------------------------------------------

def extract_all_pages(pdf_path: str) -> list[dict]:
    """Extract text from every page."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").replace('\x00', '')
            pages.append({
                "idx": i,
                "label": i + 1,
                "text": text,
                "stripped": text.strip(),
                "chars": len(text.strip()),
            })
    return pages


def clean_page_text(text: str) -> str:
    """Remove page numbers and OceanofPDF lines from extracted text."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        # Skip OceanofPDF lines
        if "oceanofpdf" in s.lower():
            continue
        # Skip standalone page numbers (1-4 digit numbers alone on a line)
        if re.match(r'^\d{1,4}$', s):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Image rendering for vision pass
# ---------------------------------------------------------------------------

def render_image_pages(pdf_path: str, pages: list[dict], images_dir: Path) -> dict[int, str]:
    """
    Render pages that have little/no extractable text as PNG images.
    Returns a dict mapping page index -> image file path.
    """
    import pypdfium2 as pdfium

    images_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(pdf_path)
    rendered = {}

    for page_data in pages:
        idx = page_data["idx"]
        if page_data["chars"] < IMAGE_PAGE_THRESHOLD:
            img_name = f"page_{idx + 1:04d}.png"
            img_path = images_dir / img_name
            page = pdf[idx]
            bitmap = page.render(scale=2)  # 2x for readability
            img = bitmap.to_pil()
            img.save(str(img_path))
            rendered[idx] = str(img_path)

    pdf.close()
    return rendered


# ---------------------------------------------------------------------------
# Chapter detection strategies
# ---------------------------------------------------------------------------

def find_backmatter_start(pages: list[dict]) -> int:
    """
    Find where backmatter begins (Notes, Bibliography, References, etc.)
    to avoid detecting endnote chapter references as real chapters.
    """
    backmatter_keywords = [
        "notes", "bibliography", "references", "index",
        "acknowledgments", "acknowledgements", "about the author",
    ]
    for i, page in enumerate(pages):
        first_line = page["stripped"].split("\n")[0].strip().lower() if page["stripped"] else ""
        # Only match if it's the primary content of a page header
        if first_line in backmatter_keywords or (
            any(first_line.startswith(kw) for kw in backmatter_keywords)
            and len(first_line) < 30
        ):
            # Verify this is the real backmatter, not just a chapter mentioning "Notes"
            # by checking if it's past the halfway point of the book
            if i > len(pages) * 0.5:
                return i
    return len(pages)


def detect_chapters_by_text_markers(pages: list[dict]) -> list[dict]:
    """
    Find chapters by scanning for 'CHAPTER N' or 'Chapter N:' text markers
    at the start of pages.
    """
    backmatter = find_backmatter_start(pages)

    # Identify TOC pages to skip
    toc_pages = set()
    for p in pages[:20]:
        lower = p["stripped"].lower()
        if "contents" in lower and p["chars"] < 2000:
            toc_pages.add(p["idx"])
            # Also mark the next few pages as potential TOC continuation
            for offset in range(1, 4):
                if p["idx"] + offset < len(pages):
                    next_p = pages[p["idx"] + offset]
                    # TOC continuation pages tend to be short with many entries
                    if next_p["chars"] < 1500 and next_p["stripped"].count("\n") > 5:
                        toc_pages.add(next_p["idx"])

    chapters = []
    i = 0
    while i < min(len(pages), backmatter):
        if i in toc_pages:
            i += 1
            continue

        text = pages[i]["stripped"]
        first_lines = text[:200]  # Check first 200 chars

        # Match "CHAPTER N" or "Chapter N:" patterns
        match = re.match(
            r'^(?:CHAPTER|Chapter)\s+(\d+)\s*[:\.]?\s*(.*?)$',
            first_lines, re.MULTILINE
        )
        if match:
            num = match.group(1)
            # The subtitle might be on the same page or the next page
            subtitle = match.group(2).strip()

            # If the page is short (just "CHAPTER N"), the title is on the next page
            if pages[i]["chars"] < 50 and i + 1 < len(pages):
                next_text = pages[i + 1]["stripped"]
                # First line of next page is likely the chapter title
                subtitle = next_text.split("\n")[0].strip()
                content_start = i + 1
            else:
                content_start = i

            # Try to get a better subtitle from the next line if current is empty
            if not subtitle and pages[i]["chars"] > 50:
                lines = text.split("\n")
                for line in lines[1:]:
                    candidate = line.strip()
                    if candidate and len(candidate) > 3 and not re.match(r'^\d+$', candidate):
                        subtitle = candidate
                        break

            title = f"Chapter {num}: {subtitle}" if subtitle else f"Chapter {num}"
            chapters.append({
                "title": title,
                "start_page": content_start,
                "marker_page": i,
                "type": "chapter",
            })
        i += 1

    return chapters


def detect_chapters_by_single_number(pages: list[dict]) -> list[dict]:
    """
    For books like Big Fat Surprise where chapters are marked by just
    a number (e.g., "1") as the first line of a page.
    """
    backmatter = find_backmatter_start(pages)
    chapters = []
    for i, page in enumerate(pages[:backmatter]):
        text = page["stripped"]
        lines = text.split("\n")
        first_line = lines[0].strip() if lines else ""

        # Page starts with a single number 1-99 and has content after it
        if re.match(r'^(\d{1,2})$', first_line) and page["chars"] > 100:
            num = int(first_line)
            if 1 <= num <= 50:
                # Get chapter title from second line or TOC
                subtitle = ""
                for line in lines[1:]:
                    candidate = line.strip()
                    if candidate and len(candidate) > 3:
                        subtitle = candidate
                        break
                title = f"Chapter {num}: {subtitle}" if subtitle else f"Chapter {num}"
                chapters.append({
                    "title": title,
                    "start_page": i,
                    "marker_page": i,
                    "type": "chapter",
                })

    # Validate: numbers should be roughly sequential
    if chapters:
        nums = [int(re.search(r'Chapter (\d+)', c["title"]).group(1)) for c in chapters]
        if nums == sorted(nums) and len(set(nums)) == len(nums):
            return chapters

    return []


def detect_sections_by_headers(pages: list[dict]) -> list[dict]:
    """
    For workbook-style books without traditional chapters.
    Detect section boundaries by ALL-CAPS headers on first line of pages.
    Only include headers that seem like major section breaks.
    """
    # First pass: collect all caps headers
    all_headers = []
    for i, page in enumerate(pages):
        text = page["stripped"]
        if not text:
            continue
        first_line = text.split("\n")[0].strip()

        if (first_line.isupper() and 5 < len(first_line) < 80
                and not re.match(r'^\d+$', first_line)
                and "OCEANOFPDF" not in first_line):
            all_headers.append({
                "title": first_line.title(),
                "start_page": i,
                "marker_page": i,
                "type": "section",
            })

    # If there are too many sections (> 25), keep only those that span
    # multiple pages or are clearly major sections
    if len(all_headers) > 25:
        major = []
        for j, h in enumerate(all_headers):
            next_page = all_headers[j + 1]["start_page"] if j + 1 < len(all_headers) else len(pages)
            span = next_page - h["start_page"]
            if span >= 2:  # Section spans at least 2 pages
                major.append(h)
        if len(major) >= 5:
            return major

    return all_headers


def detect_named_sections(pages: list[dict]) -> list[dict]:
    """Detect Foreword, Introduction, Epilogue, etc."""
    section_names = [
        "Foreword", "Preface", "Introduction", "Prologue",
        "Epilogue", "Afterword", "Conclusion", "Acknowledgments",
        "About the Author", "Appendix", "Notes", "References",
        "Bibliography", "Glossary", "Resources", "Dedication",
    ]
    sections = []
    for i, page in enumerate(pages):
        text = page["stripped"]
        if not text:
            continue
        first_line = text.split("\n")[0].strip()

        for name in section_names:
            if re.match(rf'^{name}\b', first_line, re.IGNORECASE):
                # Check if this is a standalone section header page or content page
                display_name = first_line if len(first_line) < 80 else name
                sections.append({
                    "title": display_name,
                    "start_page": i,
                    "marker_page": i,
                    "type": "named_section",
                })
                break

    return sections


def detect_sections_from_toc(pages: list[dict]) -> list[dict]:
    """
    For guidebooks: parse the TOC, then find each section title
    in the actual page content to determine start pages.
    """
    # Find the TOC page
    toc_page = None
    for page in pages[:10]:
        text = page["stripped"].lower()
        if "table of contents" in text or "contents" in text:
            toc_page = page
            break

    if not toc_page:
        return []

    # Extract section titles from TOC (lines that look like entries)
    toc_lines = toc_page["stripped"].split("\n")
    entries = []
    for line in toc_lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        # Skip the "Table of Contents" header itself
        if "contents" in line.lower() and len(line) < 25:
            continue
        # Remove trailing page numbers and dots
        cleaned = re.sub(r'\s*\.{2,}\s*\d+\s*$', '', line).strip()
        cleaned = re.sub(r'\s+\d+\s*$', '', cleaned).strip()
        if cleaned and 3 < len(cleaned) < 80:
            entries.append(cleaned)

    if len(entries) < 3:
        return []

    # Match each TOC entry to a page in the book
    sections = []
    for entry in entries:
        entry_words = set(entry.lower().split())
        entry_words -= {"the", "a", "an", "of", "and", "in", "to", "for", "is", "on", "your", "you"}

        best_page = None
        best_score = 0
        for page in pages[2:]:  # Skip first 2 pages
            first_line = page["stripped"].split("\n")[0].strip().lower() if page["stripped"] else ""
            first_words = set(first_line.split())
            first_words -= {"the", "a", "an", "of", "and", "in", "to", "for", "is", "on", "your", "you"}

            if not first_words:
                continue

            overlap = entry_words & first_words
            score = len(overlap) / max(len(entry_words), 1)

            if score > best_score and score > 0.5:
                best_score = score
                best_page = page["idx"]

        if best_page is not None:
            # Clean up title: remove leading page numbers
            clean_title = re.sub(r'^\d+\s+', '', entry).strip()
            sections.append({
                "title": clean_title or entry,
                "start_page": best_page,
                "marker_page": best_page,
                "type": "section",
            })

    # Deduplicate by page
    seen_pages = set()
    unique = []
    for s in sections:
        if s["start_page"] not in seen_pages:
            unique.append(s)
            seen_pages.add(s["start_page"])

    return unique


def detect_parts(pages: list[dict]) -> list[dict]:
    """Detect Part markers."""
    parts = []
    for i, page in enumerate(pages):
        text = page["stripped"]
        if not text:
            continue
        first_line = text.split("\n")[0].strip()

        match = re.match(r'^(?:PART|Part)\s+(\d+|[IVXLC]+)\s*[:\.]?\s*(.*?)$', first_line, re.IGNORECASE)
        if match:
            part_id = match.group(1)
            subtitle = match.group(2).strip()
            title = f"Part {part_id}: {subtitle}" if subtitle else f"Part {part_id}"
            parts.append({
                "title": title,
                "start_page": i,
                "marker_page": i,
                "type": "part",
            })

    return parts


# ---------------------------------------------------------------------------
# TOC parsing
# ---------------------------------------------------------------------------

def parse_toc(pages: list[dict], max_pages: int = 20) -> list[str]:
    """Parse table of contents from the first N pages."""
    toc_text = ""
    for page in pages[:max_pages]:
        text = page["stripped"].lower()
        if "contents" in text or "table of contents" in text:
            toc_text += page["stripped"] + "\n"
            # Also grab following pages that look like TOC continuation
            idx = page["idx"] + 1
            while idx < min(len(pages), page["idx"] + 5):
                next_text = pages[idx]["stripped"]
                # TOC pages tend to have many short lines or page numbers
                if next_text and (next_text.count("\n") > 5 or re.search(r'\d+\s*$', next_text)):
                    toc_text += next_text + "\n"
                else:
                    break
                idx += 1
            break

    entries = []
    for line in toc_text.split("\n"):
        line = line.strip()
        if not line or len(line) < 3:
            continue

        # "Chapter N: Title ... page" or "Chapter N: Title"
        ch_match = re.match(
            r'(?:Chapter\s+)?(\d+)[.:\s]+(.+?)(?:\s*\.{2,}\s*\d+|\s+\d+\s*$)?$',
            line, re.IGNORECASE
        )
        if ch_match:
            num = ch_match.group(1)
            title = ch_match.group(2).strip().rstrip('.')
            if title and len(title) > 1 and not title.isdigit():
                entries.append(f"Chapter {num}: {title}")

    return entries


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def extract_metadata(pages: list[dict]) -> dict:
    """Extract book metadata from the first few pages."""
    meta = {"title": "", "author": "", "publisher": "", "copyright": "", "isbn": "", "edition": ""}

    combined = "\n".join(p["stripped"] for p in pages[:12] if p["stripped"])

    # ISBN — try labeled first, then bare 978/979 patterns
    isbn_match = re.search(r'ISBN[:\s-]*(\d[\d-]{9,}[\dXx])', combined)
    if not isbn_match:
        isbn_match = re.search(r'\b(97[89][\d-]{10,}[\dXx])\b', combined)
    if isbn_match:
        meta["isbn"] = isbn_match.group(1)

    # Copyright
    copy_match = re.search(r'(?:Copyright\s*©?\s*|©\s*)(\d{4})', combined)
    if copy_match:
        meta["copyright"] = f"Copyright © {copy_match.group(1)}"

    # Publisher — look for "Published by <Name>" or "Publishing" on a line
    pub_match = re.search(
        r'(?:Published\s+by|Publisher[:\s])\s*(.+?)(?:\n|$)', combined, re.IGNORECASE
    )
    if pub_match:
        meta["publisher"] = pub_match.group(1).strip().rstrip('.,')
    else:
        for line in combined.split("\n"):
            s = line.strip()
            if re.search(r'\b(?:Publishing|Publishers|Press|Books)\b', s, re.IGNORECASE):
                if len(s) < 80 and not re.search(r'(?:may be purchased|available)', s, re.IGNORECASE):
                    meta["publisher"] = s
                    break

    # Author — look for "by <Name>" near the title (single line only)
    author_match = re.search(r'\bby\s+([A-Z][a-zA-Z.\- ,]+(?:MD|PhD|DO|DC|RD|MS|MPH|Jr|Sr)?\.?)\s*$',
                             combined[:2000], re.MULTILINE)
    if author_match:
        candidate = author_match.group(1).strip().rstrip(',.')
        # Reject if it looks like a sentence fragment rather than a name:
        # must have <=6 words, <80 chars, and at least 2 words (first + last)
        if (len(candidate) < 80
                and 2 <= candidate.count(' ') + 1 <= 6
                and not any(w in candidate.lower() for w in [
                    "chapter", "page", "section", "figure", "table", "atom",
                    "acid", "carbon", "types", "sources", "illustration",
                ])):
            meta["author"] = candidate

    # Title from first non-trivial page (skip disclaimers, legal text, OceanofPDF)
    skip_keywords = [
        "oceanofpdf", "the advice herein", "disclaimer", "all rights reserved",
        "thank you for downloading", "copyright", "isbn", "contents",
        "table of contents", "balance books", "for gregory", "dedication",
        "1 peter", "may be purchased",
    ]
    for page in pages[:10]:
        text = page["stripped"]
        if not text or page["chars"] < 5:
            continue
        first_line = text.split("\n")[0].strip()
        lower = first_line.lower()
        if any(kw in lower for kw in skip_keywords):
            continue
        if len(first_line) < 3:
            continue
        if not meta["title"]:
            meta["title"] = first_line
            break

    return meta


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def merge_and_sort_sections(
    chapters: list[dict],
    named_sections: list[dict],
    parts: list[dict],
    total_pages: int,
) -> list[dict]:
    """Merge all detected sections, deduplicate, sort by page."""
    all_sections = []
    used_pages = set()

    # Parts first (they're structural markers)
    for p in parts:
        all_sections.append(p)
        used_pages.add(p["start_page"])

    # Named sections (Foreword, Introduction, etc.)
    for s in named_sections:
        if s["start_page"] not in used_pages:
            all_sections.append(s)
            used_pages.add(s["start_page"])

    # Chapters
    for c in chapters:
        if c["start_page"] not in used_pages:
            all_sections.append(c)
            used_pages.add(c["start_page"])

    all_sections.sort(key=lambda s: s["start_page"])

    # Calculate end pages
    for i, section in enumerate(all_sections):
        if i + 1 < len(all_sections):
            next_marker = all_sections[i + 1]["marker_page"]
            section["end_page"] = next_marker - 1
        else:
            section["end_page"] = total_pages - 1

    return all_sections


def build_markdown(
    meta: dict,
    sections: list[dict],
    pages: list[dict],
    rendered_images: dict[int, str] | None = None,
) -> str:
    """Build the final Markdown output. If rendered_images is provided,
    insert <!-- IMAGE: path --> placeholders for pages that were rendered."""
    rendered_images = rendered_images or {}
    lines = []

    # Title block
    title = meta.get("title", "Unknown Title")
    lines.append(f"# {title}")
    lines.append("")

    if meta.get("author"):
        lines.append(f"**Author:** {meta['author']}")
    if meta.get("publisher"):
        lines.append(f"**Publisher:** {meta['publisher']}")
    if meta.get("copyright"):
        lines.append(f"**Copyright:** {meta['copyright']}")
    if meta.get("isbn"):
        lines.append(f"**ISBN:** {meta['isbn']}")
    if meta.get("edition"):
        lines.append(f"**Edition:** {meta['edition']}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Sections
    for section in sections:
        title = section["title"]

        # Part headers get ## Part N, chapters get ## Chapter N, etc.
        if section["type"] == "part":
            lines.append(f"## {title}")
        elif section["type"] in ("chapter", "named_section", "section"):
            lines.append(f"## {title}")

        lines.append("")

        # Extract text for this section's page range
        start = section["start_page"]
        end = min(section["end_page"], len(pages) - 1)

        section_text_parts = []
        for p_idx in range(start, end + 1):
            page = pages[p_idx]

            # If this page was rendered as an image, insert a placeholder
            if p_idx in rendered_images:
                img_path = rendered_images[p_idx]
                section_text_parts.append(
                    f"<!-- IMAGE: {img_path} | Page {p_idx + 1} — "
                    f"This page could not be extracted as text. "
                    f"Read the image and replace this placeholder with the content. -->"
                )
            elif page["chars"] > MIN_CHARS:
                cleaned = clean_page_text(page["stripped"])
                if cleaned.strip():
                    section_text_parts.append(cleaned)

        full_text = "\n\n".join(section_text_parts)

        # Remove the chapter/section header from the beginning of the text
        # to avoid duplication with the ## heading
        header_patterns = [
            rf'^(?:CHAPTER|Chapter)\s+\d+\s*[:\.]?\s*\n?',
            rf'^(?:PART|Part)\s+\d+\s*[:\.]?\s*\n?',
            rf'^{re.escape(section["title"])}\s*\n?',
        ]
        for pat in header_patterns:
            full_text = re.sub(pat, '', full_text, count=1, flags=re.IGNORECASE).strip()

        lines.append(full_text)
        lines.append("\n---\n")

    result = "\n".join(lines)

    # Clean up excessive blank lines
    result = re.sub(r'\n{4,}', '\n\n\n', result)

    return result


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: str,
    output_path: str = None,
    dry_run: bool = False,
    render_images: bool = False,
    images_dir: str = None,
) -> str:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting: {pdf_path.name}")
    pages = extract_all_pages(str(pdf_path))
    print(f"  Pages: {len(pages)}")

    # --- Strategy 1: Text markers (CHAPTER N / Chapter N:) ---
    chapters = detect_chapters_by_text_markers(pages)
    strategy = "text_markers"

    # --- Strategy 2: Single number chapters (e.g., Big Fat Surprise) ---
    if len(chapters) < 3:
        single_num = detect_chapters_by_single_number(pages)
        if len(single_num) > len(chapters):
            chapters = single_num
            strategy = "single_number"

    # --- Strategy 3: Section headers for workbook-style books ---
    if len(chapters) < 3:
        sections = detect_sections_by_headers(pages)
        if len(sections) >= 5:
            chapters = sections
            strategy = "section_headers"

    # --- Strategy 4: TOC-based sections for guidebooks ---
    if len(chapters) < 3:
        toc_sections = detect_sections_from_toc(pages)
        if len(toc_sections) >= 3:
            chapters = toc_sections
            strategy = "toc_sections"

    print(f"  Strategy: {strategy} ({len(chapters)} chapters/sections found)")

    # Detect named sections (Foreword, Introduction, etc.)
    named = detect_named_sections(pages)
    # Filter named sections that overlap with detected chapters
    chapter_pages = {c["start_page"] for c in chapters}
    named = [n for n in named if n["start_page"] not in chapter_pages]
    print(f"  Named sections: {len(named)}")

    # Detect parts
    parts = detect_parts(pages)
    print(f"  Parts: {len(parts)}")

    # Try to enrich chapter titles from TOC
    toc_entries = parse_toc(pages)
    if toc_entries:
        print(f"  TOC entries: {len(toc_entries)}")
        # Match TOC entries to detected chapters by number
        toc_map = {}
        for entry in toc_entries:
            m = re.match(r'Chapter (\d+): (.+)', entry)
            if m:
                toc_map[m.group(1)] = m.group(2)

        for ch in chapters:
            m = re.match(r'Chapter (\d+)', ch["title"])
            if m and m.group(1) in toc_map:
                ch["title"] = f"Chapter {m.group(1)}: {toc_map[m.group(1)]}"

    # Merge everything
    all_sections = merge_and_sort_sections(chapters, named, parts, len(pages))

    # Extract metadata
    meta = extract_metadata(pages)
    print(f"  Title: {meta['title']}")

    # Count image pages
    image_pages = [p for p in pages if p["chars"] < IMAGE_PAGE_THRESHOLD]
    if image_pages:
        print(f"  Image/empty pages: {len(image_pages)}")

    if dry_run:
        print(f"\n=== DRY RUN ===")
        for s in all_sections:
            end = min(s["end_page"], len(pages) - 1)
            print(f"  [{s['type']:14s}] Pages {s['start_page']+1:3d}-{end+1:3d}: {s['title']}")
        if image_pages and not render_images:
            print(f"\n  Tip: Use --render-images to render {len(image_pages)} "
                  f"image pages as PNGs for Claude Code to read.")
        return None

    # Render image pages if requested
    rendered_images = {}
    if render_images:
        if not images_dir:
            images_dir = Path(".tmp") / "extracted_images" / pdf_path.stem
        else:
            images_dir = Path(images_dir)
        rendered_images = render_image_pages(str(pdf_path), pages, images_dir)
        print(f"  Rendered {len(rendered_images)} pages as images to: {images_dir}")

    # Build markdown
    md = build_markdown(meta, all_sections, pages, rendered_images)

    # Determine output path
    if not output_path:
        output_path = pdf_path.with_suffix(".md")
    output_path = Path(output_path)
    output_path.write_text(md, encoding="utf-8")

    print(f"  Output: {output_path}")
    print(f"  Size: {len(md):,} chars")
    if rendered_images:
        print(f"  Placeholders: {len(rendered_images)} image pages need vision pass")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="Extract PDF book to structured Markdown")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--output", "-o", help="Output Markdown file path")
    parser.add_argument("--dry-run", action="store_true", help="Preview chapter detection without writing")
    parser.add_argument("--render-images", action="store_true",
                        help="Render image/empty pages as PNGs for Claude Code vision pass")
    parser.add_argument("--images-dir", help="Directory to save rendered page images "
                        "(default: .tmp/extracted_images/<book_name>)")
    args = parser.parse_args()
    process_pdf(args.pdf_path, args.output, args.dry_run, args.render_images, args.images_dir)


if __name__ == "__main__":
    main()
