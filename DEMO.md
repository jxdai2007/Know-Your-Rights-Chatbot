# Know Your Rights - Demo Guide

## 30-Second Elevator Pitch

> Millions of immigrants in the US don't know their constitutional rights during encounters with law enforcement. Legal information exists, but it's buried in long PDFs, often only in English, and hard to access in a moment of crisis.
>
> **Know Your Rights** is a bilingual RAG chatbot that gives instant, accurate answers to immigration rights questions — powered by verified ACLU sources. Ask a question in English or Spanish, and get a cited, trustworthy answer in seconds. No hallucination, no guessing — just verified legal information when people need it most.

---

## Demo Scenarios

### Scenario 1: ICE at the Door (English)

**Question:** "What are my rights if ICE comes to my door?"

**What to highlight:**
- Answer cites ACLU sources directly
- Mentions right to not open the door without a judicial warrant
- Expandable sources section shows exact ACLU document
- Response time ~2-3 seconds

### Scenario 2: Police Stop (Spanish)

**Switch language to Espanol, then ask:**
"Cuales son mis derechos cuando me detiene la policia?"

**What to highlight:**
- Full Spanish response from Spanish ACLU content (not machine-translated)
- Same quality and citations as English
- Quick action buttons also switch to Spanish
- Demonstrates true bilingual support

### Scenario 3: Off-Topic Graceful Handling

**Question:** "What's the weather today?"

**What to highlight:**
- Bot correctly says "I don't have verified information about that"
- Does NOT hallucinate an answer or cite irrelevant sources
- Shows the safety guardrails in action
- Recommends consulting an immigration attorney

### Bonus: Quick Action Buttons

**Click:** "Can I refuse to answer questions?"

**What to highlight:**
- Pre-built questions for common scenarios
- One-click access to critical information
- Useful for users who don't know what to ask

---

## Key Features to Highlight

| Feature | Detail |
|---------|--------|
| Bilingual | Native English and Spanish content from ACLU |
| RAG Pipeline | 154 knowledge chunks from 11 ACLU PDFs |
| Verified Sources | Every answer cites ACLU documents with links |
| Safety First | Never hallucinates, never gives legal advice |
| Semantic Search | Gemini embeddings + ChromaDB cosine similarity |
| Fast | 1-3 second response time |

---

## Anticipated Judge Questions

### "Why not just link to the ACLU website?"

The ACLU website has dense, multi-page documents. Our chatbot:
- Gives **instant, specific answers** to exact questions
- Works in **both English and Spanish** from a single interface
- Is **accessible** to people with limited literacy or tech skills
- Can be used on a **phone during a stressful encounter**
- **Cites the exact source** so users can verify

### "How do you prevent misinformation/hallucination?"

Three layers of protection:
1. **Only verified sources** — all 154 knowledge chunks come from official ACLU Know Your Rights guides
2. **RAG architecture** — the LLM can ONLY use provided context, never its training data
3. **Distance threshold** — if no relevant chunk matches the question, the bot says "I don't have information" instead of guessing

### "What's the social impact?"

- **11.5 million** undocumented immigrants in the US face rights uncertainty
- **Language barriers** prevent millions from accessing existing resources
- ICE enforcement has increased — people need to know their rights NOW
- This tool is **free, instant, and bilingual** — removing three major barriers
- Can be deployed as a **community resource** at churches, legal aid clinics, and community centers

### "What's the tech stack?"

- **Google Gemini 3 Pro** — LLM for answer generation + multimodal image analysis
- **Gemini Embeddings** (gemini-embedding-001, 768 dimensions) — semantic search
- **ChromaDB** — persistent vector database with cosine similarity
- **Streamlit** — responsive web frontend
- **Flask + Twilio** — WhatsApp bot with image recognition and conversation memory
- **Python** — end-to-end pipeline (PDF extraction, chunking, RAG)

### "What would you add with more time?"

1. **More languages** — Mandarin, Arabic, Vietnamese, Haitian Creole
2. **Offline mode** — critical for areas with limited connectivity
3. **Local legal aid finder** — connect users with nearby immigration attorneys
4. **Voice input** — for users with limited literacy

---

## Pre-Demo Checklist

- [ ] Vector DB is populated (`chroma_db/` directory exists)
- [ ] API key is in `.env`
- [ ] Run `streamlit run app.py` and verify it loads
- [ ] Test all 4 quick action buttons
- [ ] Test language switch to Spanish
- [ ] Test an off-topic question
- [ ] Check that sources expand and show links
