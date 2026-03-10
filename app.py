import streamlit as st
import tempfile
import os
import io
import math
from docx import Document
from fpdf import FPDF
from dotenv import load_dotenv
from pydub import AudioSegment

# Import the modern GenAI SDK
from google import genai
from google.genai import types

# 1. Load configuration
load_dotenv()
client = genai.Client()

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

# --- PDF & DOCX EXPORTERS ---
def create_docx(text, title="Meeting Minutes"):
    doc = Document()
    doc.add_heading(title, 0)
    for line in text.split('\n'):
        if line.strip():
            doc.add_paragraph(line.replace('#', '').strip())
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

def create_pdf(text, title="Official Document"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 1. Use a standard width (Page width - margins)
    # A4 is 210mm wide. 10mm margins on each side = 190mm effective width.
    effective_width = 190 

    # 2. Add Title
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(effective_width, 10, title, ln=True, align='C')
    pdf.ln(10)
    
    # 3. Clean and Encode the text
    # Standard fonts only like Latin-1 characters. 
    # We replace common problematic AI characters manually.
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-')
    # Remove any characters that aren't in the Latin-1 range to prevent crashes
    text = "".join(i for i in text if ord(i) < 256)

    pdf.set_font("Helvetica", size=11)
    
    for line in text.split('\n'):
        line = line.strip()
        
        # Skip truly empty lines, but add a spacer
        if not line:
            pdf.ln(5)
            continue
            
        # Clean markdown bolding for the PDF
        clean_line = line.replace('**', '').replace('#', '').strip()
        
        # Ensure we don't pass an empty string to multi_cell after cleaning
        if not clean_line:
            continue

        try:
            # We use effective_width instead of 0 for stability
            pdf.multi_cell(w=effective_width, h=6, txt=clean_line)
        except Exception:
            # Ultimate Fallback: If fpdf still hates the line, 
            # we print it character by character or chunk it manually
            short_chunk = clean_line[:50] + "..."
            pdf.multi_cell(w=effective_width, h=6, txt=short_chunk)
            
    return bytes(pdf.output())

# --- CORE LOGIC ---
def process_audio_to_detailed(uploaded_file):
    """Chunks audio and generates full detailed minutes."""
    file_ext = uploaded_file.name.split('.')[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        status = st.empty()
        progress = st.progress(0)
        audio = AudioSegment.from_file(tmp_path)
        
        chunk_ms = 45 * 60 * 1000 # 45 mins
        total_chunks = math.ceil(len(audio) / chunk_ms)
        all_chunks_text = []

        for i in range(total_chunks):
            status.info(f"Analyzing Part {i+1} of {total_chunks}...")
            progress.progress(i / total_chunks)
            
            chunk = audio[i*chunk_ms : min((i+1)*chunk_ms, len(audio))]
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as c_tmp:
                chunk.export(c_tmp.name, format="mp3")
                c_path = c_tmp.name
            
            g_file = client.files.upload(file=c_path)
            res = client.models.generate_content(
                model='gemini-2.0-flash', # Use the latest flash model
                contents=["Exhaustively transcribe and summarize this part of the meeting.", g_file]
            )
            all_chunks_text.append(res.text)
            client.files.delete(name=g_file.name)
            os.remove(c_path)

        status.info("Synthesizing Final Detailed Minutes...")
        combined = "\n\n".join(all_chunks_text)
        final = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=f"{PROFESSIONAL_PROMPT}\n\nNotes:\n{combined}"
        )
        progress.progress(1.0)
        return final.text
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

# --- UI CONFIG ---
st.set_page_config(page_title="Minutes AI", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #0F172A; color: #F8FAFC; }
    .main-header { font-weight: 700; font-size: 2.5rem; color: #F8FAFC; }
    [data-testid="stFileUploadDropzone"] { background-color: #1E293B !important; border: 2px dashed #475569 !important; }
    div.stButton > button { background-color: #FACC15 !important; color: #0F172A !important; font-weight: 700; width: 100%; }
    .document-card { background-color: #1E293B; border-top: 4px solid #FACC15; padding: 20px; border-radius: 8px; margin: 10px 0; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #1E293B; border-radius: 4px; color: white; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #FACC15 !important; color: #0F172A !important; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">Minutes AI: Dual Mode</div>', unsafe_allow_html=True)
st.write("Upload audio to generate both **Detailed Minutes** and a **Concise Flash Report**.")

# Session State Init
if "detailed" not in st.session_state: st.session_state.detailed = None
if "concise" not in st.session_state: st.session_state.concise = None

uploaded_file = st.file_uploader("Upload Audio", type=['mp3', 'wav', 'm4a'], label_visibility="collapsed")

if uploaded_file and st.button("Generate Both Documents"):
    det = process_audio_to_detailed(uploaded_file)
    if det:
        st.session_state.detailed = det
        with st.spinner("Synthesizing Concise Version..."):
            con = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=f"{CONCISE_PROMPT}\n\nDetailed Source:\n{det}"
            )
            st.session_state.concise = con.text
        st.success("Generation Complete!")

# RESULTS VIEW
if st.session_state.detailed:
    tab1, tab2 = st.tabs(["Detailed Minutes", "Concise Flash Report"])
    
    with tab1:
        st.markdown('<div class="document-card">', unsafe_allow_html=True)
        st.markdown(st.session_state.detailed)
        st.markdown('</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        col1.download_button("Download Detailed (PDF)", create_pdf(st.session_state.detailed, "Detailed Minutes"), "Detailed_Minutes.pdf")
        col2.download_button("Download Detailed (Word)", create_docx(st.session_state.detailed, "Detailed Minutes"), "Detailed_Minutes.docx")

    with tab2:
        st.markdown('<div class="document-card" style="border-top-color: #EAB308;">', unsafe_allow_html=True)
        st.markdown(st.session_state.concise)
        st.markdown('</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        col1.download_button("Download Concise (PDF)", create_pdf(st.session_state.concise, "Flash Report"), "Flash_Report.pdf")
        col2.download_button("Download Concise (Word)", create_docx(st.session_state.concise, "Flash Report"), "Flash_Report.docx")