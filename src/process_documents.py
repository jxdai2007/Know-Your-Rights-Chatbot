"""
process_documents.py — Clean, chunk, and prepare documents for embedding.

Reads extracted .txt files from data/raw/, strips PDF artifacts,
splits into overlapping chunks, auto-detects categories, and saves
structured JSON to data/processed/chunks.json.
"""

import json
import os
import re
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"
CHUNKS_FILE = DATA_PROCESSED_DIR / "chunks.json"

# ── Chunking parameters ──────────────────────────────────────────
CHUNK_MIN = 800
CHUNK_MAX = 1200
CHUNK_OVERLAP = 200

# ── ACLU source URL mapping (slug prefix → URL) ─────────────────
SOURCE_URLS = {
    "immigrants_rights": "https://www.aclu.org/know-your-rights/immigrants-rights",
    "stopped_by_police": "https://www.aclu.org/know-your-rights/stopped-by-police",
    "protesters_rights": "https://www.aclu.org/know-your-rights/protesters-rights",
    "voting_rights": "https://www.aclu.org/know-your-rights/voting-rights",
    "100_mile_border_zone": "https://www.aclu.org/know-your-rights/border-zone",
    "federal_agents_at_the_polls": "https://www.aclu.org/know-your-rights/federal-agents-polls",
    "derechos_de_los_inmigrantes": "https://www.aclu.org/know-your-rights/derechos-de-los-inmigrantes",
    "que_debe_hacer_si_la_policia": "https://www.aclu.org/know-your-rights/stopped-by-police",
    "derechos_de_los_manifestantes": "https://www.aclu.org/know-your-rights/protesters-rights",
    "derecho_al_voto": "https://www.aclu.org/know-your-rights/voting-rights",
    "agentes_federales_en_los_centros_de_votacion": "https://www.aclu.org/know-your-rights/federal-agents-polls",
}

# ── Category detection keywords ─────────────────────────────────
# Matched against title + body text (case-insensitive).
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("ICE Encounters", [
        "ice", "immigra", "inmigra", "border", "frontera", "deporta",
        "cbp", "detain", "deten", "removal",
    ]),
    ("Police Rights", [
        "police", "policía", "policia", "stopped by",
        "law enforcement", "officer", "patrol",
    ]),
    ("Protest Rights", [
        "protest", "manifestante", "demonstrat", "first amendment",
        "free speech", "assembly",
    ]),
    ("Voting Rights", [
        "vot", "poll", "elect", "ballot",
        "centros de votación", "derecho al voto",
    ]),
]


# ── Parsing ──────────────────────────────────────────────────────
def load_raw_document(path: Path) -> tuple[dict, str]:
    """
    Parse a raw .txt file. Returns (metadata_dict, body_text).
    Expects the ---METADATA--- / ---END METADATA--- block format
    produced by data_collection.py.
    """
    text = path.read_text(encoding="utf-8")

    meta_match = re.search(
        r"---METADATA---\n(.+?)\n---END METADATA---",
        text,
        re.DOTALL,
    )
    if not meta_match:
        raise ValueError(f"No metadata block found in {path}")

    metadata = json.loads(meta_match.group(1))
    body = text[meta_match.end():].strip()
    return metadata, body


# ── Additional text cleaning (PDF artifacts) ─────────────────────

# Page-header PREFIX on each page-line:
#   "2/7/26, 12:16 PM Stopped by Police | American Civil Liberties Union "
_PAGE_HEADER_PREFIX_RE = re.compile(
    r"\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}\s*(?:AM|PM)?\s+"
    r"[^\n]*?American Civil Liberties Union\s*",
    re.IGNORECASE,
)

# Page-footer SUFFIX at end of each page-line:
#   "https://www.aclu.org/know-your-rights/stopped-by-police 2/6"
_PAGE_FOOTER_SUFFIX_RE = re.compile(
    r"\s*https?://\S+\s+\d+/\d+\s*$",
    re.MULTILINE,
)

# Issue/date metadata line embedded in text:
#   "Issue: Immigrants' Rights Last Updated: September 3, 2025"
_ISSUE_LINE_RE = re.compile(
    r"Issue:\s+.*?Last Updated:\s+\w+\s+\d{1,2},\s+\d{4}\s*",
)

# "In other languages ..." blocks with non-Latin script names.
_OTHER_LANGUAGES_RE = re.compile(
    r"In other languages\s*\(.*?\)[\s\S]*?(?=\s[A-Z][a-z]|\n\n|$)",
)

# Boilerplate strings to remove.
_BOILERPLATE = [
    "KNOW YOUR RIGHTS",
    "\u00a9 2026 American Civil Liberties Union",
    "\u00a9 2025 American Civil Liberties Union",
]


def clean_body(text: str) -> str:
    """Remove PDF print artifacts that survived initial extraction."""
    # Strip page-header prefixes (date/time + title bar).
    text = _PAGE_HEADER_PREFIX_RE.sub("", text)
    # Strip page-footer suffixes (URL + page numbers).
    text = _PAGE_FOOTER_SUFFIX_RE.sub("", text)
    # Strip "Issue: ... Last Updated: ..." metadata.
    text = _ISSUE_LINE_RE.sub("", text)
    # Strip "In other languages ..." blocks.
    text = _OTHER_LANGUAGES_RE.sub("", text)
    # Strip boilerplate strings.
    for bp in _BOILERPLATE:
        text = text.replace(bp, "")
    # Collapse excessive whitespace.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ── Category detection ───────────────────────────────────────────
def detect_category(title: str, body: str) -> str:
    """
    Auto-detect document category from title and body keywords.
    Title matches are weighted 3x to prioritize document subject.
    """
    title_lower = title.lower()
    body_lower = body[:500].lower()

    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_RULES:
        title_hits = sum(3 for kw in keywords if kw in title_lower)
        body_hits = sum(1 for kw in keywords if kw in body_lower)
        score = title_hits + body_hits
        if score > 0:
            scores[category] = score

    if not scores:
        return "General"
    return max(scores, key=scores.get)


# ── URL lookup ───────────────────────────────────────────────────
def get_source_url(filename: str) -> str:
    """Map a raw .txt filename to its ACLU source URL."""
    # Strip language prefix and .txt: "en_immigrants_rights.txt" -> "immigrants_rights"
    stem = Path(filename).stem
    # Remove en_ or es_ prefix
    if stem.startswith(("en_", "es_")):
        key = stem[3:]
    else:
        key = stem

    return SOURCE_URLS.get(key, "https://www.aclu.org/know-your-rights")


# ── Clean title ──────────────────────────────────────────────────
def clean_title(title: str) -> str:
    """Strip the org suffix from the title for display."""
    for sep in (" | American Civil Liberties Union", " _ American Civil Liberties Union"):
        if title.endswith(sep):
            return title[: -len(sep)]
    return title


# ── Chunking ─────────────────────────────────────────────────────
def chunk_text(text: str) -> list[str]:
    """
    Split text into overlapping chunks of CHUNK_MIN–CHUNK_MAX characters.

    Strategy:
      1. Split on paragraph boundaries (double newlines).
      2. Accumulate paragraphs until the chunk reaches CHUNK_MIN.
      3. If adding the next paragraph would exceed CHUNK_MAX, finalize the chunk.
      4. For overlap, the next chunk starts CHUNK_OVERLAP characters before
         the end of the previous chunk, snapping to a word boundary.
      5. Single paragraphs longer than CHUNK_MAX are split at sentence
         boundaries, then at word boundaries as a last resort.
    """
    paragraphs = re.split(r"\n{2,}", text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # If paragraph alone exceeds CHUNK_MAX, split it further.
        if len(para) > CHUNK_MAX:
            if current:
                chunks.append(current.strip())
                current = _overlap_start(current)
            for sub in _split_long_paragraph(para):
                if len(current) + len(sub) + 1 > CHUNK_MAX and len(current) >= CHUNK_MIN:
                    chunks.append(current.strip())
                    current = _overlap_start(current)
                current = f"{current}\n{sub}".strip() if current else sub
            continue

        combined = f"{current}\n\n{para}".strip() if current else para

        if len(combined) <= CHUNK_MAX:
            current = combined
        else:
            # Current chunk is full — finalize it.
            if current:
                chunks.append(current.strip())
            current = _overlap_start(current) + "\n\n" + para
            current = current.strip()

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _overlap_start(text: str) -> str:
    """
    Return the last CHUNK_OVERLAP characters of text, snapped to
    a word boundary, for use as the start of the next chunk.
    """
    if len(text) <= CHUNK_OVERLAP:
        return text
    overlap = text[-CHUNK_OVERLAP:]
    # Snap to word boundary (skip partial word at the start).
    space_idx = overlap.find(" ")
    if space_idx != -1 and space_idx < len(overlap) // 2:
        overlap = overlap[space_idx + 1:]
    return overlap


def _split_long_paragraph(para: str) -> list[str]:
    """Split a paragraph that exceeds CHUNK_MAX at sentence boundaries.
    Targets CHUNK_MAX - CHUNK_OVERLAP so overlap can be added later."""
    target = CHUNK_MAX - CHUNK_OVERLAP
    sentences = re.split(r"(?<=[.!?])\s+", para)
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > target:
            # Last resort: split at word boundaries.
            if current:
                pieces.append(current.strip())
                current = ""
            words = sentence.split()
            buf = ""
            for word in words:
                test = f"{buf} {word}".strip()
                if len(test) > target and buf:
                    pieces.append(buf)
                    buf = word
                else:
                    buf = test
            if buf:
                pieces.append(buf)
            continue

        test = f"{current} {sentence}".strip()
        if len(test) > target and current:
            pieces.append(current.strip())
            current = sentence
        else:
            current = test

    if current.strip():
        pieces.append(current.strip())

    return pieces


# ── Main pipeline ────────────────────────────────────────────────
def process_all() -> list[dict]:
    """
    Load all raw documents, clean, chunk, and return a list of
    chunk dicts ready for embedding.
    """
    raw_files = sorted(DATA_RAW_DIR.glob("*.txt"))
    if not raw_files:
        print("No .txt files found in data/raw/")
        return []

    print(f"Found {len(raw_files)} raw documents.\n")
    all_chunks: list[dict] = []

    for raw_path in raw_files:
        filename = raw_path.name
        print(f"Processing: {filename}")

        try:
            metadata, body = load_raw_document(raw_path)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"  [ERROR] {exc}")
            continue

        body = clean_body(body)
        if not body:
            print("  [WARN] Empty after cleaning. Skipping.")
            continue

        title = clean_title(metadata.get("title", filename))
        language = metadata.get("language", "en")
        source_url = get_source_url(filename)
        category = detect_category(title, body)

        chunks = chunk_text(body)
        print(f"  Title: {title}")
        print(f"  Category: {category}  |  Language: {language}  |  Chunks: {len(chunks)}")

        for i, chunk_text_content in enumerate(chunks):
            all_chunks.append({
                "text": chunk_text_content,
                "metadata": {
                    "source": "ACLU",
                    "title": title,
                    "language": language,
                    "category": category,
                    "url": source_url,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "doc_filename": filename,
                },
            })

    return all_chunks


def save_chunks(chunks: list[dict]) -> str:
    """Save chunks to data/processed/chunks.json."""
    os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)
    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    return str(CHUNKS_FILE)


def print_summary(chunks: list[dict]) -> None:
    """Print processing statistics."""
    if not chunks:
        print("\nNo chunks produced.")
        return

    # Collect stats.
    categories: dict[str, int] = {}
    languages: dict[str, int] = {}
    docs: set[str] = set()
    char_lengths: list[int] = []

    for chunk in chunks:
        meta = chunk["metadata"]
        categories[meta["category"]] = categories.get(meta["category"], 0) + 1
        languages[meta["language"]] = languages.get(meta["language"], 0) + 1
        docs.add(meta["doc_filename"])
        char_lengths.append(len(chunk["text"]))

    avg_len = sum(char_lengths) / len(char_lengths)

    print(f"\nTotal chunks: {len(chunks)}")
    print(f"From {len(docs)} documents")
    print(f"\nChunk sizes (chars):  Min: {min(char_lengths)}  Max: {max(char_lengths)}  Avg: {avg_len:.0f}")
    print(f"\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")
    print(f"\nBy language:")
    for lang, count in sorted(languages.items()):
        print(f"  {lang}: {count}")


if __name__ == "__main__":
    print("=" * 60)
    print("KYR Chatbot — Document Processing & Chunking")
    print("=" * 60)

    chunks = process_all()

    if chunks:
        path = save_chunks(chunks)
        print(f"\nSaved to: {path}")

    print("\n" + "=" * 60)
    print_summary(chunks)
    print("=" * 60)
