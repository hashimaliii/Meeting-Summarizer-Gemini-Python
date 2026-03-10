import streamlit as st
import tempfile
import os
import io
import math
from datetime import datetime
from docx import Document
from fpdf import FPDF
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
    """Uses multi_cell to prevent word truncation and strips Markdown."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, title, ln=True, align='C')
    pdf.ln(10)

    # Sanitize and strip formatting that causes fragmentation
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-')
    text = "".join(i for i in text if ord(i) < 256)
    
    pdf.set_font("Helvetica", size=11)
    for line in text.split('\n'):
        line = line.strip().replace('**', '').replace('#', '')
        if not line:
            pdf.ln(4)
            continue
        try:
            # Fixes truncation seen in Detailed.pdf
            pdf.multi_cell(w=190, h=7, txt=line, border=0, align='L')
        except:
            continue
    return bytes(pdf.output())

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
            c1.download_button("Word", create_docx(content, title), f"{title}.docx", key=f"{key_p}_w")
            c2.download_button("PDF", create_pdf(content, title), f"{title}.pdf", key=f"{key_p}_p")
            c3.download_button("Text", content.encode('utf-8'), f"{title}.txt", key=f"{key_p}_t")
            st.markdown(f'<div class="document-card">{content}</div>', unsafe_allow_html=True)