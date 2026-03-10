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

# 1. Environment and Date Setup
load_dotenv()
client = genai.Client()

# This variable is used to force-replace [Current Date] in the AI output
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

# --- ROBUST PDF EXPORTER ---
def create_pdf(text, title="Official Document"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Header logic
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, title, ln=True, align='C')
    pdf.ln(10)

    # Sanitize text for Latin-1 (removes smart quotes/em-dashes)
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-')
    text = "".join(i for i in text if ord(i) < 256)

    pdf.set_font("Helvetica", size=11)
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        
        # CRITICAL FIX: Strip Markdown symbols (**, #)
        # These symbols cause the PDF engine to miscalculate line width, leading to trimmed text.
        clean_line = line.replace('**', '').replace('#', '').strip()
        
        if clean_line:
            try:
                pdf.multi_cell(w=190, h=7, txt=clean_line, border=0, align='L')
            except Exception:
                continue
                
    return bytes(pdf.output())

# --- AUDIO CHUNKING ENGINE ---
def process_audio(file_obj):
    ext = file_obj.name.split('.')[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(file_obj.read())
        path = tmp.name
    
    try:
        audio = AudioSegment.from_file(path)
        chunk_ms = 45 * 60 * 1000 # 45-minute chunks for Gemini
        chunks_count = math.ceil(len(audio) / chunk_ms)
        summaries = []
        
        for i in range(chunks_count):
            chunk = audio[i*chunk_ms : min((i+1)*chunk_ms, len(audio))]
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as c_tmp:
                chunk.export(c_tmp.name, format="mp3")
                g_file = client.files.upload(file=c_tmp.name)
                res = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=["Provide a highly detailed transcript summary for this segment.", g_file]
                )
                summaries.append(res.text)
                client.files.delete(name=g_file.name)
                os.remove(c_tmp.name)
        return "\n".join(summaries)
    finally:
        if os.path.exists(path): os.remove(path)

# --- UI CONFIG & CSS ---
st.set_page_config(page_title="Minutes AI Pro", layout="centered")

st.markdown(f"""
    <style>
    .stApp {{ background-color: #0F172A; color: #F8FAFC; }}
    
    /* Removes 'Ghost Boxes' by hiding empty Streamlit containers */
    [data-testid="stVerticalBlock"] > div:empty {{ display: none !important; }}

    div.stButton > button {{ 
        background-color: #FACC15 !important; 
        color: #0F172A !important; 
        font-weight: 700; width: 100%; border: none; padding: 12px; border-radius: 8px;
    }}
    
    .stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid #334155; gap: 20px; }}
    .stTabs [aria-selected="true"] {{ color: #FACC15 !important; border-bottom: 2px solid #FACC15 !important; font-weight: bold; }}
    .stTabs [data-baseweb="tab-highlight"] {{ display: none !important; }}

    .document-card {{ 
        background-color: #1E293B; 
        padding: 2.5rem; 
        border-radius: 12px; 
        margin-top: 1.5rem;
        line-height: 1.6;
        color: #E2E8F0;
    }}
    </style>
""", unsafe_allow_html=True)

# --- APP LAYOUT ---
st.title("Minutes AI: Multi-Source Synthesis")
st.write(f"Today's System Date: **{current_date_str}**")

if "detailed" not in st.session_state: st.session_state.detailed = None
if "concise" not in st.session_state: st.session_state.concise = None

uploaded_files = st.file_uploader("Upload Audio or Text Assets", type=['mp3', 'wav', 'm4a', 'txt'], accept_multiple_files=True)

# The Generate Button
if uploaded_files and st.button("Generate Both Documents"):
    all_context = []
    
    for f in uploaded_files:
        with st.spinner(f"Processing {f.name}..."):
            if f.name.endswith('.txt'):
                all_context.append(f.read().decode("utf-8"))
            else:
                all_context.append(process_audio(f))
    
    with st.spinner("Synthesizing final documents..."):
        # MANDATORY DATE INJECTION
        date_instr = f"MANDATORY: Use '{current_date_str}' as the meeting date. Replace all [Current Date] placeholders with this value."
        
        # 1. Detailed Minutes
        res_det = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[date_instr, PROF_PROMPT, "\n\n".join(all_context)]
        )
        st.session_state.detailed = res_det.text
        
        # 2. Flash Report
        res_con = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[date_instr, CONCISE_PROMPT, res_det.text]
        )
        st.session_state.concise = res_con.text
    st.success("Analysis Complete!")

# RESULTS VIEW
if st.session_state.detailed:
    t1, t2 = st.tabs(["Detailed Master Minutes", "Executive Flash Report"])
    
    with t1:
        st.markdown(f'<div class="document-card">{st.session_state.detailed}</div>', unsafe_allow_html=True)
        st.download_button("Download Detailed PDF", create_pdf(st.session_state.detailed, "Detailed Minutes"), "Detailed.pdf")
        
    with t2:
        st.markdown(f'<div class="document-card">{st.session_state.concise}</div>', unsafe_allow_html=True)
        st.download_button("Download Flash Report PDF", create_pdf(st.session_state.concise, "Flash Report"), "FlashReport.pdf")