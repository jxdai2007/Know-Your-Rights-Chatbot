"""
rag_engine.py — Core RAG query pipeline.

Accepts a user question (English or Spanish), retrieves relevant chunks
from the vector database, builds a grounded prompt, and calls Gemini 2.0
Flash to generate a cited, safe answer.
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Import query_similar — works both as `python src/rag_engine.py` and
# as `from src.rag_engine import ...`.
try:
    from src.vector_db import query_similar
except ImportError:
    from vector_db import query_similar

# ── Config ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GENERATION_MODEL = "gemini-2.0-flash"
VALID_LANGUAGES = {"en", "es"}
MAX_RETRIES = 5
INITIAL_BACKOFF = 0  # seconds; Gemini 429 needs ~60s cool-down

# Distance threshold — chunks farther than this are likely irrelevant.
# Cosine distance: 0 = identical, 2 = opposite.  Good matches < 0.5.
MAX_DISTANCE = 0.75

# ── API client (singleton) ────────────────────────────────────────
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


# ── Rate-limit retry ──────────────────────────────────────────────
def _is_rate_limit_error(exc: Exception) -> bool:
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
                f"  Rate limit hit (attempt {attempt + 1}/{MAX_RETRIES}). "
                f"Waiting {wait}s before retry..."
            )
            time.sleep(wait)


# ── Prompt template ────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are an immigration rights information assistant providing accurate, \
empathetic guidance based on verified sources from the American Civil \
Liberties Union (ACLU).

CRITICAL RULES:
1. Answer ONLY using the provided context below.
2. If the message is a greeting or introductory message (like "hi", \
"hello", "hey", "hola", etc.), respond with a friendly greeting and \
briefly explain that you are an immigration rights assistant that can \
help with ICE encounters, police stops, protest rights, and voting rights \
based on ACLU sources. Do NOT cite any sources in this case.
3. If the question is NOT about immigration rights, police encounters, \
protests, or voting rights, respond EXACTLY with: "This isn't something \
I'm designed to help with. I only provide immigration rights information \
based on ACLU sources. For other questions, try a general-purpose AI \
assistant." Do NOT cite any sources in this case.
4. If the question IS about immigration rights but the provided context \
does not contain a relevant answer, respond EXACTLY with: "I don't have \
verified information about that specific question. For personalized legal \
advice, please consult with a qualified immigration attorney." Do NOT \
cite any sources in this case.
5. When you DO have a relevant answer, cite your sources by mentioning \
"According to ACLU..." or referencing the source title.
6. NEVER provide legal advice — you provide information only.
7. Encourage users to consult with immigration attorneys for their \
specific situation.
8. Be empathetic, clear, and supportive in tone.
9. If responding in Spanish, maintain the same guidelines."""

USER_PROMPT_TEMPLATE = """\
VERIFIED CONTEXT:
{context}

USER QUESTION: {question}

Provide a clear, accurate answer with source citations:"""

NO_CONTEXT_REPLY_EN = (
    "I don't have verified information about that specific question. "
    "For personalized legal advice, please consult with a qualified "
    "immigration attorney."
)
NO_CONTEXT_REPLY_ES = (
    "No tengo informacion verificada sobre esa pregunta especifica. "
    "Para obtener asesoramiento legal personalizado, consulte con un "
    "abogado de inmigracion calificado."
)

OFF_TOPIC_REPLY_EN = (
    "This isn't something I'm designed to help with. I only provide "
    "immigration rights information based on ACLU sources. For other "
    "questions, try a general-purpose AI assistant."
)
OFF_TOPIC_REPLY_ES = (
    "Esto no es algo para lo que estoy diseñado. Solo proporciono "
    "información sobre derechos de inmigración basada en fuentes de la ACLU. "
    "Para otras preguntas, pruebe un asistente de IA de propósito general."
)


# ── Context formatting ─────────────────────────────────────────────
def _build_context(results: list[dict]) -> str:
    """Format retrieved chunks into a numbered context block."""
    sections: list[str] = []
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        header = (
            f"[Source {i}: {meta['title']} — "
            f"{meta['category']} ({meta['language'].upper()})]"
        )
        sections.append(f"{header}\n{r['text']}")
    return "\n\n---\n\n".join(sections)


def _format_sources(results: list[dict]) -> list[dict]:
    """Extract source metadata for citation display (deduplicated by title)."""
    seen_titles: set[str] = set()
    sources: list[dict] = []
    for r in results:
        meta = r["metadata"]
        title = meta["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)
        sources.append({
            "title": title,
            "category": meta["category"],
            "language": meta["language"],
            "url": meta.get("url", ""),
            "excerpt": r["text"][:150] + "...",
        })
    return sources


# ── Core pipeline ──────────────────────────────────────────────────
def answer_question(
    question: str,
    language: str = "en",
    n_results: int = 5,
    system_prompt: str | None = None,
    max_output_tokens: int = 1024,
) -> tuple[str, list[dict]]:
    """
    End-to-end RAG pipeline: retrieve context, generate answer.

    Args:
        question:          The user's question.
        language:          "en" or "es" — filters chunks and selects fallback reply.
        n_results:         Number of chunks to retrieve from the vector DB.
        system_prompt:     Override the default system prompt (e.g. for WhatsApp).
        max_output_tokens: Max tokens in the generated response.

    Returns:
        (answer_text, sources_list)
        where sources_list contains dicts with title, category, language,
        url, and excerpt keys.
    """
    # ── 1. Validate language ──────────────────────────────────────
    if language not in VALID_LANGUAGES:
        language = "en"

    # ── 2. Retrieve relevant chunks ───────────────────────────────
    results = query_similar(question, n_results=n_results, language=language)

    # Filter out chunks that are too far away (likely irrelevant).
    results = [r for r in results if r["distance"] <= MAX_DISTANCE]

    if not results:
        off = OFF_TOPIC_REPLY_ES if language == "es" else OFF_TOPIC_REPLY_EN
        return off, []

    # ── 3. Build prompt ───────────────────────────────────────────
    context = _build_context(results)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        context=context, question=question,
    )

    # ── 4. Call Gemini ────────────────────────────────────────────
    client = _get_genai_client()

    response = _call_with_retry(
        client.models.generate_content,
        model=GENERATION_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt or SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=max_output_tokens,
        ),
    )

    answer = response.text or (
        NO_CONTEXT_REPLY_ES if language == "es" else NO_CONTEXT_REPLY_EN
    )

    # ── 5. Format sources ─────────────────────────────────────────
    sources = _format_sources(results)

    return answer, sources


# ── Main (quick test) ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("KYR Chatbot — RAG Engine Test")
    print("=" * 60)

    test_questions = [
        ("What are my rights if ICE comes to my door?", "en"),
        ("Do I have to show ID to police?", "en"),
        ("Cuales son mis derechos si me detiene la policia?", "es"),
    ]

    for q, lang in test_questions:
        print(f"\n{'─' * 60}")
        print(f"Q ({lang}): {q}")
        print("─" * 60)

        start = time.time()
        answer, sources = answer_question(q, language=lang)
        elapsed = time.time() - start

        print(f"\nAnswer ({elapsed:.1f}s):\n{answer}")
        if sources:
            print(f"\nSources ({len(sources)}):")
            for s in sources:
                print(f"  - {s['title']} [{s['category']}] ({s['language']})")
                print(f"    {s['url']}")
