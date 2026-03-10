import streamlit as st
import tempfile
import os
import io
import math
from datetime import datetime
from docx import Document
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from pydub import AudioSegment
from google import genai

# 1. Setup and Date Extraction
load_dotenv()
client = genai.Client()

# Fixes the [Current Date] placeholder issue
current_date_val = datetime.now().strftime("%B %d, %Y")

# Fetch the system prompt from the .env file
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

CONCISE_PROMPT = os.getenv("CONCISE_PROMPT", """You are a Chief of Staff. Summarize these notes into a 'Flash Report'. Focus on the 3 most critical outcomes, the 5 most urgent action items, and major blockers. Keep it under 300 words.

MANDATORY DATE: [Insert Today's Date]

FLEXIBLE STRUCTURE RULE:
You may rename or create new headings if they more accurately reflect the urgency or nature of the specific meeting.

MANDATORY EXPORT FORMATTING:
1. CLEAN EXPORT: Use only plain text and simple bullets (-). No tables or bolding inside text blocks.
2. PDF ALIGNMENT: Ensure no line is excessively long; use standard spacing to ensure the PDF export is clean and fully readable without truncation.

Default Structure:
# Executive Flash Report
## I. Key Strategic Outcomes
## II. Urgent Actions
## III. Critical Blockers""")

PROFESSIONAL_PROMPT = os.getenv("PROFESSIONAL_PROMPT", """You are a Senior Corporate Secretary. Your task is to generate exhaustive, professional meeting minutes. Capture the nuance, data points, and all perspectives shared.

MANDATORY DATE: [Insert Today's Date]

FLEXIBLE STRUCTURE RULE: 
If the structure below does not fit the flow of the specific meeting, you are AUTHORIZED and encouraged to generate your own logical headings and sub-headings that best organize the information discussed. 

MANDATORY EXPORT FORMATTING:
1. UNIVERSAL COMPATIBILITY: No Markdown tables, nested columns, or complex symbols.
2. PDF/WORD SAFETY: Use plain text with simple bullet points (-) only. Do NOT use bolding (**) or italics (*) within sentences, as these break the PDF rendering engine and cause text truncation.
3. TEXT WRAPPING: Use clear line breaks and keep paragraphs concise so text wraps correctly in PDF/Word without cutting off at the margins.

Default Structure (Adapt as needed):
# Official Meeting Minutes
## 1. Executive Summary
## 2. Detailed Discussion Points (Create custom sub-headings based on topics)
## 3. Key Decisions Made
## 4. Action Items (Task | Owner | Deadline)
## 5. Next Steps / Follow-up""")

# --- PARSERS FOR MULTIPLE MEDIUMS ---

def extract_text_from_pdf(file_obj):
    reader = PdfReader(file_obj)
    return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])

def extract_text_from_docx(file_obj):
    doc = Document(file_obj)
    return "\n".join([para.text for para in doc.paragraphs])

def process_audio(file_obj):
    ext = file_obj.name.split('.')[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(file_obj.read())
        path = tmp.name
    try:
        audio = AudioSegment.from_file(path)
        chunk_ms = 45 * 60 * 1000 
        chunks_count = math.ceil(len(audio) / chunk_ms)
        summaries = []
        for i in range(chunks_count):
            chunk = audio[i*chunk_ms : min((i+1)*chunk_ms, len(audio))]
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as c_tmp:
                chunk.export(c_tmp.name, format="mp3")
                g_file = client.files.upload(file=c_tmp.name)
                res = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=["Summarize this meeting audio segment in detail.", g_file]
                )
                summaries.append(res.text)
                client.files.delete(name=g_file.name)
        return "\n".join(summaries)
    finally:
        if os.path.exists(path): os.remove(path)

# --- HARDENED EXPORT ENGINES (FIXES TRUNCATION) ---

def create_pdf(text, title="Official Document"):
    """Uses reportlab with proper margins and text wrapping to prevent truncation."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=inch, rightMargin=inch,
        topMargin=inch, bottomMargin=inch
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Title'], fontSize=16, spaceAfter=16)
    heading_style = ParagraphStyle('DocHeading', parent=styles['Heading2'], fontSize=13, spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle('DocBody', parent=styles['Normal'], fontSize=11, leading=16, spaceAfter=4)
    bullet_style = ParagraphStyle('DocBullet', parent=styles['Normal'], fontSize=11, leading=16, leftIndent=20, spaceAfter=4)

    story = [Paragraph(title, title_style), Spacer(1, 6)]

    for line in text.split('\n'):
        clean = line.strip().replace('**', '').replace('*', '')
        clean = clean.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        clean_text = clean.lstrip('#').strip()
        if not clean_text:
            story.append(Spacer(1, 6))
            continue
        if clean.startswith('#'):
            story.append(Paragraph(clean_text, heading_style))
        elif clean_text.startswith('-') or clean_text.startswith('\u2022'):
            story.append(Paragraph(clean_text[1:].strip(), bullet_style))
        else:
            story.append(Paragraph(clean_text, body_style))

    doc.build(story)
    return buf.getvalue()

def create_docx(text, title="Meeting Minutes"):
    doc = Document()
    doc.add_heading(title, 0)
    for line in text.split('\n'):
        line = line.strip().replace('**', '').replace('#', '')
        if line:
            doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

# --- UI AND LAYOUT ---
st.set_page_config(page_title="Minutes AI", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow:wght@400;500;600;700;800&display=swap');

:root {
    --red:       #E50914;
    --red-dark:  #B20710;
    --bg:        #141414;
    --surface:   #1f1f1f;
    --surface2:  #1a1a1a;
    --surface3:  #2a2a2a;
    --border:    rgba(255,255,255,0.07);
    --border2:   rgba(255,255,255,0.13);
    --text:      #e5e5e5;
    --text-dim:  #999;
    --text-muted:#555;
    --white:     #fff;
}

html, body, [class*="css"] {
    font-family: 'Barlow', sans-serif !important;
    -webkit-font-smoothing: antialiased;
}

.stApp {
    background: var(--bg) !important;
    color: var(--text) !important;
}

.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

[data-testid="stVerticalBlock"] > div:empty { display: none !important; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { display: none !important; }
[data-testid="stToolbar"]     { display: none !important; }
[data-testid="stDecoration"]  { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }

/* ── ANIMATIONS ── */
@keyframes fadeUp  { from { opacity:0; transform:translateY(16px) } to { opacity:1; transform:translateY(0) } }
@keyframes fadeIn  { from { opacity:0 } to { opacity:1 } }
@keyframes ticker  { from { transform:translateX(0) } to { transform:translateX(-50%) } }
@keyframes glowred { 0%,100% { opacity:.5 } 50% { opacity:1 } }
@keyframes pulsedot { 0%,100% { box-shadow:0 0 0 0 rgba(229,9,20,.55) } 70% { box-shadow:0 0 0 9px rgba(229,9,20,0) } }

/* ── NAVBAR ── */
.nf-nav {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 1.25rem;
    height: 52px;
    background: rgba(14,14,14,0.97);
    border-bottom: 1px solid var(--border);
    position: sticky; top: 0; z-index: 999;
    animation: fadeIn .3s ease both;
}
.nf-logo {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 1.5rem; letter-spacing: .06em;
    color: var(--red);
    text-shadow: 0 2px 12px rgba(229,9,20,.35);
    line-height: 1;
}
.nf-logo span {
    color: rgba(255,255,255,.8); font-size: .68rem;
    letter-spacing: .2em; margin-left: .4rem;
    font-family: 'Barlow', sans-serif; font-weight: 600;
    text-shadow: none; vertical-align: middle;
}
.nf-nav-right { display:flex; align-items:center; gap:.75rem; }
.nf-date  { font-size:.72rem; color:var(--text-dim); font-weight:500; }
.nf-pill  {
    font-size:.58rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
    color:var(--white); background:var(--red);
    padding:.2rem .55rem; border-radius:2px;
}

/* ── TICKER ── */
.nf-ticker {
    background: rgba(0,0,0,.55);
    border-bottom: 1px solid var(--border);
    padding: .32rem 0; overflow: hidden;
}
.nf-ticker-track { display:flex; width:max-content; animation: ticker 28s linear infinite; }
.nf-ticker-item  {
    white-space:nowrap; font-size:.6rem; font-weight:700;
    letter-spacing:.12em; text-transform:uppercase;
    color:var(--text-muted); padding:0 2rem;
}
.nf-ticker-item b { color:var(--red); margin-right:.4rem; }

/* ── STREAMLIT COLUMNS: fill viewport height below nav+ticker ── */
[data-testid="stHorizontalBlock"] {
    height: calc(100vh - 78px) !important;
    align-items: stretch !important;
    gap: 0 !important;
}
[data-testid="stHorizontalBlock"] > div {
    height: 100% !important;
    overflow: hidden !important;
}

/* ── LEFT COLUMN (Streamlit) ── */
[data-testid="stHorizontalBlock"] > div:first-child {
    border-right: 1px solid var(--border) !important;
    background: linear-gradient(180deg, #0d0d0d 0%, #141414 100%) !important;
    overflow-y: auto !important;
}

/* ── RIGHT COLUMN (Streamlit) ── */
[data-testid="stHorizontalBlock"] > div:last-child {
    overflow-y: auto !important;
}

/* ── LEFT PANEL INNER ── */
.left-col {
    padding: 1.75rem 1.5rem 1.25rem;
    display: flex; flex-direction: column;
    position: relative; overflow: hidden;
    animation: fadeUp .5s cubic-bezier(.22,1,.36,1) .08s both;
    height: 100%;
    box-sizing: border-box;
}
.left-col::before {
    content:''; position:absolute;
    width:280px; height:280px;
    background:radial-gradient(circle, rgba(229,9,20,.08) 0%, transparent 70%);
    top:-60px; left:-60px;
    animation: glowred 5s ease-in-out infinite; pointer-events:none;
}

.panel-eyebrow {
    font-size:.58rem; font-weight:700; letter-spacing:.18em; text-transform:uppercase;
    color:var(--red); margin-bottom:1.2rem;
    display:flex; align-items:center; gap:.5rem;
}
.panel-eyebrow::before { content:''; width:20px; height:2px; background:var(--red); display:block; }

.panel-title {
    font-family:'Bebas Neue', sans-serif;
    font-size:clamp(1.8rem, 3vw, 2.6rem); font-weight:400; line-height:.92;
    color:var(--white); letter-spacing:.02em; margin-bottom:.55rem;
}
.panel-title em { color:var(--red); font-style:normal; }

.panel-desc {
    font-size:.8rem; color:var(--text-dim); line-height:1.55;
    margin-bottom:1rem; font-weight:400;
}

.fmt-row { display:flex; gap:.3rem; flex-wrap:wrap; margin-bottom:1rem; }
.fmt-chip {
    font-size:.57rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase;
    color:var(--text-muted);
    background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.07);
    padding:.18rem .5rem; border-radius:2px;
}

/* ── EMPTY STATE ── */
.empty-state {
    flex:1; display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    text-align:center; padding:2rem;
    animation: fadeIn .6s ease both;
    min-height: calc(100vh - 140px);
}
.empty-icon {
    font-family:'Bebas Neue', sans-serif; font-size:clamp(3rem, 8vw, 6rem); line-height:1;
    color:rgba(255,255,255,.03); letter-spacing:.05em; margin-bottom:1rem;
}
.empty-title { font-size:.85rem; font-weight:600; color:var(--text-muted); }
.empty-sub   { font-size:.72rem; color:var(--text-muted); opacity:.55; margin-top:.3rem; }

/* ── RESULTS ── */
.results-area { padding: 1.25rem 1.25rem 0; }

.result-header {
    display:flex; align-items:center; justify-content:space-between; margin-bottom:.9rem;
}
.result-title {
    font-family:'Bebas Neue', sans-serif; font-size:1.35rem;
    color:var(--white); letter-spacing:.04em;
}
.result-dot {
    width:8px; height:8px; border-radius:50%; background:var(--red);
    animation: pulsedot 2.5s ease infinite;
}

.export-row { display:flex; align-items:center; gap:.55rem; margin-bottom:.7rem; }
.export-tag {
    font-size:.58rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase;
    color:var(--text-muted); white-space:nowrap;
}
.export-line { flex:1; height:1px; background:var(--border); }

.document-card {
    background:var(--surface); border:1px solid var(--border);
    border-top:2px solid rgba(229,9,20,.3); border-radius:4px;
    padding:1.25rem 1.5rem; color:rgba(255,255,255,.72);
    font-size:.84rem; line-height:1.85; white-space:pre-wrap;
    font-family:'Barlow', sans-serif;
    box-shadow:0 4px 28px rgba(0,0,0,.5);
    animation: fadeUp .4s cubic-bezier(.22,1,.36,1) both;
    max-height: calc(100vh - 340px); overflow-y: auto;
    min-height: 200px;
}
.document-card::-webkit-scrollbar { width:3px; }
.document-card::-webkit-scrollbar-thumb { background:var(--surface3); border-radius:3px; }

/* ── MOBILE RESPONSIVE ── */
@media (max-width: 768px) {
    .nf-date { display: none; }
    .nf-logo { font-size: 1.3rem; }
    .panel-title { font-size: 1.8rem; }
    .panel-eyebrow { margin-bottom: .8rem; }

    /* Stack columns vertically on mobile */
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        height: auto !important;
    }
    [data-testid="stHorizontalBlock"] > div {
        width: 100% !important;
        min-width: 100% !important;
        height: auto !important;
        overflow: visible !important;
    }
    [data-testid="stHorizontalBlock"] > div:first-child {
        border-right: none !important;
        border-bottom: 1px solid var(--border) !important;
    }
    .left-col {
        padding: 1.25rem 1rem;
        min-height: auto;
        height: auto;
    }
    .document-card {
        max-height: 60vh;
    }
    .results-area { padding: 1rem; }
    .stTabs [data-baseweb="tab-list"] { padding: 0 1rem !important; }
    .stTabs [data-baseweb="tab"] { padding: .7rem .9rem !important; font-size: .68rem !important; }
}

@media (min-width: 769px) and (max-width: 1024px) {
    .panel-title { font-size: 2rem; }
    .panel-eyebrow { margin-bottom: .9rem; }
    .document-card { max-height: calc(100vh - 310px); }
}

/* ── STREAMLIT UPLOADER ── */
[data-testid="stFileUploader"] {
    background: var(--surface) !important;
    border: 1px solid var(--border2) !important;
    border-radius: 5px !important; padding: .3rem !important;
    box-shadow: 0 4px 20px rgba(0,0,0,.4) !important;
    transition: border-color .2s, box-shadow .2s !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(229,9,20,.4) !important;
    box-shadow: 0 4px 24px rgba(229,9,20,.12) !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: var(--surface2) !important;
    border: 1.5px dashed rgba(255,255,255,.09) !important;
    border-radius: 4px !important; padding: 1.5rem 1rem !important;
    transition: all .2s !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: rgba(229,9,20,.45) !important;
    background: rgba(229,9,20,.03) !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] span {
    color: var(--text-dim) !important; font-size: .82rem !important;
    font-family: 'Barlow', sans-serif !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: var(--surface3) !important; color: var(--text) !important;
    border: 1px solid rgba(255,255,255,.1) !important; border-radius: 3px !important;
    font-size: .76rem !important; font-weight: 600 !important;
    font-family: 'Barlow', sans-serif !important; padding: .4rem 1rem !important;
    transition: all .15s !important;
}
[data-testid="stFileUploaderDropzone"] button:hover { background: rgba(255,255,255,.1) !important; }
[data-testid="stFileUploader"] label { display: none !important; }

/* ── TABS (inside right panel) ── */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(0,0,0,.5) !important;
    border-bottom: 1px solid var(--border2) !important;
    gap: 0 !important; padding: 0 1.25rem !important;
    position: sticky; top: 0; z-index: 10;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Barlow', sans-serif !important;
    font-size: .72rem !important; font-weight: 700 !important;
    letter-spacing: .1em !important; text-transform: uppercase !important;
    color: var(--text-muted) !important; background: transparent !important;
    border: none !important; border-bottom: 2px solid transparent !important;
    padding: .75rem 1.25rem !important; margin-bottom: -1px !important;
    transition: color .18s !important;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--text) !important; }
.stTabs [aria-selected="true"] {
    color: var(--white) !important;
    border-bottom: 2px solid var(--red) !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-panel"]    { padding: 0 !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* ── PRIMARY BUTTON ── */
div.stButton > button {
    width: 100% !important; background: var(--red) !important;
    color: var(--white) !important; font-family: 'Barlow', sans-serif !important;
    font-weight: 700 !important; font-size: .84rem !important;
    letter-spacing: .08em !important; text-transform: uppercase !important;
    border: none !important; border-radius: 3px !important;
    padding: .75rem 1rem !important; margin-top: .85rem !important;
    box-shadow: 0 4px 18px rgba(229,9,20,.28) !important;
    transition: all .18s cubic-bezier(.4,0,.2,1) !important;
}
div.stButton > button:hover {
    background: #f40612 !important;
    box-shadow: 0 6px 30px rgba(229,9,20,.42) !important;
    transform: translateY(-1px) !important;
}
div.stButton > button:active {
    background: var(--red-dark) !important; transform: scale(.998) !important;
}

/* ── DOWNLOAD BUTTONS ── */
div.stDownloadButton > button {
    width: 100% !important; background: rgba(255,255,255,.06) !important;
    color: var(--text) !important; font-family: 'Barlow', sans-serif !important;
    font-size: .7rem !important; font-weight: 700 !important;
    letter-spacing: .08em !important; text-transform: uppercase !important;
    border: 1px solid rgba(255,255,255,.09) !important; border-radius: 3px !important;
    padding: .55rem .4rem !important; transition: all .15s ease !important;
}
div.stDownloadButton > button:hover {
    background: rgba(255,255,255,.12) !important;
    border-color: rgba(255,255,255,.18) !important;
    color: var(--white) !important; transform: translateY(-1px) !important;
}

/* ── ALERTS / SPINNER ── */
.stAlert {
    background: rgba(229,9,20,.08) !important;
    border: 1px solid rgba(229,9,20,.25) !important;
    border-radius: 3px !important; color: #ff7070 !important;
    font-size: .8rem !important; font-weight: 500 !important;
}
.stSpinner > div {
    border-color: var(--surface3) var(--surface3) var(--surface3) var(--red) !important;
}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)

# session state
if "detailed" not in st.session_state: st.session_state.detailed = None
if "concise"  not in st.session_state: st.session_state.concise  = None

# ticker
items = ["Meeting Minutes","Flash Reports","PDF Export","Word Export",
         "Multi-File Synthesis","Action Items","Key Decisions","Audio Transcription"]
ticker_html = "".join(
    f'<span class="nf-ticker-item"><b>●</b>{t}</span>' for t in items * 3
)

# ── NAVBAR ────────────────────────────────────────────────────
st.markdown(f"""
<div class="nf-nav">
  <div class="nf-logo">MINUTES<span>AI</span></div>
  <div class="nf-nav-right">
    <span class="nf-date">{current_date_val}</span>
    <span class="nf-pill">Pro</span>
  </div>
</div>
<div class="nf-ticker">
  <div class="nf-ticker-track">{ticker_html}</div>
</div>
""", unsafe_allow_html=True)

# ── TWO-COLUMN LAYOUT via Streamlit columns ───────────────────
left_col, right_col = st.columns([35, 65], gap="small")

# ══ LEFT ══════════════════════════════════════════════════════
with left_col:
    st.markdown("""
    <div class="left-col">
      <div class="panel-eyebrow">Upload</div>
      <div class="panel-title">MEETING<em> MINUTES</em> ON DEMAND.</div>
      <p class="panel-desc">Drop in audio, transcripts or notes. Walk away with polished professional documents instantly.</p>
      <div class="fmt-row">
        <span class="fmt-chip">MP3</span><span class="fmt-chip">WAV</span>
        <span class="fmt-chip">M4A</span><span class="fmt-chip">TXT</span>
        <span class="fmt-chip">PDF</span><span class="fmt-chip">DOCX</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "upload",
        type=['mp3','wav','m4a','txt','pdf','docx'],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if uploaded_files and st.button("▶  Generate Report"):
        all_context = []
        for f in uploaded_files:
            with st.spinner(f"Processing {f.name}..."):
                if f.name.endswith('.txt'):
                    all_context.append(f.read().decode("utf-8"))
                elif f.name.endswith('.pdf'):
                    all_context.append(extract_text_from_pdf(f))
                elif f.name.endswith('.docx'):
                    all_context.append(extract_text_from_docx(f))
                else:
                    all_context.append(process_audio(f))
        with st.spinner("Synthesizing..."):
            date_instr = f"MANDATORY: Today is {current_date_val}. Replace all [Current Date] placeholders."
            res_det = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[date_instr, PROFESSIONAL_PROMPT, "\n\n".join(all_context)]
            )
            st.session_state.detailed = res_det.text
            res_con = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[date_instr, CONCISE_PROMPT, res_det.text]
            )
            st.session_state.concise = res_con.text
        st.success("Done.")

# ══ RIGHT ══════════════════════════════════════════════════════
with right_col:
    if st.session_state.detailed:
        t1, t2 = st.tabs(["  Detailed Minutes  ", "  Executive Flash Report  "])
        for tab, content, title, key_p in zip(
            [t1, t2],
            [st.session_state.detailed, st.session_state.concise],
            ["Detailed Minutes", "Flash Report"],
            ["d", "c"]
        ):
            with tab:
                st.markdown(f"""
                <div class="results-area">
                  <div class="result-header">
                    <span class="result-title">{title.upper()}</span>
                    <div class="result-dot"></div>
                  </div>
                  <div class="export-row">
                    <span class="export-tag">Export as</span>
                    <div class="export-line"></div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                c1.download_button("Word",  create_docx(content, title), f"{title}.docx", key=f"{key_p}_w")
                c2.download_button("PDF",   create_pdf(content, title),  f"{title}.pdf",  key=f"{key_p}_p")
                c3.download_button("Text",  content.encode('utf-8'),      f"{title}.txt",  key=f"{key_p}_t")
                st.markdown(f'<div style="padding:0 1.25rem 1.5rem;"><div class="document-card">{content}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-icon">MINUTES</div>
          <div class="empty-title">No report generated yet</div>
          <div class="empty-sub">Upload files on the left and hit Generate</div>
        </div>
        """, unsafe_allow_html=True)