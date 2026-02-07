# Know Your Rights

Immigration Rights Information Assistant built for QWER Hacks 2025.

## Overview

A bilingual (English/Spanish) RAG-powered chatbot providing accurate immigration rights information from verified ACLU sources. Built to make critical legal information accessible to vulnerable communities during encounters with law enforcement and immigration officials.

## Features

- **Bilingual Support** — Native English and Spanish content from ACLU guides
- **Verified Sources** — All answers grounded in 154 knowledge chunks from 11 ACLU PDFs
- **Source Citations** — Every response links back to the original ACLU document
- **Safe & Accurate** — RAG architecture prevents hallucination; off-topic questions are handled gracefully
- **Fast Responses** — 1-3 second answer generation
- **Quick Actions** — Pre-built buttons for the most common immigration rights questions

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Google Gemini 2.0 Flash |
| Embeddings | Gemini Embedding 001 (768 dimensions) |
| Vector DB | ChromaDB (persistent, cosine similarity) |
| Frontend | Streamlit |
| Language | Python 3.10+ |

## Quick Start

```bash
# 1. Clone and enter project
git clone <repo-url>
cd kyr-chatbot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
# Get one at: https://aistudio.google.com/apikey

# 4. Extract text from PDFs
python src/data_collection.py

# 5. Process and chunk documents
python src/process_documents.py

# 6. Build vector database (embeds 154 chunks)
python src/vector_db.py

# 7. Launch the app
streamlit run app.py
```

## Project Structure

```
kyr-chatbot/
├── app.py                      # Streamlit frontend
├── src/
│   ├── data_collection.py      # PDF text extraction (pdfplumber + PyPDF2)
│   ├── process_documents.py    # Cleaning, chunking, category detection
│   ├── vector_db.py            # ChromaDB indexing + Gemini embeddings
│   └── rag_engine.py           # RAG query pipeline (retrieve + generate)
├── data/
│   ├── pdfs/english/           # 6 ACLU PDFs (English)
│   ├── pdfs/spanish/           # 5 ACLU PDFs (Spanish)
│   ├── raw/                    # Extracted .txt files with metadata
│   └── processed/chunks.json   # 154 chunks ready for embedding
├── chroma_db/                  # Persistent vector database
├── tests/test_app.py           # Smoke tests for the pipeline
├── requirements.txt
├── .env.example
└── DEMO.md                     # Demo script and talking points
```

## How It Works

1. **PDF Extraction** — `data_collection.py` extracts text from ACLU PDFs using pdfplumber (with PyPDF2 fallback), cleans artifacts, and saves structured `.txt` files
2. **Chunking** — `process_documents.py` splits documents into 800-1200 character overlapping chunks, auto-detects categories (ICE Encounters, Police Rights, Protest Rights, Voting Rights), and maps source URLs
3. **Embedding** — `vector_db.py` embeds all 154 chunks using Gemini's embedding model and stores them in ChromaDB with cosine similarity indexing
4. **RAG Query** — `rag_engine.py` embeds the user's question, retrieves the top matching chunks, and sends them as context to Gemini 2.0 Flash with safety-focused system instructions
5. **Frontend** — `app.py` provides a bilingual chat interface with quick actions, source citations, and conversation history

## Data Sources

All content is sourced from official ACLU Know Your Rights guides:

- [Immigrants' Rights](https://www.aclu.org/know-your-rights/immigrants-rights)
- [Stopped by Police](https://www.aclu.org/know-your-rights/stopped-by-police)
- [Protesters' Rights](https://www.aclu.org/know-your-rights/protesters-rights)
- [Voting Rights](https://www.aclu.org/know-your-rights/voting-rights)
- [100-Mile Border Zone](https://www.aclu.org/know-your-rights/border-zone)
- [Federal Agents at the Polls](https://www.aclu.org/know-your-rights/federal-agents-polls)
- Plus 5 Spanish-language equivalents

## Social Impact

This tool addresses the critical need for accessible, multilingual immigration rights information. Many immigrant communities face language barriers and lack access to legal resources. By providing instant, accurate information in both English and Spanish, this chatbot empowers vulnerable individuals to understand and assert their rights during encounters with law enforcement and immigration officials.

## Running Tests

```bash
python tests/test_app.py
```

Validates: vector DB loading, English/Spanish RAG responses, off-topic handling, and source format.

## Future Enhancements

- Additional languages (Mandarin, Arabic, Vietnamese, Haitian Creole)
- SMS/WhatsApp bot integration for broader reach
- Offline mode for areas with limited connectivity
- Integration with local legal aid finder
- Voice input for accessibility

## Hackathon

**QWER Hacks 2025** — Nurture Track

## Disclaimer

This chatbot provides general information only and is **not legal advice**. For guidance on your specific situation, please consult a qualified immigration attorney or contact your local legal aid organization.

Content sourced from ACLU Know Your Rights guides. Not affiliated with or endorsed by the ACLU.
