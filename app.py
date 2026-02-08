"""
app.py — Streamlit frontend for the Know Your Rights chatbot.
"""

import os
import time

import streamlit as st

from src.rag_engine import answer_question
from src.whatsapp_bot import get_log_stats, LOG_FILE

# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Know Your Rights",
    page_icon="\U0001f6e1\ufe0f",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "language" not in st.session_state:
    st.session_state.language = "en"
if "processing" not in st.session_state:
    st.session_state.processing = False
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

# ── Dark theme CSS ────────────────────────────────────────────────
DARK_THEME_CSS = """
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    .stChatMessage { background-color: #1a1d24; }
    .stMarkdown, .stMarkdown p, .stMarkdown li { color: #fafafa; }
    header[data-testid="stHeader"] { background-color: #0e1117; }
    .stSidebar, section[data-testid="stSidebar"] { background-color: #161b22; }
    .stSidebar .stMarkdown, .stSidebar .stMarkdown p { color: #e6edf3; }
    div[data-testid="stExpander"] { background-color: #161b22; border-color: #30363d; }
    .stTabs [data-baseweb="tab-list"] { background-color: #0e1117; }
    .stTabs [data-baseweb="tab"] { color: #fafafa; }
    .stDivider { border-color: #30363d; }
    .stChatInput input, .stChatInput textarea { background-color: #1a1d24; color: #fafafa; }
</style>
"""

LIGHT_THEME_CSS = """
<style>
    .stApp { background-color: #ffffff; color: #262730; }
</style>
"""

if st.session_state.dark_mode:
    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)
else:
    st.markdown(LIGHT_THEME_CSS, unsafe_allow_html=True)

# ── Quick-action definitions per language ─────────────────────────
QUICK_ACTIONS = {
    "en": [
        ("\U0001f6aa What if ICE comes to my door?", "What are my rights if ICE comes to my door?"),
        ("\U0001f46e Rights when stopped by police", "What are my rights when stopped by police?"),
        ("\U0001f910 Can I refuse to answer questions?", "Can I refuse to answer questions from immigration agents?"),
        ("\U0001faaa Do I need to show ID?", "Do I need to show identification to police or immigration agents?"),
    ],
    "es": [
        ("\U0001f6aa \u00bfQu\u00e9 pasa si ICE viene a mi puerta?", "\u00bfCu\u00e1les son mis derechos si ICE viene a mi puerta?"),
        ("\U0001f46e Derechos al ser detenido por la polic\u00eda", "\u00bfCu\u00e1les son mis derechos cuando me detiene la polic\u00eda?"),
        ("\U0001f910 \u00bfPuedo negarme a responder preguntas?", "\u00bfPuedo negarme a responder preguntas de agentes de inmigraci\u00f3n?"),
        ("\U0001faaa \u00bfNecesito mostrar identificaci\u00f3n?", "\u00bfNecesito mostrar identificaci\u00f3n a la polic\u00eda o agentes de inmigraci\u00f3n?"),
    ],
}

DISCLAIMER = {
    "en": (
        "\u26a0\ufe0f **Disclaimer:** This tool provides general information only, "
        "**not legal advice**. For guidance on your specific situation, please "
        "consult a qualified immigration attorney."
    ),
    "es": (
        "\u26a0\ufe0f **Aviso:** Esta herramienta proporciona informaci\u00f3n general "
        "solamente, **no es asesoramiento legal**. Para orientaci\u00f3n sobre su "
        "situaci\u00f3n espec\u00edfica, consulte con un abogado de inmigraci\u00f3n calificado."
    ),
}

PLACEHOLDER = {
    "en": "Ask about your immigration rights...",
    "es": "Pregunte sobre sus derechos de inmigraci\u00f3n...",
}


# ── Helpers ───────────────────────────────────────────────────────
def _should_suppress_sources(answer: str, sources: list[dict]) -> bool:
    """True if sources should be hidden (fallback, greeting, or no citations)."""
    low = answer.lower()
    # Explicit fallback phrases (off-topic or no-info responses).
    if any(p in low for p in [
        "don't have verified information",
        "no tengo informacion verificada",
        "isn't something i'm designed to help with",
        "no es algo para lo que estoy",
    ]):
        return True
    if not sources:
        return True
    # If the answer doesn't reference any source material, suppress sources.
    # The system prompt instructs: cite with "According to ACLU" or source title.
    mentions_aclu = "aclu" in low
    mentions_title = any(
        s["title"].lower() in low
        for s in sources if len(s.get("title", "")) > 3
    )
    return not mentions_aclu and not mentions_title


def _render_sources(sources: list[dict], lang: str) -> None:
    """Render the expandable sources section."""
    label = (
        f"\U0001f4da Sources ({len(sources)})" if lang == "en"
        else f"\U0001f4da Fuentes ({len(sources)})"
    )
    with st.expander(label):
        for s in sources:
            url = s.get("url", "")
            link = f"  \n[View on ACLU]({url})" if url else ""
            st.markdown(
                f"**{s['title']}**  \n"
                f"Category: {s['category']} \u2022 "
                f"Language: {s['language'].upper()}"
                f"{link}"
            )


# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### \U0001f30d Language / Idioma")
    lang_choice = st.radio(
        "Select language",
        options=["English \U0001f1fa\U0001f1f8", "Espa\u00f1ol \U0001f1f2\U0001f1fd"],
        index=0 if st.session_state.language == "en" else 1,
        label_visibility="collapsed",
    )
    new_lang = "en" if lang_choice.startswith("English") else "es"
    if new_lang != st.session_state.language:
        st.session_state.language = new_lang
        st.rerun()

    st.divider()

    # Conversation history summary.
    pairs = [
        (st.session_state.messages[i], st.session_state.messages[i + 1])
        for i in range(0, len(st.session_state.messages) - 1, 2)
        if st.session_state.messages[i]["role"] == "user"
    ]
    if pairs:
        st.markdown("### \U0001f4ac History" if st.session_state.language == "en" else "### \U0001f4ac Historial")
        for q, _a in pairs[-5:]:
            st.markdown(f"- {q['content'][:60]}{'...' if len(q['content']) > 60 else ''}")

        if st.button(
            "\U0001f5d1\ufe0f Clear conversation" if st.session_state.language == "en"
            else "\U0001f5d1\ufe0f Borrar conversaci\u00f3n"
        ):
            st.session_state.messages = []
            st.rerun()

    st.divider()

    with st.expander(
        "\u2139\ufe0f About this tool" if st.session_state.language == "en"
        else "\u2139\ufe0f Acerca de esta herramienta"
    ):
        if st.session_state.language == "en":
            st.markdown(
                "This assistant uses **Retrieval-Augmented Generation (RAG)** "
                "to answer immigration rights questions using only verified "
                "content from **ACLU Know Your Rights** guides.\n\n"
                "**How it works:** Your question is matched against 154 "
                "knowledge chunks from 11 ACLU documents (6 English, 5 Spanish) "
                "using semantic search. The most relevant passages are sent to "
                "Google Gemini to generate an accurate, cited answer.\n\n"
                "\u26a0\ufe0f This is **not legal advice**. Always consult an "
                "immigration attorney for your specific situation."
            )
        else:
            st.markdown(
                "Este asistente utiliza **Generaci\u00f3n Aumentada por "
                "Recuperaci\u00f3n (RAG)** para responder preguntas sobre derechos "
                "de inmigraci\u00f3n usando solo contenido verificado de las gu\u00edas "
                "**ACLU Conozca Sus Derechos**.\n\n"
                "**C\u00f3mo funciona:** Su pregunta se compara con 154 fragmentos "
                "de conocimiento de 11 documentos de la ACLU (6 en ingl\u00e9s, "
                "5 en espa\u00f1ol) mediante b\u00fasqueda sem\u00e1ntica. Los pasajes m\u00e1s "
                "relevantes se env\u00edan a Google Gemini para generar una "
                "respuesta precisa y citada.\n\n"
                "\u26a0\ufe0f Esto **no es asesoramiento legal**. Siempre consulte "
                "con un abogado de inmigraci\u00f3n para su situaci\u00f3n espec\u00edfica."
            )

    st.divider()
    st.caption(
        "Powered by ACLU Know Your Rights guides \u2022 "
        "Built with Gemini & ChromaDB"
    )

# ── Header ────────────────────────────────────────────────────────
lang = st.session_state.language

header_col, theme_col = st.columns([5, 1])
with header_col:
    st.markdown("# \U0001f6e1\ufe0f Know Your Rights" if lang == "en" else "# \U0001f6e1\ufe0f Conozca Sus Derechos")
with theme_col:
    st.markdown("")  # spacing
    theme_label = "Dark" if not st.session_state.dark_mode else "Light"
    if st.button(f"{theme_label}", key="theme_toggle", use_container_width=True):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

st.markdown(
    "*Immigration Rights Information Assistant*" if lang == "en"
    else "*Asistente de Informaci\u00f3n sobre Derechos de Inmigraci\u00f3n*"
)
st.info(DISCLAIMER[lang])

# ── Tabs ─────────────────────────────────────────────────────────
tab_chat, tab_wa = st.tabs([
    "Chat" if lang == "en" else "Chat",
    "WhatsApp" if lang == "en" else "WhatsApp",
])

# ── Tab 1: Chat ──────────────────────────────────────────────────
with tab_chat:
    # Quick actions (disabled while processing).
    actions = QUICK_ACTIONS[lang]
    cols = st.columns(2)
    clicked_question = None
    for idx, (label, question) in enumerate(actions):
        with cols[idx % 2]:
            if st.button(
                label,
                use_container_width=True,
                key=f"qa_{idx}",
                disabled=st.session_state.processing,
            ):
                clicked_question = question

    # Chat history display.
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                _render_sources(msg["sources"], lang)
            if msg["role"] == "assistant" and msg.get("elapsed"):
                st.caption(f"\u23f1\ufe0f {msg['elapsed']:.1f}s")

    # Chat input.
    user_input = st.chat_input(PLACEHOLDER[lang])

    # A quick-action click acts like typing the question.
    question = clicked_question or user_input

    if question:
        # Lock buttons while generating.
        st.session_state.processing = True

        # Show the user message.
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Generate the answer.
        with st.chat_message("assistant"):
            thinking = (
                "Searching verified sources and generating answer..."
                if lang == "en"
                else "Buscando fuentes verificadas y generando respuesta..."
            )
            with st.spinner(thinking):
                try:
                    start = time.time()
                    answer, sources = answer_question(
                        question, language=lang, n_results=5,
                    )
                    elapsed = time.time() - start
                except Exception as exc:
                    err_msg = str(exc).lower()
                    if "429" in err_msg or "resource_exhausted" in err_msg or "rate limit" in err_msg:
                        answer = (
                            "\u23f3 The service is temporarily busy. Please wait about 60 seconds and try again."
                            if lang == "en"
                            else "\u23f3 El servicio est\u00e1 temporalmente ocupado. Espere unos 60 segundos e int\u00e9ntelo de nuevo."
                        )
                    else:
                        answer = (
                            f"An error occurred: {exc}. Please try again."
                            if lang == "en"
                            else f"Ocurri\u00f3 un error: {exc}. Int\u00e9ntelo de nuevo."
                        )
                    sources = []
                    elapsed = 0.0

            # Bug fix: suppress sources when the LLM declined to answer.
            if _should_suppress_sources(answer, sources):
                sources = []

            st.markdown(answer)

            if sources:
                _render_sources(sources, lang)

            if elapsed:
                st.caption(f"\u23f1\ufe0f {elapsed:.1f}s")

        # Persist the assistant message (sources already cleared if fallback).
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "elapsed": elapsed,
        })

        # Unlock buttons.
        st.session_state.processing = False
        st.rerun()

# ── Tab 2: WhatsApp Access ───────────────────────────────────────
with tab_wa:
    wa_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
    # Strip the "whatsapp:" prefix for display.
    wa_display = wa_number.replace("whatsapp:", "")

    if lang == "en":
        st.markdown("### Message us on WhatsApp for instant answers")
        st.markdown(
            "Get immigration rights information directly on WhatsApp — "
            "the app millions already use every day. Rich formatting, "
            "bilingual support, and instant responses."
        )
    else:
        st.markdown("### Env\u00edenos un mensaje en WhatsApp para respuestas inmediatas")
        st.markdown(
            "Obtenga informaci\u00f3n sobre derechos de inmigraci\u00f3n directamente "
            "en WhatsApp \u2014 la app que millones ya usan todos los d\u00edas. "
            "Formato enriquecido, soporte biling\u00fce y respuestas instant\u00e1neas."
        )

    st.success(
        f"Message us on WhatsApp: **{wa_display}**"
        if lang == "en"
        else f"Escr\u00edbanos en WhatsApp: **{wa_display}**"
    )

    st.divider()

    # ── Example messages ──────────────────────────────────────
    st.markdown(
        "#### Try these messages" if lang == "en"
        else "#### Pruebe estos mensajes"
    )
    examples = [
        ("What if ICE comes to my door?", "\u00bfQu\u00e9 pasa si ICE viene a mi puerta?"),
        ("What are my rights when stopped by police?", "\u00bfCu\u00e1les son mis derechos con la polic\u00eda?"),
        ("HELP", "HELP"),
        ("ESPA\u00d1OL", "ENGLISH"),
    ]
    for en_ex, es_ex in examples:
        ex = en_ex if lang == "en" else es_ex
        st.code(ex, language=None)

    st.divider()

    # ── Live stats ────────────────────────────────────────────
    st.markdown(
        "#### WhatsApp Stats" if lang == "en"
        else "#### Estad\u00edsticas WhatsApp"
    )
    stats = get_log_stats()
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Today" if lang == "en" else "Hoy",
        stats["today"],
    )
    col2.metric(
        "Total" if lang == "en" else "Total",
        stats["total"],
    )
    lang_breakdown = stats.get("languages", {})
    col3.metric(
        "Languages" if lang == "en" else "Idiomas",
        len(lang_breakdown) if lang_breakdown else 0,
    )

    st.divider()

    # ── Sample conversation ───────────────────────────────────
    st.markdown(
        "#### Sample Conversation" if lang == "en"
        else "#### Conversaci\u00f3n de Ejemplo"
    )

    sample_en = [
        ("You", "What if ICE comes to my door?"),
        ("Bot",
         "\U0001f6aa If ICE is at your door:\n\n"
         "\u2022 DO NOT open the door\n"
         "\u2022 Ask: \"Do you have a warrant signed by a judge?\"\n"
         "\u2022 Say: \"I do not consent to your entry\"\n"
         "\u2022 Stay silent - you have the right\n"
         "\u2022 Call a lawyer immediately if possible\n\n"
         "\u26a0\ufe0f Info only, not legal advice."),
    ]
    sample_es = [
        ("T\u00fa", "\u00bfQu\u00e9 pasa si ICE viene a mi puerta?"),
        ("Bot",
         "\U0001f6aa Si ICE est\u00e1 en su puerta:\n\n"
         "\u2022 NO abra la puerta\n"
         "\u2022 Pregunte: \"\u00bfTiene una orden firmada por un juez?\"\n"
         "\u2022 Diga: \"No doy consentimiento para que entre\"\n"
         "\u2022 Guarde silencio - tiene el derecho\n"
         "\u2022 Llame a un abogado si es posible\n\n"
         "\u26a0\ufe0f Info solamente, no es asesoramiento legal."),
    ]
    sample = sample_en if lang == "en" else sample_es

    for sender, text in sample:
        if sender in ("You", "T\u00fa"):
            with st.chat_message("user"):
                st.markdown(text)
        else:
            with st.chat_message("assistant"):
                st.markdown(text)

    st.divider()

    # ── How to get started ────────────────────────────────────
    st.markdown(
        "#### How to Get Started" if lang == "en"
        else "#### C\u00f3mo Empezar"
    )

    if lang == "en":
        st.markdown(
            f"**Step 1:** Save our number to your contacts: "
            f"**{wa_display or '(number coming soon)'}**\n\n"
            "**Step 2:** Open WhatsApp and send **Hi** to that number\n\n"
            "**Step 3:** Select your language (English or Espa\u00f1ol)\n\n"
            "**Step 4:** Start asking questions about your immigration rights!"
        )
    else:
        st.markdown(
            f"**Paso 1:** Guarde nuestro n\u00famero en sus contactos: "
            f"**{wa_display or '(n\u00famero pr\u00f3ximamente)'}**\n\n"
            "**Paso 2:** Abra WhatsApp y env\u00ede **Hola** a ese n\u00famero\n\n"
            "**Paso 3:** Seleccione su idioma (English o Espa\u00f1ol)\n\n"
            "**Paso 4:** Comience a hacer preguntas sobre sus derechos de inmigraci\u00f3n!"
        )

    with st.expander(
        "Developer Info" if lang == "en"
        else "Info para Desarrolladores"
    ):
        st.markdown(
            "See `README.md` for developer setup instructions "
            "(Twilio, ngrok, Flask webhook configuration)."
            if lang == "en"
            else "Vea `README.md` para instrucciones de configuraci\u00f3n "
            "para desarrolladores (Twilio, ngrok, webhook de Flask)."
        )
