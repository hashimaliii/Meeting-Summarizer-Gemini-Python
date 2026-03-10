import streamlit as st
import tempfile
import os
import io
import math
from datetime import datetime
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
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
        if clean.startswith(('#',)):
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
st.set_page_config(page_title="Minutes AI Pro", layout="centered")

st.markdown(f"""
    <style>
    .stApp {{ background-color: #0F172A; color: #F8FAFC; }}
    [data-testid="stVerticalBlock"] > div:empty {{ display: none !important; }}
    div.stButton > button {{ 
        background-color: #FACC15 !important; color: #0F172A !important; 
        font-weight: 700; width: 100%; border-radius: 8px; padding: 12px;
    }}
    .stTabs [aria-selected="true"] {{ color: #FACC15 !important; border-bottom: 2px solid #FACC15 !important; }}
    .document-card {{ background-color: #1E293B; padding: 2.5rem; border-radius: 12px; margin-top: 1rem; color: #E2E8F0; line-height: 1.6; }}
    </style>
""", unsafe_allow_html=True)

st.title("Minutes AI: Multi-Medium Synthesis")
st.write(f"Meeting Date: **{current_date_val}**")

if "detailed" not in st.session_state: st.session_state.detailed = None
if "concise" not in st.session_state: st.session_state.concise = None

uploaded_files = st.file_uploader("Upload Audio, TXT, PDF, or DOCX", 
                                  type=['mp3', 'wav', 'm4a', 'txt', 'pdf', 'docx'], 
                                  accept_multiple_files=True)

# Generate button
if uploaded_files and st.button("Generate Master Report"):
    all_context = []
    for f in uploaded_files:
        with st.spinner(f"Reading {f.name}..."):
            if f.name.endswith('.txt'):
                all_context.append(f.read().decode("utf-8"))
            elif f.name.endswith('.pdf'):
                all_context.append(extract_text_from_pdf(f))
            elif f.name.endswith('.docx'):
                all_context.append(extract_text_from_docx(f))
            else:
                all_context.append(process_audio(f))
    
    with st.spinner("Synthesizing final documents..."):
        # Explicit date instruction
        date_instr = f"MANDATORY: Today is {current_date_val}. Replace all [Current Date] placeholders."
        
        res_det = client.models.generate_content(model=GEMINI_MODEL, contents=[date_instr, PROFESSIONAL_PROMPT, "\n\n".join(all_context)])
        st.session_state.detailed = res_det.text
        
        res_con = client.models.generate_content(model=GEMINI_MODEL, contents=[date_instr, CONCISE_PROMPT, res_det.text])
        st.session_state.concise = res_con.text
    st.success("Analysis Complete!")

# --- TOP DOWNLOAD BUTTONS ---
if st.session_state.detailed:
    t1, t2 = st.tabs(["Detailed Minutes", "Executive Flash Report"])
    for tab, content, title, key_p in zip([t1, t2], [st.session_state.detailed, st.session_state.concise], 
                                           ["Detailed Minutes", "Flash Report"], ["d", "c"]):
        with tab:
            c1, c2, c3 = st.columns(3)
            c1.download_button("Download Word", create_docx(content, title), f"{title}.docx", key=f"{key_p}_w")
            c2.download_button("Download PDF", create_pdf(content, title), f"{title}.pdf", key=f"{key_p}_p")
            c3.download_button("Download Text", content.encode('utf-8'), f"{title}.txt", key=f"{key_p}_t")
            st.markdown(f'<div class="document-card">{content}</div>', unsafe_allow_html=True)