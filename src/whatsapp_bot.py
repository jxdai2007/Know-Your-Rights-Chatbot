"""
whatsapp_bot.py — Flask webhook for Twilio WhatsApp integration.

Urgent, concise responses designed for people in crisis situations.
No sources, no follow-ups — just immediate actionable guidance.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse

try:
    from src.rag_engine import answer_question
except ImportError:
    from rag_engine import answer_question

# ── Config ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

SESSION_FILE = BASE_DIR / "data" / "whatsapp_sessions.json"
LOG_FILE = BASE_DIR / "data" / "whatsapp_log.json"

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [WA] %(message)s")
logger = logging.getLogger(__name__)

# Suppress verbose Twilio / urllib3 / httpx debug logs.
for _noisy in ("twilio", "twilio.http_client", "urllib3", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ── Flask app ─────────────────────────────────────────────────────
app = Flask(__name__)

# ── Urgent system prompt (WhatsApp-specific) ─────────────────────
URGENT_PROMPT = """\
You are an emergency immigration rights assistant. Someone is texting \
you on WhatsApp in an urgent situation.

Provide IMMEDIATE, ACTIONABLE guidance in 3-5 bullet points. Be direct \
and clear.

RULES:
1. Maximum 500 characters total.
2. Use bullet points (the bullet character followed by a space) for each action.
3. Start with the most urgent action first.
4. Use simple, clear language — no jargon.
5. No citations, no source names, no "According to..." phrases.
6. Focus on WHAT TO DO RIGHT NOW.
7. If the message is a greeting or introductory message (like "hi", \
"hello", "hey", "hola", etc.), respond EXACTLY with: \
"Hi! I'm the Know Your Rights bot. I provide immigration rights info \
from ACLU sources. Ask me about ICE encounters, police stops, protest \
rights, or voting rights. Type HELP for all options."
8. If the question is NOT about immigration rights, police encounters, \
protests, or voting rights, respond EXACTLY with: \
"This isn't something I'm designed to help with. I only cover immigration \
rights. Try a general AI assistant like ChatGPT."
9. If the question IS about immigration rights but the context doesn't \
answer it, respond EXACTLY with: \
"I don't have info on that specific topic in my sources. For legal advice, \
consult an immigration attorney."
10. If responding in Spanish, follow the same rules in Spanish.
11. NEVER provide legal advice — you provide information only."""

# Max tokens kept small to enforce concise answers.
URGENT_MAX_TOKENS = 256

# ── Topic emoji (one per message, based on question keywords) ────
TOPIC_EMOJI = {
    "ice": "\U0001f6aa",
    "door": "\U0001f6aa",
    "puerta": "\U0001f6aa",
    "police": "\U0001f46e",
    "policia": "\U0001f46e",
    "cop": "\U0001f46e",
    "stopped": "\U0001f46e",
    "detenido": "\U0001f46e",
    "protest": "\u270a",
    "protesta": "\u270a",
    "vote": "\U0001f5f3\ufe0f",
    "voting": "\U0001f5f3\ufe0f",
    "voto": "\U0001f5f3\ufe0f",
    "rights": "\u2696\ufe0f",
    "derechos": "\u2696\ufe0f",
}

LANGUAGE_SELECT_MSG = (
    "Welcome to Know Your Rights / Bienvenido a Conozca Sus Derechos\n\n"
    "Please choose your language / Elija su idioma:\n\n"
    "1 - English\n"
    "2 - Español"
)

CAPABILITIES_MSG = {
    "en": (
        "Know Your Rights Bot\n\n"
        "I provide immigration rights information from ACLU sources. "
        "I can help with:\n\n"
        "- Your rights if ICE comes to your door\n"
        "- Your rights when stopped by police\n"
        "- Your rights at protests\n"
        "- Voting rights information\n\n"
        "Try asking:\n"
        "- \"What if ICE comes to my door?\"\n"
        "- \"What are my rights with police?\"\n\n"
        "Commands: ESPAÑOL, HELP\n\n"
        "What would you like to know?"
    ),
    "es": (
        "Bot Conozca Sus Derechos\n\n"
        "Proporciono información sobre derechos de inmigración de fuentes "
        "de la ACLU. Puedo ayudar con:\n\n"
        "- Sus derechos si ICE viene a su puerta\n"
        "- Sus derechos al ser detenido por la policía\n"
        "- Sus derechos en protestas\n"
        "- Información sobre derechos de voto\n\n"
        "Pruebe preguntar:\n"
        "- \"¿Qué pasa si ICE viene a mi puerta?\"\n"
        "- \"¿Cuáles son mis derechos con la policía?\"\n\n"
        "Comandos: ENGLISH, HELP\n\n"
        "¿Qué le gustaría saber?"
    ),
}

HELP_TEXT = {
    "en": (
        "Know Your Rights\n\n"
        "Ask any question about immigration rights.\n\n"
        "Try asking about:\n"
        "- ICE encounters and your rights\n"
        "- Police stops and your rights\n"
        "- Your basic immigration rights\n\n"
        "Commands:\n"
        "ESPA\u00d1OL - switch to Spanish\n"
        "ENGLISH - switch to English\n"
        "HELP - show this message\n\n"
        "Info only, not legal advice."
    ),
    "es": (
        "Conozca Sus Derechos\n\n"
        "Haga cualquier pregunta sobre derechos de inmigraci\u00f3n.\n\n"
        "Pruebe preguntar sobre:\n"
        "- Encuentros con ICE y sus derechos\n"
        "- Paradas policiales y sus derechos\n"
        "- Sus derechos b\u00e1sicos de inmigraci\u00f3n\n\n"
        "Comandos:\n"
        "ENGLISH - cambiar a ingl\u00e9s\n"
        "ESPA\u00d1OL - cambiar a espa\u00f1ol\n"
        "HELP - mostrar este mensaje\n\n"
        "Info solamente, no es asesoramiento legal."
    ),
}

RATE_LIMIT_WINDOW = 30  # seconds
RATE_LIMIT_MAX = 20  # max messages per window (generous for hackathon demo)

DISCLAIMER = {
    "en": "\n\n\u26a0\ufe0f Info only, not legal advice.",
    "es": "\n\n\u26a0\ufe0f Info solamente, no es asesoramiento legal.",
}


# ── Session management ────────────────────────────────────────────
def _load_sessions() -> dict:
    """Load WhatsApp sessions from disk."""
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_sessions(sessions: dict) -> None:
    """Persist WhatsApp sessions to disk."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(sessions, indent=2))


def _get_session(phone: str) -> dict:
    """Get or create a session for a phone number."""
    sessions = _load_sessions()
    if phone not in sessions:
        sessions[phone] = {
            "language": "en",
            "history": [],
            "message_times": [],
            "welcomed": False,
            "awaiting_language": True,
        }
        _save_sessions(sessions)
    return sessions[phone]


def _update_session(phone: str, session: dict) -> None:
    """Update a phone number's session."""
    sessions = _load_sessions()
    sessions[phone] = session
    _save_sessions(sessions)


# ── Interaction logging ───────────────────────────────────────────
def _log_interaction(phone: str, message: str, response: str, lang: str) -> None:
    """Append an interaction to the log file."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phone_hash": hash(phone) % 10**8,
        "language": lang,
        "message_preview": message[:50],
        "response_length": len(response),
    }
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if LOG_FILE.exists():
        try:
            entries = json.loads(LOG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            entries = []
    entries.append(log_entry)
    LOG_FILE.write_text(json.dumps(entries, indent=2))


def get_log_stats() -> dict:
    """Return summary stats from the WhatsApp log."""
    if not LOG_FILE.exists():
        return {"total": 0, "today": 0, "languages": {}}
    try:
        entries = json.loads(LOG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"total": 0, "today": 0, "languages": {}}

    today = datetime.now(timezone.utc).date().isoformat()
    today_count = sum(1 for e in entries if e["timestamp"][:10] == today)
    lang_counts = {}
    for e in entries:
        lang = e.get("language", "en")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    return {"total": len(entries), "today": today_count, "languages": lang_counts}


# ── Rate limiting ─────────────────────────────────────────────────
def _is_rate_limited(session: dict, phone: str) -> bool:
    """Check if a user has exceeded the rate limit."""
    now = time.time()
    recent = [t for t in session.get("message_times", []) if now - t < RATE_LIMIT_WINDOW]
    session["message_times"] = recent
    if len(recent) >= RATE_LIMIT_MAX:
        next_allowed = min(recent) + RATE_LIMIT_WINDOW
        wait_secs = max(0, int(next_allowed - now))
        logger.warning(
            "Rate limit reached for user %s (%d/%d in %ds). Next allowed in %ds.",
            hash(phone) % 10**8, len(recent), RATE_LIMIT_MAX,
            RATE_LIMIT_WINDOW, wait_secs,
        )
        return True
    return False


# ── Topic emoji detection ─────────────────────────────────────────
def _get_topic_emoji(text: str) -> str:
    """Return a single emoji based on question keywords."""
    low = text.lower()
    for keyword, emoji in TOPIC_EMOJI.items():
        if keyword in low:
            return emoji
    return "\u2696\ufe0f"


# ── Core message handler ─────────────────────────────────────────
def handle_message(phone: str, body: str, num_media: int = 0) -> str:
    """
    Process an incoming WhatsApp message and return the reply text.
    """
    session = _get_session(phone)
    text = body.strip()
    text_upper = text.upper()

    # ── Language selection for new users ──────────────────────
    if session.get("awaiting_language"):
        choice = text_upper.strip()
        if choice in ("1", "ENGLISH", "EN"):
            session["language"] = "en"
        elif choice in ("2", "ESPAÑOL", "ESPANOL", "ES", "SPANISH"):
            session["language"] = "es"
        else:
            # First contact — send the language prompt
            if not session.get("welcomed"):
                session["welcomed"] = True
                _update_session(phone, session)
                _log_interaction(phone, "(first contact)", LANGUAGE_SELECT_MSG, "en")
                return LANGUAGE_SELECT_MSG
            # Already sent prompt but got unrecognized reply — resend
            _update_session(phone, session)
            return LANGUAGE_SELECT_MSG

        # Language selected — send capabilities summary
        session["awaiting_language"] = False
        lang = session["language"]
        _update_session(phone, session)
        reply = CAPABILITIES_MSG[lang]
        _log_interaction(phone, text, reply, lang)
        return reply

    # ── Normal processing (already onboarded) ─────────────────
    lang = session["language"]
    return _process_text(phone, session, text, text_upper, lang, num_media)


def _process_text(
    phone: str, session: dict, text: str, text_upper: str, lang: str, num_media: int
) -> str:
    """Process a message after the welcome check."""

    # ── Media handling ────────────────────────────────────────
    if num_media > 0 and not text:
        reply = (
            "I can only answer text questions. Type your question."
            if lang == "en"
            else "Solo respondo preguntas de texto. Escriba su pregunta."
        )
        _update_session(phone, session)
        _log_interaction(phone, "(media)", reply, lang)
        return reply

    # ── Rate limiting ─────────────────────────────────────────
    if _is_rate_limited(session, phone):
        reply = (
            "Please wait 30 seconds before sending another message."
            if lang == "en"
            else "Espere 30 segundos antes de enviar otro mensaje."
        )
        _update_session(phone, session)
        return reply

    session["message_times"].append(time.time())

    # ── Special commands ──────────────────────────────────────
    if text_upper == "HELP":
        reply = HELP_TEXT[lang]
        _update_session(phone, session)
        _log_interaction(phone, text, reply, lang)
        return reply

    if text_upper in ("ESPAÑOL", "ESPANOL", "SPANISH"):
        session["language"] = "es"
        reply = "Idioma cambiado a espa\u00f1ol. Escriba HELP para opciones."
        _update_session(phone, session)
        _log_interaction(phone, text, reply, "es")
        return reply

    if text_upper == "ENGLISH":
        session["language"] = "en"
        reply = "Language switched to English. Type HELP for options."
        _update_session(phone, session)
        _log_interaction(phone, text, reply, "en")
        return reply

    # ── Empty message ─────────────────────────────────────────
    if not text:
        reply = (
            "Send a question about your immigration rights. Type HELP for options."
            if lang == "en"
            else "Envie una pregunta sobre sus derechos. Escriba HELP para opciones."
        )
        _update_session(phone, session)
        _log_interaction(phone, "", reply, lang)
        return reply

    # ── RAG query with urgent prompt ──────────────────────────
    try:
        answer, _sources = answer_question(
            text,
            language=lang,
            n_results=5,
            system_prompt=URGENT_PROMPT,
            max_output_tokens=URGENT_MAX_TOKENS,
        )
    except Exception as exc:
        err_msg = str(exc).lower()
        if "429" in err_msg or "resource_exhausted" in err_msg or "rate limit" in err_msg:
            reply = (
                "Service busy. Please wait 60 seconds and try again."
                if lang == "en"
                else "Servicio ocupado. Espere 60 segundos e intente de nuevo."
            )
        else:
            logger.error("RAG error for %s: %s", hash(phone) % 10**8, exc)
            reply = (
                "An error occurred. Please try again."
                if lang == "en"
                else "Ocurrio un error. Intente de nuevo."
            )
        _update_session(phone, session)
        _log_interaction(phone, text, reply, lang)
        return reply

    # ── Format: emoji + answer + disclaimer ───────────────────
    emoji = _get_topic_emoji(text)
    reply = emoji + " " + answer + DISCLAIMER[lang]

    # ── Update conversation history (keep last 3) ─────────────
    session["history"].append({"q": text[:100], "a": answer[:200]})
    session["history"] = session["history"][-3:]

    _update_session(phone, session)
    _log_interaction(phone, text, reply, lang)
    return reply


# ── Twilio REST client (singleton) ────────────────────────────────
_twilio_client: TwilioClient | None = None


def _get_twilio_client() -> TwilioClient:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio_client


# ── Twilio WhatsApp webhook ───────────────────────────────────────
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Receive incoming WhatsApp message from Twilio and reply."""
    phone = request.form.get("From", "")
    body = request.form.get("Body", "")
    num_media = int(request.form.get("NumMedia", "0"))

    logger.info("Incoming WhatsApp from %s: %s", hash(phone) % 10**8, body[:50])

    reply_text = handle_message(phone, body, num_media=num_media)

    # Send via REST API for better error visibility.
    try:
        client = _get_twilio_client()
        msg = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=phone,
            body=reply_text,
        )
        logger.info("Sent SID=%s status=%s", msg.sid, msg.status)
    except Exception as exc:
        logger.error("Twilio send failed: %s", exc)

    # Return empty TwiML to acknowledge the webhook.
    return str(MessagingResponse()), 200, {"Content-Type": "application/xml"}


# ── Test endpoint (no Twilio needed) ─────────────────────────────
@app.route("/test", methods=["POST"])
def test_endpoint():
    """Simulate a WhatsApp interaction for local development."""
    data = request.get_json(force=True)
    phone = data.get("phone", "whatsapp:+1TEST000000")
    body = data.get("message", "")
    num_media = data.get("num_media", 0)

    logger.info("Test WhatsApp from %s: %s", phone, body[:50])

    reply_text = handle_message(phone, body, num_media=num_media)
    return jsonify({"reply": reply_text, "phone": phone})


@app.route("/stats", methods=["GET"])
def stats_endpoint():
    """Return WhatsApp interaction stats."""
    return jsonify(get_log_stats())


@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"status": "ok", "service": "kyr-whatsapp-bot"})


# ── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("WHATSAPP_BOT_PORT", "5001"))
    logger.info("Starting WhatsApp bot on port %d", port)
    logger.info("Twilio webhook URL: POST /whatsapp")
    logger.info("Test endpoint: POST /test")
    logger.info("Stats endpoint: GET /stats")
    app.run(host="0.0.0.0", port=port, debug=True)
