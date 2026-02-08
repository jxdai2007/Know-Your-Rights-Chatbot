# Know Your Rights

Immigration Rights Information Assistant built for QWER Hacks 2025.
**[Try It Out](https://knowyourrights.streamlit.app)**
## Overview

A bilingual (English/Spanish) RAG-powered chatbot providing accurate immigration rights information from verified ACLU sources. Available as both a web app and a WhatsApp bot — meeting vulnerable communities where they are during encounters with law enforcement and immigration officials.

## Features

- **Bilingual Support** — Native English and Spanish content from ACLU guides
- **Verified Sources** — All answers grounded in 154 knowledge chunks from 11 ACLU PDFs
- **Source Citations** — Every response links back to the original ACLU document
- **Safe & Accurate** — RAG architecture prevents hallucination; off-topic questions are handled gracefully
- **WhatsApp Bot** — Urgent, concise guidance via Twilio WhatsApp integration with two-step language onboarding
- **Image Recognition** — Send a photo of a warrant or document for instant analysis via Gemini multimodal
- **Conversation Memory** — Follow-up questions get contextual answers (last 5 exchanges)
- **Quick Actions** — Pre-built buttons for the most common immigration rights questions (web UI)

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Google Gemini 3 Pro (preview) |
| Embeddings | Gemini Embedding 001 (768 dimensions) |
| Vector DB | ChromaDB (persistent, cosine similarity) |
| Web Frontend | Streamlit |
| WhatsApp | Flask + Twilio REST API |
| Language | Python 3.10+ |

## Quick Start

```bash
# 1. Clone and enter project
git clone <repo-url>
cd kyr-chatbot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env and add your keys:
#   GOOGLE_API_KEY        — required (https://aistudio.google.com/apikey)
#   TWILIO_ACCOUNT_SID    — for WhatsApp bot only
#   TWILIO_AUTH_TOKEN      — for WhatsApp bot only
#   TWILIO_WHATSAPP_NUMBER — for WhatsApp bot only

# 4. Build the knowledge base (run in order, one-time setup)
python src/data_collection.py      # Extract text from PDFs
python src/process_documents.py    # Chunk documents
python src/vector_db.py            # Embed & index into ChromaDB

# 5. Launch the web app
streamlit run app.py

# 6. Launch the WhatsApp bot (optional, requires Twilio credentials)
python src/whatsapp_bot.py
```

### Testing the WhatsApp bot locally

```bash
# Without Twilio — use the /test endpoint
curl -X POST http://localhost:5001/test \
  -H "Content-Type: application/json" \
  -d '{"phone": "whatsapp:+1TEST", "message": "What if ICE comes to my door?"}'

# Health check
curl http://localhost:5001/health
```

## Project Structure

```
kyr-chatbot/
├── app.py                      # Streamlit web frontend (landing page + chat)
├── src/
│   ├── data_collection.py      # PDF text extraction (pdfplumber + PyPDF2)
│   ├── process_documents.py    # Cleaning, chunking, category detection
│   ├── vector_db.py            # ChromaDB indexing + Gemini embeddings
│   ├── rag_engine.py           # RAG query pipeline (retrieve + generate)
│   └── whatsapp_bot.py         # Flask webhook for Twilio WhatsApp
├── data/
│   ├── pdfs/english/           # 6 ACLU PDFs (English)
│   ├── pdfs/spanish/           # 5 ACLU PDFs (Spanish)
│   ├── raw/                    # Extracted .txt files with metadata
│   ├── processed/chunks.json   # 154 chunks ready for embedding
│   ├── whatsapp_sessions.json  # Per-user WhatsApp session state
│   └── whatsapp_log.json       # Anonymized interaction log
├── chroma_db/                  # Persistent vector database
├── tests/test_app.py           # Smoke tests for the pipeline
├── requirements.txt
├── .env.example
├── CLAUDE.md                   # Developer guide for AI-assisted coding
└── DEMO.md                     # Demo script and talking points
```

## How It Works

1. **PDF Extraction** — `data_collection.py` extracts text from ACLU PDFs using pdfplumber (with PyPDF2 fallback), cleans artifacts, and saves structured `.txt` files
2. **Chunking** — `process_documents.py` splits documents into 800-1200 character overlapping chunks, auto-detects categories (ICE Encounters, Police Rights, Protest Rights, Voting Rights), and maps source URLs
3. **Embedding** — `vector_db.py` embeds all 154 chunks using Gemini's embedding model and stores them in ChromaDB with cosine similarity indexing
4. **RAG Query** — `rag_engine.py` embeds the user's question, retrieves the top matching chunks, and sends them as context to Gemini 3 Pro with safety-focused system instructions and BLOCK_ONLY_HIGH safety settings
5. **Web Frontend** — `app.py` provides a bilingual chat interface with quick actions, source citations, conversation history, and a WhatsApp QR code for connecting via phone
6. **WhatsApp Bot** — `whatsapp_bot.py` delivers urgent, concise bullet-point guidance via Twilio. Supports language onboarding, conversation memory for follow-ups, image analysis for documents/warrants, and commands (HELP, RESET, ESPAÑOL/ENGLISH)

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

This tool addresses the critical need for accessible, multilingual immigration rights information. Many immigrant communities face language barriers and lack access to legal resources. By providing instant, accurate information in both English and Spanish — through both a web app and WhatsApp — this chatbot empowers vulnerable individuals to understand and assert their rights during encounters with law enforcement and immigration officials.

## Running Tests

```bash
python tests/test_app.py
```

Validates: vector DB loading, English/Spanish RAG responses, off-topic handling, and source format.

## Future Enhancements

- Additional languages (Mandarin, Arabic, Vietnamese, Haitian Creole)
- Offline mode for areas with limited connectivity
- Integration with local legal aid finder
- Voice input for accessibility

## Hackathon

**QWER Hacks 2025** — Nurture Track

## Disclaimer

This chatbot provides general information only and is **not legal advice**. For guidance on your specific situation, please consult a qualified immigration attorney or contact your local legal aid organization.

Content sourced from ACLU Know Your Rights guides. Not affiliated with or endorsed by the ACLU.
