"""
data_collection.py — Extract text from KYR PDF documents.

Reads PDFs from data/pdfs/english/ and data/pdfs/spanish/,
extracts text, cleans it, and saves to data/raw/ as .txt files
with embedded metadata blocks.
"""

import json
import logging
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Suppress noisy pdfminer font warnings (harmless FontBBox parsing messages).
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIRS = {
    "en": BASE_DIR / "data" / "pdfs" / "english",
    "es": BASE_DIR / "data" / "pdfs" / "spanish",
}
DATA_RAW_DIR = BASE_DIR / "data" / "raw"

ORGANIZATION_SUFFIX = " _ American Civil Liberties Union"
LOW_WORD_THRESHOLD = 100


# ── Discovery ─────────────────────────────────────────────────────
def discover_pdfs() -> list[dict]:
    """
    Scan PDF_DIRS and return a list of dicts:
      {path: Path, language: str, filename: str}

    English files listed first, then Spanish, alphabetical within each.
    """
    results: list[dict] = []
    for lang in ("en", "es"):
        pdf_dir = PDF_DIRS[lang]
        if not pdf_dir.exists():
            print(f"  [WARN] Directory not found: {pdf_dir}")
            continue
        for pdf_path in sorted(pdf_dir.glob("*.pdf")):
            if pdf_path.name.startswith("."):
                continue
            results.append(
                {"path": pdf_path, "language": lang, "filename": pdf_path.name}
            )
    return results


# ── Slug generation ───────────────────────────────────────────────
def generate_slug(filename: str, language: str) -> str:
    """
    Convert a PDF filename into a filesystem-safe slug.

    "Immigrants' Rights _ American Civil Liberties Union.pdf", "en"
    -> "en_immigrants_rights"
    """
    name = filename
    # Strip .pdf
    if name.lower().endswith(".pdf"):
        name = name[: -len(".pdf")]
    # Strip organization suffix (use rsplit to handle titles with underscores)
    if ORGANIZATION_SUFFIX in name:
        name = name.rsplit(ORGANIZATION_SUFFIX, 1)[0]
    # Transliterate Unicode to ASCII (á -> a, ñ -> n, etc.)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    # Replace non-alphanumeric with underscores
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    return f"{language}_{name}"


# ── Title extraction ──────────────────────────────────────────────
def extract_title(pdf_path: Path, filename: str) -> str:
    """
    Extract a readable title from PDF metadata, falling back to filename.
    """
    # Try pdfplumber metadata first.
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            meta_title = (pdf.metadata or {}).get("Title", "")
            if meta_title and len(meta_title) >= 3 and not meta_title.startswith("http"):
                return meta_title.strip()
    except Exception:
        pass

    # Fallback: derive from filename.
    name = filename
    if name.lower().endswith(".pdf"):
        name = name[: -len(".pdf")]
    if ORGANIZATION_SUFFIX in name:
        name = name.rsplit(ORGANIZATION_SUFFIX, 1)[0]
    return name.strip()


# ── PDF text extraction ──────────────────────────────────────────
def extract_text_with_pdfplumber(pdf_path: Path) -> str | None:
    """Extract text from all pages using pdfplumber. Returns None on failure."""
    try:
        import pdfplumber
    except ImportError:
        return None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages) if pages else None
    except Exception as exc:
        print(f"  [WARN] pdfplumber failed: {exc}")
        return None


def extract_text_with_pypdf2(pdf_path: Path) -> str | None:
    """Fallback text extraction using PyPDF2. Returns None on failure."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages) if pages else None
    except Exception as exc:
        print(f"  [WARN] PyPDF2 failed: {exc}")
        return None


def extract_text_from_pdf(pdf_path: Path) -> str | None:
    """Try pdfplumber first, fall back to PyPDF2."""
    text = extract_text_with_pdfplumber(pdf_path)
    if text:
        print("  Extracted with pdfplumber.")
        return text

    text = extract_text_with_pypdf2(pdf_path)
    if text:
        print("  Extracted with PyPDF2 (fallback).")
        return text

    return None


# ── Text cleaning ────────────────────────────────────────────────
def _strip_repeated_lines(text: str, min_repeats: int = 3, max_line_len: int = 80) -> str:
    """Remove short lines that appear many times (page headers/footers)."""
    lines = text.split("\n")
    counts: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) <= max_line_len:
            counts[stripped] += 1

    repeated = {line for line, count in counts.items() if count >= min_repeats}
    if not repeated:
        return text

    filtered = [line for line in lines if line.strip() not in repeated]
    return "\n".join(filtered)


def clean_text(raw_text: str) -> str:
    """
    Clean PDF-extracted text.

    Pipeline (order matters):
      1. Remove non-printable control chars (keep Unicode text)
      2. Rejoin hyphenated line breaks
      3. Collapse single newlines to spaces (paragraph wraps)
      4. Normalize horizontal whitespace
      5. Strip repeated header/footer lines
      6. Remove standalone page numbers and "Page X of Y"
      7. Collapse excessive blank lines
      8. Final strip
    """
    text = raw_text

    # 1. Remove non-printable control chars (keep \n, \t, and all Unicode text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 2. Rejoin hyphenated words split across lines
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # 3. Collapse single newlines to spaces (preserve paragraph breaks)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    # 4. Normalize horizontal whitespace
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 5. Strip repeated lines (headers/footers)
    text = _strip_repeated_lines(text)

    # 6. Remove standalone page numbers and "Page X of Y" patterns
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*Page\s+\d+\s*(of\s+\d+)?\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # 7. Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 8. Final strip
    text = text.strip()

    return text


# ── Save ─────────────────────────────────────────────────────────
def save_document(
    slug: str,
    source_path: str,
    title: str,
    body: str,
    language: str,
    filename: str,
) -> str:
    """Write extracted document to data/raw/<slug>.txt with metadata header."""
    os.makedirs(DATA_RAW_DIR, exist_ok=True)

    metadata = {
        "source": source_path,
        "title": title,
        "language": language,
        "filename": filename,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extractor": "data_collection.py",
    }

    path = os.path.join(DATA_RAW_DIR, f"{slug}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---METADATA---\n{json.dumps(metadata, indent=2)}\n---END METADATA---\n\n")
        f.write(body)

    return path


# ── Main pipeline ────────────────────────────────────────────────
def extract_all() -> tuple[list[str], dict[str, int]]:
    """
    Discover all PDFs, extract text, clean, and save.
    Returns (saved_paths, word_counts_by_filename).
    """
    pdfs = discover_pdfs()
    if not pdfs:
        print("No PDF files found in data/pdfs/")
        return [], {}

    print(f"Found {len(pdfs)} PDF files.\n")
    saved: list[str] = []
    word_counts: dict[str, int] = {}

    for i, pdf_info in enumerate(pdfs):
        pdf_path = pdf_info["path"]
        language = pdf_info["language"]
        filename = pdf_info["filename"]

        print(f"[{i + 1}/{len(pdfs)}] {filename}  ({language})")

        try:
            title = extract_title(pdf_path, filename)
            print(f"  Title: {title}")

            raw_text = extract_text_from_pdf(pdf_path)
            if not raw_text:
                print("  [ERROR] No text extracted. Skipping.")
                continue

            body = clean_text(raw_text)
            if not body.strip():
                print("  [WARN] Text was empty after cleaning. Skipping.")
                continue

            slug = generate_slug(filename, language)
            rel_path = str(pdf_path.relative_to(BASE_DIR))
            path = save_document(slug, rel_path, title, body, language, filename)

            wc = len(body.split())
            word_counts[filename] = wc
            if wc < LOW_WORD_THRESHOLD:
                print(f"  [WARN] Only {wc} words extracted (expected 500+).")
            print(f"  Saved: {path}  ({wc} words)")
            saved.append(path)

        except Exception as exc:
            print(f"  [ERROR] Failed to process {filename}: {exc}")
            continue

    return saved, word_counts


def print_summary(saved: list[str], total: int, word_counts: dict[str, int]) -> None:
    """Print extraction summary with word count statistics."""
    print(f"\nDone. {len(saved)}/{total} documents saved to data/raw/.")

    if not word_counts:
        return

    counts = list(word_counts.values())
    avg = sum(counts) / len(counts)
    print(f"\nWord count stats:")
    print(f"  Min: {min(counts)}  Max: {max(counts)}  Avg: {avg:.0f}")

    low = {name: wc for name, wc in word_counts.items() if wc < LOW_WORD_THRESHOLD}
    if low:
        print(f"\n  [!] {len(low)} document(s) with < {LOW_WORD_THRESHOLD} words:")
        for name, wc in low.items():
            print(f"      {name}: {wc} words")

    if len(saved) < total:
        print(
            "\nSome PDFs failed or returned empty content.\n"
            "Check the errors above and verify the PDF files are valid."
        )


if __name__ == "__main__":
    print("=" * 60)
    print("KYR Chatbot — PDF Text Extraction")
    print("=" * 60)

    saved, word_counts = extract_all()
    total = sum(1 for d in PDF_DIRS.values() if d.exists() for _ in d.glob("*.pdf"))

    print("\n" + "=" * 60)
    print_summary(saved, total, word_counts)
    print("=" * 60)
