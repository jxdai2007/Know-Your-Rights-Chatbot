"""
vector_db.py — ChromaDB indexing and retrieval with Gemini embeddings.

Loads chunks from data/processed/chunks.json, embeds them using
Google's gemini-embedding-001 model, and stores them in a persistent
ChromaDB collection for semantic search.
"""

import json
import os
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ── Config ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_FILE = BASE_DIR / "data" / "processed" / "chunks.json"
CHROMA_DIR = str(BASE_DIR / "chroma_db")
COLLECTION_NAME = "kyr_chunks"

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768  # 768/1536/3072 supported; 768 is fast + accurate enough
BATCH_SIZE = 50  # texts per API call (stay well under rate limits)
BATCH_DELAY = 2.0  # seconds between batches (free tier = 100 req/min)
MAX_RETRIES = 5  # retry attempts on rate-limit errors
INITIAL_BACKOFF = 60  # first retry wait in seconds (Gemini 429 needs ~60s)

# ── API setup ──────────────────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")

_client: genai.Client | None = None


def _get_genai_client() -> genai.Client:
    """Return a configured Gemini API client (singleton)."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY not set. Copy .env.example to .env and add your key."
        )
    _client = genai.Client(api_key=api_key)
    return _client


# ── Rate-limit retry helper ───────────────────────────────────────
def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception is a Gemini rate-limit (429 / RESOURCE_EXHAUSTED)."""
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "rate limit" in msg


def _call_with_retry(fn, *args, **kwargs):
    """Call fn with exponential backoff on rate-limit errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_rate_limit_error(exc):
                raise
            if attempt == MAX_RETRIES - 1:
                raise
            wait = INITIAL_BACKOFF * (2 ** attempt)
            print(
                f"  ⏳ Rate limit hit (attempt {attempt + 1}/{MAX_RETRIES}). "
                f"Waiting {wait}s before retry..."
            )
            time.sleep(wait)


# ── Embedding ──────────────────────────────────────────────────────
def embed_texts(
    texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT"
) -> list[list[float]]:
    """
    Embed a list of texts using Gemini embedding API in batches.

    Includes retry with exponential backoff for rate-limit errors
    and a configurable delay between batches.

    task_type should be:
      - "RETRIEVAL_DOCUMENT" when embedding chunks for storage
      - "RETRIEVAL_QUERY" when embedding a user question for search
    """
    client = _get_genai_client()
    all_embeddings: list[list[float]] = []

    total = len(texts)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    start_time = time.time()

    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        batch = texts[start:end]
        batch_num = start // BATCH_SIZE + 1

        print(
            f"  Batch {batch_num}/{total_batches}"
            f"  (chunks {start + 1}–{end} of {total})"
        )

        result = _call_with_retry(
            client.models.embed_content,
            model=EMBEDDING_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBEDDING_DIMENSIONS,
            ),
        )

        for emb in result.embeddings:
            all_embeddings.append(list(emb.values))

        elapsed = time.time() - start_time
        print(f"    ✓ {len(all_embeddings)}/{total} embedded ({elapsed:.1f}s elapsed)")

        # Delay between batches to stay under rate limits.
        if end < total:
            time.sleep(BATCH_DELAY)

    return all_embeddings


def embed_query(question: str) -> list[float]:
    """Embed a single query string for retrieval (with retry)."""
    client = _get_genai_client()
    result = _call_with_retry(
        client.models.embed_content,
        model=EMBEDDING_MODEL,
        contents=question,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    return list(result.embeddings[0].values)


# ── ChromaDB ─────────────────────────────────────────────────────
def _get_chroma_client() -> chromadb.ClientAPI:
    """Return a persistent ChromaDB client."""
    return chromadb.PersistentClient(path=CHROMA_DIR)


def _get_collection(client: chromadb.ClientAPI) -> chromadb.Collection:
    """Get or create the KYR chunks collection."""
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ── Setup (index all chunks) ────────────────────────────────────
def setup_vector_db() -> int:
    """
    Load chunks from chunks.json, embed them, and store in ChromaDB.
    Returns the number of chunks indexed.

    Safe to re-run: deletes and recreates the collection.
    """
    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {CHUNKS_FILE}\n"
            "Run process_documents.py first."
        )

    with open(CHUNKS_FILE, encoding="utf-8") as f:
        chunks = json.load(f)

    if not chunks:
        print("No chunks to index.")
        return 0

    print(f"Loaded {len(chunks)} chunks from {CHUNKS_FILE.name}")

    # Extract texts and metadata.
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    ids = [f"{m['doc_filename']}_{m['chunk_index']}" for m in metadatas]

    # Embed all texts.
    print("\nEmbedding chunks with Gemini...")
    embeddings = embed_texts(texts, task_type="RETRIEVAL_DOCUMENT")
    print(f"Generated {len(embeddings)} embeddings (dim={EMBEDDING_DIMENSIONS})")

    # Store in ChromaDB.
    print("\nStoring in ChromaDB...")
    client = _get_chroma_client()

    # Delete existing collection to avoid duplicates on re-run.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = _get_collection(client)

    # ChromaDB add() has its own internal batch limits.
    chroma_batch = 500
    for start in range(0, len(ids), chroma_batch):
        end = min(start + chroma_batch, len(ids))
        collection.add(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )

    print(f"Indexed {collection.count()} chunks in collection '{COLLECTION_NAME}'")
    return collection.count()


# ── Query ────────────────────────────────────────────────────────
def query_similar(
    question: str,
    n_results: int = 5,
    language: str | None = None,
) -> list[dict]:
    """
    Semantic search: embed the question and find the most similar chunks.

    Args:
        question: The user's question.
        n_results: Number of results to return.
        language: Optional filter ("en" or "es").

    Returns a list of dicts with keys: text, metadata, distance.
    """
    query_embedding = embed_query(question)

    client = _get_chroma_client()
    collection = _get_collection(client)

    where_filter = None
    if language:
        where_filter = {"language": language}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    # Unpack ChromaDB's nested list format into flat dicts.
    output: list[dict] = []
    if results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "text": doc,
                "metadata": meta,
                "distance": dist,
            })

    return output


def get_by_category(category: str) -> list[dict]:
    """
    Retrieve all chunks matching a specific category.

    Returns a list of dicts with keys: text, metadata.
    """
    client = _get_chroma_client()
    collection = _get_collection(client)

    results = collection.get(
        where={"category": category},
        include=["documents", "metadatas"],
    )

    output: list[dict] = []
    if results["documents"]:
        for doc, meta in zip(results["documents"], results["metadatas"]):
            output.append({"text": doc, "metadata": meta})

    return output


# ── Main ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("KYR Chatbot — Vector Database Setup")
    print("=" * 60)

    count = setup_vector_db()

    if count == 0:
        print("\nNo chunks indexed. Check data/processed/chunks.json.")
        raise SystemExit(1)

    # Quick test query.
    print("\n" + "-" * 60)
    print("Test query: 'What are my rights if ICE comes to my door?'")
    print("-" * 60)

    results = query_similar(
        "What are my rights if ICE comes to my door?", n_results=3
    )
    for i, r in enumerate(results):
        meta = r["metadata"]
        print(
            f"\n[{i + 1}] {meta['title']} ({meta['language']})"
            f" — distance: {r['distance']:.4f}"
        )
        print(
            f"    Category: {meta['category']}"
            f"  |  Chunk: {meta['chunk_index'] + 1}/{meta['total_chunks']}"
        )
        print(f"    {r['text'][:150]}...")

    # Test category filter.
    print("\n" + "-" * 60)
    ice_chunks = get_by_category("ICE Encounters")
    print(f"get_by_category('ICE Encounters'): {len(ice_chunks)} chunks")

    police_chunks = get_by_category("Police Rights")
    print(f"get_by_category('Police Rights'): {len(police_chunks)} chunks")

    print("\n" + "=" * 60)
    print("Vector database ready.")
    print("=" * 60)
