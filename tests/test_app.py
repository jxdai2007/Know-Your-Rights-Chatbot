"""
test_app.py — Smoke tests for the KYR chatbot pipeline.

Run:  python tests/test_app.py
"""

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

passed = 0
failed = 0


def report(name: str, ok: bool, detail: str = ""):
    global passed, failed
    tag = "PASS" if ok else "FAIL"
    passed += ok
    failed += (not ok)
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))


# ── 1. Vector DB loads ────────────────────────────────────────────
print("\n=== Vector DB ===")
try:
    from src.vector_db import _get_chroma_client, _get_collection, COLLECTION_NAME

    client = _get_chroma_client()
    collection = _get_collection(client)
    count = collection.count()
    report("Collection exists", count > 0, f"{count} chunks")
    report("Has enough chunks", count >= 100, f"expected 100+, got {count}")
except Exception as exc:
    report("Vector DB loads", False, str(exc))

# ── 2. RAG engine — English ──────────────────────────────────────
print("\n=== RAG Engine (English) ===")
try:
    from src.rag_engine import answer_question

    en_questions = [
        "What are my rights if ICE comes to my door?",
        "Do I have to show ID to police?",
        "What should I do if I am arrested?",
    ]
    for q in en_questions:
        start = time.time()
        answer, sources = answer_question(q, language="en", n_results=5)
        elapsed = time.time() - start

        has_answer = len(answer) > 50
        has_sources = len(sources) > 0
        reasonable_time = elapsed < 30

        report(
            f"EN: {q[:50]}...",
            has_answer and has_sources and reasonable_time,
            f"{len(answer)} chars, {len(sources)} sources, {elapsed:.1f}s",
        )
        time.sleep(1)  # Rate-limit courtesy.
except Exception as exc:
    report("RAG English pipeline", False, str(exc))

# ── 3. RAG engine — Spanish ──────────────────────────────────────
print("\n=== RAG Engine (Spanish) ===")
try:
    es_questions = [
        "\u00bfCu\u00e1les son mis derechos si ICE viene a mi puerta?",
        "\u00bfQu\u00e9 debo hacer si me detiene la polic\u00eda?",
    ]
    for q in es_questions:
        start = time.time()
        answer, sources = answer_question(q, language="es", n_results=5)
        elapsed = time.time() - start

        has_answer = len(answer) > 50
        report(
            f"ES: {q[:50]}...",
            has_answer,
            f"{len(answer)} chars, {len(sources)} sources, {elapsed:.1f}s",
        )
        time.sleep(1)
except Exception as exc:
    report("RAG Spanish pipeline", False, str(exc))

# ── 4. Off-topic question handling ───────────────────────────────
print("\n=== Off-Topic Handling ===")
try:
    off_topic = [
        "What's the weather today?",
        "Tell me a joke",
        "How do I bake a cake?",
    ]
    for q in off_topic:
        answer, sources = answer_question(q, language="en", n_results=5)
        # Should either return the fallback message or mention "don't have" / "attorney".
        is_safe = (
            "don't have" in answer.lower()
            or "attorney" in answer.lower()
            or "verified information" in answer.lower()
            or len(sources) == 0
        )
        report(f"Off-topic: {q}", is_safe, f"sources={len(sources)}")
        time.sleep(1)
except Exception as exc:
    report("Off-topic handling", False, str(exc))

# ── 5. Source format validation ──────────────────────────────────
print("\n=== Source Format ===")
try:
    answer, sources = answer_question(
        "What are my rights if ICE comes to my door?", language="en"
    )
    if sources:
        s = sources[0]
        has_title = bool(s.get("title"))
        has_category = bool(s.get("category"))
        has_language = s.get("language") in ("en", "es")
        has_url = s.get("url", "").startswith("http")
        has_excerpt = len(s.get("excerpt", "")) > 20
        report("title field", has_title, s.get("title", "")[:40])
        report("category field", has_category, s.get("category"))
        report("language field", has_language, s.get("language"))
        report("url field", has_url, s.get("url", "")[:50])
        report("excerpt field", has_excerpt, f"{len(s.get('excerpt', ''))} chars")
    else:
        report("Sources returned", False, "empty list")
except Exception as exc:
    report("Source format", False, str(exc))

# ── Summary ──────────────────────────────────────────────────────
print(f"\n{'=' * 50}")
total = passed + failed
print(f"Results: {passed}/{total} passed, {failed} failed")
print("=" * 50)
sys.exit(1 if failed else 0)
