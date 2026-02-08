"""
app.py — Know Your Rights landing page.

Single-page dark-themed site that drives users to WhatsApp,
with a secondary chat demo powered by the RAG engine.
"""

import base64
import time
from io import BytesIO

import qrcode
import streamlit as st

from src.rag_engine import answer_question

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Know Your Rights",
    page_icon="\U0001f6e1\ufe0f",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session state ────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "language" not in st.session_state:
    st.session_state.language = "en"
if "processing" not in st.session_state:
    st.session_state.processing = False

lang = st.session_state.language

# ── Constants ────────────────────────────────────────────────────────
WA_NUMBER = "+1 (415) 523-8886"
WA_LINK = "https://wa.me/14155238886?text=Hi"

RIGHTS_CARDS = {
    "en": [
        ("\U0001f6aa", "ICE at Your Door",
         "You do NOT have to open the door without a warrant signed by a judge"),
        ("\U0001f910", "Right to Remain Silent",
         "You have the right to remain silent. Use it."),
        ("\u2696\ufe0f", "Right to a Lawyer",
         "You have the right to speak with a lawyer before answering questions"),
        ("\U0001f6ab", "Refuse Entry",
         "You can say: \u201cI do not consent to your entry or search\u201d"),
        ("\U0001f46e", "Police Stops",
         "You can ask: \u201cAm I free to go?\u201d If yes, calmly leave"),
        ("\U0001f4f1", "Document Everything",
         "Film police encounters. It\u2019s your right."),
        ("\U0001faaa", "ID Requirements",
         "Only show ID to police if driving. Otherwise, check your state laws."),
        ("\U0001f310", "Language Rights",
         "You have the right to an interpreter"),
    ],
    "es": [
        ("\U0001f6aa", "ICE en Su Puerta",
         "NO tiene que abrir la puerta sin una orden firmada por un juez"),
        ("\U0001f910", "Derecho a Guardar Silencio",
         "Tiene derecho a guardar silencio. \u00daselo."),
        ("\u2696\ufe0f", "Derecho a un Abogado",
         "Tiene derecho a hablar con un abogado antes de responder preguntas"),
        ("\U0001f6ab", "Rechazar Entrada",
         "Puede decir: \u201cNo doy consentimiento para que entre o registre\u201d"),
        ("\U0001f46e", "Paradas Policiales",
         "Puede preguntar: \u201c\u00bfSoy libre de irme?\u201d Si s\u00ed, v\u00e1yase con calma"),
        ("\U0001f4f1", "Documente Todo",
         "Filmar encuentros policiales es su derecho."),
        ("\U0001faaa", "Requisitos de ID",
         "Solo muestre ID si conduce. De lo contrario, consulte las leyes de su estado."),
        ("\U0001f310", "Derechos de Idioma",
         "Tiene derecho a un int\u00e9rprete"),
    ],
}

QUICK_ACTIONS = {
    "en": [
        ("\U0001f6aa ICE at my door", "What are my rights if ICE comes to my door?"),
        ("\U0001f46e Police stops", "What are my rights when stopped by police?"),
        ("\U0001f910 Refuse questions", "Can I refuse to answer questions from immigration agents?"),
        ("\U0001faaa Show ID?", "Do I need to show identification to police or immigration agents?"),
    ],
    "es": [
        ("\U0001f6aa ICE en mi puerta", "\u00bfCu\u00e1les son mis derechos si ICE viene a mi puerta?"),
        ("\U0001f46e Parada policial", "\u00bfCu\u00e1les son mis derechos cuando me detiene la polic\u00eda?"),
        ("\U0001f910 Negarme a responder", "\u00bfPuedo negarme a responder preguntas de agentes de inmigraci\u00f3n?"),
        ("\U0001faaa \u00bfMostrar ID?", "\u00bfNecesito mostrar identificaci\u00f3n a la polic\u00eda o agentes de inmigraci\u00f3n?"),
    ],
}

PLACEHOLDER = {
    "en": "Ask about your immigration rights...",
    "es": "Pregunte sobre sus derechos de inmigraci\u00f3n...",
}


# ── Helpers ──────────────────────────────────────────────────────────
@st.cache_data
def _generate_qr(url: str) -> str:
    """Generate a QR code as a base64 PNG data URI."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#25D366", back_color="#1f2937")
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _should_suppress_sources(answer: str, sources: list[dict]) -> bool:
    """True if sources should be hidden (fallback, greeting, or no citations)."""
    low = answer.lower()
    if any(p in low for p in [
        "don't have verified information",
        "no tengo informacion verificada",
        "isn't something i'm designed to help with",
        "no es algo para lo que estoy",
    ]):
        return True
    if not sources:
        return True
    mentions_aclu = "aclu" in low
    mentions_title = any(
        s["title"].lower() in low
        for s in sources if len(s.get("title", "")) > 3
    )
    return not mentions_aclu and not mentions_title


def _render_sources(sources: list[dict], display_lang: str) -> None:
    """Render the expandable sources section."""
    label = (
        f"\U0001f4da Sources ({len(sources)})" if display_lang == "en"
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


# ── Global CSS ───────────────────────────────────────────────────────
GLOBAL_CSS = """
<style>
    /* ── Hide Streamlit chrome ────────────────────────────────── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stSidebar"] {display: none !important;}
    [data-testid="collapsedControl"] {display: none !important;}
    header[data-testid="stHeader"] {background: transparent !important;}

    /* ── Base ─────────────────────────────────────────────────── */
    .stApp {
        background: linear-gradient(180deg, #0f1419 0%, #1a1f2e 100%);
        color: #ffffff;
    }

    /* ── Typography — force all text light ────────────────────── */
    .stMarkdown, .stMarkdown p, .stMarkdown li,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
    .stMarkdown strong, .stMarkdown em,
    .stMarkdown a,
    label, [data-testid="stWidgetLabel"] p { color: #ffffff !important; }
    [data-testid="stCaptionContainer"] p { color: #6b7280 !important; }

    /* ── Hero ─────────────────────────────────────────────────── */
    .hero-container {
        text-align: center;
        padding: 3rem 1rem 4rem 1rem;
    }
    .hero-icon { font-size: 5rem; margin-bottom: 1rem; }
    .hero-title {
        font-size: 4rem; font-weight: 800;
        color: #ffffff !important;
        margin: 0 0 0.5rem 0; line-height: 1.1;
    }
    .hero-subtitle {
        font-size: 1.5rem; color: #9ca3af !important;
        margin: 0 0 2.5rem 0; font-weight: 400;
    }
    .hero-cta {
        display: inline-block;
        background-color: #25D366; color: #ffffff !important;
        padding: 1rem 2.5rem; border-radius: 50px;
        font-size: 1.25rem; font-weight: 700;
        text-decoration: none !important;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(37,211,102,0.3);
    }
    .hero-cta:hover {
        background-color: #1fb855;
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(37,211,102,0.4);
        color: #ffffff !important;
    }
    .hero-secondary {
        color: #6b7280 !important;
        margin-top: 1.5rem; font-size: 1rem;
    }

    /* ── Section headers ──────────────────────────────────────── */
    .section-header {
        text-align: center; font-size: 2rem; font-weight: 700;
        color: #ffffff !important; margin: 4rem 0 0.75rem 0;
    }
    .section-divider {
        width: 60px; height: 3px;
        background: #25D366;
        margin: 0 auto 2rem auto; border-radius: 2px;
    }

    /* ── Rights carousel ──────────────────────────────────────── */
    .carousel-container {
        overflow: hidden; width: 100%;
        padding: 1rem 0; margin: 0;
    }
    .carousel-track {
        display: flex; gap: 1.25rem;
        animation: carousel-scroll 45s linear infinite;
        width: max-content;
    }
    .carousel-track:hover { animation-play-state: paused; }
    @keyframes carousel-scroll {
        0%   { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    .carousel-card {
        min-width: 280px; max-width: 280px;
        background: #1f2937; border: 1px solid #374151;
        border-radius: 12px; padding: 1.5rem;
        transition: all 0.3s ease; flex-shrink: 0;
    }
    .carousel-card:hover {
        border-color: #25D366; transform: translateY(-4px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
    }
    .card-emoji { font-size: 2.5rem; margin-bottom: 0.75rem; }
    .card-title {
        font-size: 1.1rem; font-weight: 700;
        color: #ffffff; margin-bottom: 0.5rem;
    }
    .card-desc {
        font-size: 0.95rem; color: #d1d5db; line-height: 1.5;
    }

    /* ── Chat demo ────────────────────────────────────────────── */
    .stChatMessage {
        background-color: #1f2937 !important;
        border: 1px solid #374151; border-radius: 12px !important;
    }
    .stChatMessage p, .stChatMessage li { color: #ffffff !important; }
    .stChatInput > div { background-color: #1f2937 !important; }
    .stChatInput input, .stChatInput textarea {
        background-color: #1f2937 !important;
        color: #ffffff !important; border-color: #374151 !important;
    }

    /* ── Buttons ──────────────────────────────────────────────── */
    .stButton > button {
        background-color: #1f2937 !important; color: #ffffff !important;
        border: 1px solid #374151 !important; border-radius: 8px !important;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #374151 !important;
        border-color: #25D366 !important; color: #ffffff !important;
    }
    .stButton > button:disabled {
        background-color: #111827 !important; color: #4b5563 !important;
        border-color: #1f2937 !important;
    }

    /* ── Card grid (equal-height columns) ────────────────────── */
    .card-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1.25rem;
        margin: 0 auto;
    }
    @media (max-width: 768px) {
        .card-grid { grid-template-columns: 1fr; }
    }

    /* ── Step / Why cards ─────────────────────────────────────── */
    .step-card, .why-card {
        background: #1f2937; border: 1px solid #374151;
        border-radius: 12px; padding: 2rem 1.5rem;
        text-align: center;
        display: flex; flex-direction: column;
        align-items: center; justify-content: flex-start;
    }
    .step-number {
        display: inline-block; width: 40px; height: 40px;
        line-height: 40px; border-radius: 50%;
        background: #25D366; color: #ffffff;
        font-weight: 700; font-size: 1.1rem; margin-bottom: 1rem;
    }
    .step-icon, .why-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
    .step-title, .why-title {
        font-size: 1.1rem; font-weight: 700;
        color: #ffffff; margin-bottom: 0.5rem;
    }
    .step-desc, .why-desc {
        color: #9ca3af; font-size: 0.95rem; line-height: 1.5;
    }

    /* ── WhatsApp nudge ───────────────────────────────────────── */
    .wa-nudge {
        background: linear-gradient(135deg, #1a3a2a 0%, #1f2937 100%);
        border: 1px solid #25D366; border-radius: 12px;
        padding: 1.25rem; text-align: center; margin: 1rem 0;
    }
    .wa-nudge a {
        color: #25D366 !important; text-decoration: none; font-weight: 600;
    }
    .wa-nudge a:hover { text-decoration: underline; }

    /* ── Alert boxes ──────────────────────────────────────────── */
    [data-testid="stAlert"] {
        background-color: #1f2937 !important; border-color: #374151 !important;
    }
    [data-testid="stAlert"] p { color: #d1d5db !important; }

    /* ── Expanders ────────────────────────────────────────────── */
    div[data-testid="stExpander"] {
        background-color: #1f2937 !important; border-color: #374151 !important;
    }
    div[data-testid="stExpander"] summary { color: #9ca3af !important; }
    div[data-testid="stExpander"] p { color: #d1d5db !important; }

    /* ── Code blocks ──────────────────────────────────────────── */
    .stCode, code, .stCodeBlock {
        background-color: #1f2937 !important; color: #25D366 !important;
    }

    /* ── Dividers ─────────────────────────────────────────────── */
    .stDivider, hr { border-color: #374151 !important; }

    /* ── Spinner ──────────────────────────────────────────────── */
    .stSpinner > div { color: #25D366 !important; }

    /* ── Footer ───────────────────────────────────────────────── */
    .footer-section {
        text-align: center; padding: 2rem 0; color: #6b7280;
    }
    .footer-section p { color: #6b7280 !important; }
    .footer-section strong { color: #9ca3af !important; }

    /* ── Responsive ───────────────────────────────────────────── */
    @media (max-width: 768px) {
        .hero-title { font-size: 2.5rem; }
        .hero-subtitle { font-size: 1.1rem; }
        .hero-cta { padding: 0.75rem 2rem; font-size: 1rem; }
        .carousel-card { min-width: 240px; max-width: 240px; }
    }
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# =====================================================================
#  SECTION 1: HERO
# =====================================================================
hero_title = "Know Your Rights" if lang == "en" else "Conozca Sus Derechos"
hero_subtitle = (
    "Immigration Rights Assistant via WhatsApp" if lang == "en"
    else "Asistente de Derechos de Inmigraci\u00f3n por WhatsApp"
)
hero_cta = (
    "\U0001f4ac Get Started on WhatsApp" if lang == "en"
    else "\U0001f4ac Comience en WhatsApp"
)
hero_secondary = (
    "Or try the demo below \u2193" if lang == "en"
    else "O pruebe la demostraci\u00f3n abajo \u2193"
)

st.markdown(f"""
<div class="hero-container">
    <div class="hero-icon">\U0001f6e1\ufe0f</div>
    <h1 class="hero-title">{hero_title}</h1>
    <p class="hero-subtitle">{hero_subtitle}</p>
    <a href="{WA_LINK}" target="_blank" class="hero-cta">{hero_cta}</a>
    <p class="hero-secondary">{hero_secondary}</p>
</div>
""", unsafe_allow_html=True)


# =====================================================================
#  SECTION 2: RIGHTS CAROUSEL
# =====================================================================
section_title = (
    "Your Rights at a Glance" if lang == "en"
    else "Sus Derechos de un Vistazo"
)
st.markdown(
    f'<div class="section-header">{section_title}</div>'
    '<div class="section-divider"></div>',
    unsafe_allow_html=True,
)

# Build cards HTML (duplicated for seamless infinite loop).
cards_html = ""
for emoji, title, desc in RIGHTS_CARDS[lang]:
    cards_html += (
        f'<div class="carousel-card">'
        f'<div class="card-emoji">{emoji}</div>'
        f'<div class="card-title">{title}</div>'
        f'<div class="card-desc">{desc}</div>'
        f'</div>'
    )

st.markdown(
    f'<div class="carousel-container">'
    f'<div class="carousel-track">{cards_html}{cards_html}</div>'
    f'</div>',
    unsafe_allow_html=True,
)


# =====================================================================
#  SECTION 3: CHAT DEMO
# =====================================================================
section_title = "Try It Out" if lang == "en" else "Pru\u00e9belo"
st.markdown(
    f'<div class="section-header">{section_title}</div>'
    '<div class="section-divider"></div>',
    unsafe_allow_html=True,
)

# Center the chat in a narrower column.
_, chat_col, _ = st.columns([1, 2, 1])

with chat_col:
    # Quick-action buttons.
    actions = QUICK_ACTIONS[lang]
    btn_cols = st.columns(2)
    clicked_question = None
    for idx, (label, question) in enumerate(actions):
        with btn_cols[idx % 2]:
            if st.button(
                label, use_container_width=True,
                key=f"qa_{idx}", disabled=st.session_state.processing,
            ):
                clicked_question = question

    # Show last 3 exchanges (6 messages) only.
    display_msgs = st.session_state.messages[-6:]
    for msg in display_msgs:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                _render_sources(msg["sources"], lang)

    # Chat input (disabled while processing).
    user_input = st.chat_input(PLACEHOLDER[lang], disabled=st.session_state.processing)
    question = clicked_question or user_input

    if question:
        st.session_state.processing = True
        st.session_state.messages.append({"role": "user", "content": question})

        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            thinking = (
                "Searching verified sources..." if lang == "en"
                else "Buscando fuentes verificadas..."
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
                    if "429" in err_msg or "resource_exhausted" in err_msg:
                        answer = (
                            "\u23f3 Service temporarily busy. Wait ~60 s and try again."
                            if lang == "en"
                            else "\u23f3 Servicio ocupado. Espere ~60 s e int\u00e9ntelo de nuevo."
                        )
                    else:
                        answer = (
                            f"An error occurred: {exc}" if lang == "en"
                            else f"Ocurri\u00f3 un error: {exc}"
                        )
                    sources = []
                    elapsed = 0.0

            if _should_suppress_sources(answer, sources):
                sources = []

            st.markdown(answer)
            if sources:
                _render_sources(sources, lang)

        st.session_state.messages.append({
            "role": "assistant", "content": answer,
            "sources": sources, "elapsed": elapsed,
        })
        st.session_state.processing = False
        st.rerun()

    # WhatsApp nudge after 2+ exchanges.
    if len(st.session_state.messages) >= 4:
        nudge = (
            "\U0001f4a1 Get instant answers anytime \u2014 " if lang == "en"
            else "\U0001f4a1 Respuestas instant\u00e1neas \u2014 "
        )
        link_text = (
            "continue on WhatsApp!" if lang == "en"
            else "\u00a1contin\u00fae en WhatsApp!"
        )
        st.markdown(
            f'<div class="wa-nudge">{nudge}'
            f'<a href="{WA_LINK}" target="_blank">{link_text}</a></div>',
            unsafe_allow_html=True,
        )


# =====================================================================
#  SECTION 4: WHATSAPP SETUP GUIDE
# =====================================================================
section_title = (
    "Get Started on WhatsApp in 3 Steps" if lang == "en"
    else "Comience en WhatsApp en 3 Pasos"
)
st.markdown(
    f'<div class="section-header">{section_title}</div>'
    '<div class="section-divider"></div>',
    unsafe_allow_html=True,
)

qr_data_uri = _generate_qr(WA_LINK)

step1_t = "Open WhatsApp" if lang == "en" else "Abra WhatsApp"
step1_d = (
    "Open WhatsApp on your phone or use WhatsApp Web"
    if lang == "en"
    else "Abra WhatsApp en su tel\u00e9fono o use WhatsApp Web"
)
step2_t = "Message Our Number" if lang == "en" else "Env\u00ede un Mensaje"
send_word = "Hi" if lang == "en" else "Hola"
step2_d = (
    f"Send <strong>{send_word}</strong> to:<br>"
    f"<strong style='color:#25D366;font-size:1.1rem'>{WA_NUMBER}</strong>"
)
step3_t = "Start Asking" if lang == "en" else "Comience a Preguntar"
step3_d = (
    "Ask in English or Spanish:<br>"
    "<em style='color:#25D366'>\u201cWhat if ICE comes to my door?\u201d</em><br>"
    "<em style='color:#25D366'>\u201c\u00bfQu\u00e9 hago si me para la polic\u00eda?\u201d</em>"
    if lang == "en"
    else "Pregunte en ingl\u00e9s o espa\u00f1ol:<br>"
    "<em style='color:#25D366'>\u201cWhat if ICE comes to my door?\u201d</em><br>"
    "<em style='color:#25D366'>\u201c\u00bfQu\u00e9 hago si me para la polic\u00eda?\u201d</em>"
)

st.markdown(
    f'<div class="card-grid">'
    # Step 1
    f'<div class="step-card">'
    f'<div class="step-number">1</div>'
    f'<div class="step-icon">\U0001f4f1</div>'
    f'<div class="step-title">{step1_t}</div>'
    f'<div class="step-desc">{step1_d}</div>'
    f'</div>'
    # Step 2
    f'<div class="step-card">'
    f'<div class="step-number">2</div>'
    f'<div class="step-icon">\U0001f4ac</div>'
    f'<div class="step-title">{step2_t}</div>'
    f'<div class="step-desc">{step2_d}</div>'
    f'<img src="{qr_data_uri}" alt="QR Code" '
    f'style="margin-top:1rem;border-radius:8px;width:140px;">'
    f'</div>'
    # Step 3
    f'<div class="step-card">'
    f'<div class="step-number">3</div>'
    f'<div class="step-icon">\u2705</div>'
    f'<div class="step-title">{step3_t}</div>'
    f'<div class="step-desc">{step3_d}</div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)


# =====================================================================
#  SECTION 5: WHY WHATSAPP
# =====================================================================
section_title = (
    "Why We Use WhatsApp" if lang == "en"
    else "\u00bfPor Qu\u00e9 Usamos WhatsApp?"
)
st.markdown(
    f'<div class="section-header">{section_title}</div>'
    '<div class="section-divider"></div>',
    unsafe_allow_html=True,
)

why1_t = "Widely Used" if lang == "en" else "Uso Extendido"
why1_d = (
    "87% of Latino immigrants use WhatsApp weekly. "
    "We meet you where you are."
    if lang == "en"
    else "El 87% de los inmigrantes latinos usan WhatsApp "
    "diariamente. Le encontramos donde est\u00e1."
)
why2_t = "Free &amp; Accessible" if lang == "en" else "Gratis y Accesible"
why2_d = (
    "No SMS fees. Works on WiFi. "
    "Available on any smartphone."
    if lang == "en"
    else "Sin cargos de SMS. Funciona con WiFi. "
    "Disponible en cualquier smartphone."
)
why3_t = "Private &amp; Secure" if lang == "en" else "Privado y Seguro"
why3_d = (
    "End-to-end encrypted. "
    "Your questions stay private."
    if lang == "en"
    else "Cifrado de extremo a extremo. "
    "Sus preguntas son privadas."
)

st.markdown(
    f'<div class="card-grid">'
    f'<div class="why-card">'
    f'<div class="why-icon">\U0001f30d</div>'
    f'<div class="why-title">{why1_t}</div>'
    f'<div class="why-desc">{why1_d}</div>'
    f'</div>'
    f'<div class="why-card">'
    f'<div class="why-icon">\U0001f4b8</div>'
    f'<div class="why-title">{why2_t}</div>'
    f'<div class="why-desc">{why2_d}</div>'
    f'</div>'
    f'<div class="why-card">'
    f'<div class="why-icon">\U0001f512</div>'
    f'<div class="why-title">{why3_t}</div>'
    f'<div class="why-desc">{why3_d}</div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)


# =====================================================================
#  SECTION 6: FOOTER
# =====================================================================
st.divider()

_, ft_col, _ = st.columns([1, 2, 1])
with ft_col:
    # Language toggle.
    lc1, lc2 = st.columns(2)
    with lc1:
        if st.button(
            "\U0001f1fa\U0001f1f8 English", use_container_width=True,
            key="lang_en", disabled=(lang == "en"),
        ):
            st.session_state.language = "en"
            st.rerun()
    with lc2:
        if st.button(
            "\U0001f1f2\U0001f1fd Espa\u00f1ol", use_container_width=True,
            key="lang_es", disabled=(lang == "es"),
        ):
            st.session_state.language = "es"
            st.rerun()

disclaimer = (
    "\u26a0\ufe0f <strong>Disclaimer:</strong> This tool provides general "
    "information only, <strong>not legal advice</strong>. For guidance on "
    "your specific situation, please consult a qualified immigration attorney."
    if lang == "en"
    else "\u26a0\ufe0f <strong>Aviso:</strong> Esta herramienta proporciona "
    "informaci\u00f3n general solamente, <strong>no es asesoramiento legal"
    "</strong>. Para orientaci\u00f3n sobre su situaci\u00f3n espec\u00edfica, "
    "consulte con un abogado de inmigraci\u00f3n calificado."
)

st.markdown(
    f'<div class="footer-section">'
    f'<p>{disclaimer}</p>'
    f'<p style="margin-top:1rem;">'
    f'Powered by ACLU Know Your Rights guides \u2022 '
    f'Built with Gemini &amp; ChromaDB'
    f'</p></div>',
    unsafe_allow_html=True,
)
