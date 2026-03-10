import streamlit as st
import tempfile
import os
import io
import math
from datetime import datetime
from docx import Document
from fpdf import FPDF
from dotenv import load_dotenv
from pydub import AudioSegment
from google import genai
from google.genai import types

# 1. Setup & Dynamic Date Capture
load_dotenv()
client = genai.Client()

# Capture the current dynamic date for injection
current_date_str = datetime.now().strftime("%B %d, %Y")

# Fetch the system prompt from the .env file
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
CONCISE_PROMPT = os.getenv("CONCISE_PROMPT", "You are a Chief of Staff. Summarize the following meeting notes into a 'Flash Report'. Focus only on the 3 most critical outcomes, the 5 most urgent action items, and any major blockers. Keep it under 300 words. Use bullet points for readability.")
PROFESSIONAL_PROMPT = os.getenv("PROFESSIONAL_PROMPT", """
You are a Senior Corporate Secretary. Your task is to listen to the provided meeting audio/transcript and generate exhaustive, professional meeting minutes. 
Do not leave out any discussed topics. Capture the nuance, data points, and different perspectives shared.

Please format the document strictly using the following structure:

# Official Meeting Minutes

## 1. Executive Summary
Provide a concise, high-level summary (3-4 sentences) of the meeting's primary objective and overall outcome.

## 2. Detailed Discussion Points
Break down *every* topic discussed in the meeting. For each topic, include:
* Context: What was the issue/topic?
* Key Arguments/Perspectives: What were the different viewpoints shared?
* Data/Metrics: Include any specific numbers, dates, or financial figures.

## 3. Key Decisions Made
List all formal decisions and agreements reached.

## 4. Action Items
* Task Description - Assigned to: Name | Deadline: Date

## 5. Parking Lot / Next Steps
List any topics tabled for future meetings, or the agreed-upon date for the next follow-up.
""")

# --- HARDENED PDF EXPORTER (Fixes Trimmed Text) ---
def create_pdf(text, title="Official Document"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Page Setup
    effective_width = 190
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(effective_width, 10, title, ln=True, align='C')
    pdf.ln(10)

    # 1. Sanitize and Clean Markdown
    # FPDF automatic line breaks are confused by symbols like ** or #. 
    # We strip them out before passing to multi_cell to prevent trimmed lines.
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-')
    text = "".join(i for i in text if ord(i) < 256) # Ensure Latin-1 Compatibility

    pdf.set_font("Helvetica", size=11)
    
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            pdf.ln(4) # Standardized empty line spacer
            continue
        
        # Surgical stripping of Markdown symbols
        clean_line = line.replace('**', '').replace('#', '').strip()
        
        if clean_line:
            try:
                # Use a stable height and effective width for perfect wrapping
                pdf.multi_cell(w=effective_width, h=7, txt=clean_line, border=0, align='L')
            except Exception:
                continue
                
    return bytes(pdf.output())

def create_docx(text, title="Meeting Minutes"):
    doc = Document()
    doc.add_heading(title, 0)
    for line in text.split('\n'):
        if line.strip():
            # Standardize cleaned text for DOCX too
            doc.add_paragraph(line.replace('**', '').replace('#', '').strip())
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

# --- AUDIO PROCESSING ENGINE ---
def get_audio_summary(file_obj):
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
                    contents=["Summarize this segment exhaustively.", g_file]
                )
                summaries.append(res.text)
                client.files.delete(name=g_file.name)
                os.remove(c_tmp.name)
        return "\n".join(summaries)
    finally:
        if os.path.exists(path): os.remove(path)

# --- UI CSS (Cleans up Tab UI) ---
st.set_page_config(page_title="Minutes AI Pro", layout="centered")

st.markdown(f"""
    <style>
    /* Dark Mode App Setup */
    .stApp {{ background-color: #0F172A; color: #F8FAFC; }}
    
    /* Hide empty vertical blocks that create ghost UI issues */
    [data-testid="stVerticalBlock"] > div:empty {{ display: none !important; }}

    /* Primary Generate Button - Bright Yellow */
    div.stButton > button {{ 
        background-color: #FACC15 !important; 
        color: #0F172A !important; 
        font-weight: 700; width: 100%; border: none; padding: 10px; border-radius: 8px;
        margin-bottom: 20px;
    }}
    
    /* Clean Tab Headers - Minimalist Underline Vibe */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 24px;
        background-color: transparent;
        border-bottom: 1px solid #334155;
    }}

    .stTabs [data-baseweb="tab"] {{
        height: 50px;
        background-color: transparent !important;
        border: none !important;
        color: #94A3B8 !important;
    }}

    .stTabs [aria-selected="true"] {{
        color: #FACC15 !important;
        font-weight: 700 !important;
        border-bottom: 2px solid #FACC15 !important;
    }}

    .stTabs [data-baseweb="tab-highlight"] {{ display: none !important; }}

    /* Content Card */
    .document-card {{ 
        background-color: #1E293B; 
        padding: 2rem; 
        border-radius: 12px; 
        margin-top: 20px;
        margin-bottom: 20px;
        color: #E2E8F0; 
        line-height: 1.6;
        border: none;
    }}
    
    /* Download Buttons */
    .stDownloadButton button {{
        background-color: transparent !important;
        color: #FACC15 !important;
        border: 1px solid #FACC15 !important;
        width: 100%;
    }}
    </style>
""", unsafe_allow_html=True)

# --- MAIN UI ---
st.title("Minutes AI: Multi-Source Synthesis")
st.write(f"Context date for minutes: **{current_date_str}**")

# Session State
if "detailed" not in st.session_state: st.session_state.detailed = None
if "concise" not in st.session_state: st.session_state.concise = None

uploaded_files = st.file_uploader("Upload Audio (Breakout Sessions) or Notes (TXT)", type=['mp3', 'wav', 'm4a', 'txt'], accept_multiple_files=True)

# THE GENERATE BUTTON - Brought back to primary placement
if uploaded_files and st.button("Generate Documents", key="primary_gen_btn"):
    all_context = []
    
    for f in uploaded_files:
        with st.spinner(f"Reading {f.name}..."):
            if f.name.endswith('.txt'):
                content = f.read().decode("utf-8")
                all_context.append(f"SOURCE FILE ({f.name}):\n{content}")
            else:
                summary = get_audio_summary(f)
                all_context.append(f"AUDIO SOURCE ({f.name}):\n{summary}")
    
    with st.spinner("Merging & Synthesizing Master Data..."):
        master_data = "\n\n--- NEW SOURCE BLOCK ---\n\n".join(all_context)
        
        # Dynamic Date Injection strategy
        date_instruction = f"IMPORTANT: Today's date is {current_date_str}. Replace any [Current Date] placeholders with this exact date."
        
        # Final detailed synthesis pass
        res_det = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[f"{date_instruction}\n\n{PROFESSIONAL_PROMPT}", f"DATA:\n{master_data}"]
        )
        st.session_state.detailed = res_det.text
        
        # Second, concise pass from the detailed minutes
        res_con = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[f"{date_instruction}\n\n{CONCISE_PROMPT}", f"SOURCE MINUTES:\n{res_det.text}"]
        )
        st.session_state.concise = res_con.text
    st.success("Documents Generated Successfully!")

# --- DISPLAY & EXPORT ---
if st.session_state.detailed:
    t1, t2 = st.tabs(["Detailed Minutes", "Executive Flash Report"])
    
    with t1:
        # Wrap the content properly inside the div f-string to prevent ghosting
        st.markdown(f'<div class="document-card">{st.session_state.detailed}</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.download_button("Download Detailed (PDF)", create_pdf(st.session_state.detailed, "Detailed Minutes"), "Detailed_Minutes.pdf")
        c2.download_button("Download Detailed (Word)", create_docx(st.session_state.detailed, "Detailed Minutes"), "Detailed_Minutes.docx")

    with t2:
        st.markdown(f'<div class="document-card">{st.session_state.concise}</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.download_button("Download Concise (PDF)", create_pdf(st.session_state.concise, "Flash Report"), "Flash_Report.pdf")
        c2.download_button("Download Concise (Word)", create_docx(st.session_state.concise, "Flash Report"), "Flash_Report.docx")