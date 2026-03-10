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

# 1. Environment & Date Logic
load_dotenv()
client = genai.Client()

# System date to replace [Current Date] placeholders
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

# --- EXPORT ENGINES ---

def create_pdf(text, title="Official Document"):
    """Fixed PDF engine: Strips Markdown and uses multi_cell to prevent fragmentation."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, title, ln=True, align='C')
    pdf.ln(10)

    # Sanitize for Latin-1 and strip fragmentation-causing characters
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-')
    text = "".join(i for i in text if ord(i) < 256)

    pdf.set_font("Helvetica", size=11)
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        
        # Strip Markdown (** and #) that breaks horizontal alignment in FPDF
        clean_line = line.replace('**', '').replace('#', '').strip()
        if clean_line:
            try:
                # multi_cell ensures text wraps correctly within margins
                pdf.multi_cell(w=190, h=7, txt=clean_line, border=0, align='L')
            except:
                continue
    return bytes(pdf.output())

def create_docx(text, title="Meeting Minutes"):
    """Generates professional Word document."""
    doc = Document()
    doc.add_heading(title, 0)
    for line in text.split('\n'):
        line = line.strip()
        if line:
            doc.add_paragraph(line.replace('**', '').replace('#', '').strip())
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

def create_txt(text):
    """Generates simple clean text file."""
    clean_text = text.replace('**', '').replace('# ', '')
    return clean_text.encode('utf-8')

# --- UI STYLING ---
st.set_page_config(page_title="Minutes AI Pro", layout="centered")

st.markdown(f"""
    <style>
    .stApp {{ background-color: #0F172A; color: #F8FAFC; }}
    
    /* Remove ghost boxes and empty containers */
    [data-testid="stVerticalBlock"] > div:empty {{ display: none !important; }}

    div.stButton > button {{ 
        background-color: #FACC15 !important; 
        color: #0F172A !important; 
        font-weight: 700; width: 100%; border-radius: 8px; padding: 12px;
    }}
    
    .stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid #334155; }}
    .stTabs [aria-selected="true"] {{ color: #FACC15 !important; border-bottom: 2px solid #FACC15 !important; }}

    .document-card {{ 
        background-color: #1E293B; 
        padding: 2.5rem; 
        border-radius: 12px; 
        margin-top: 1rem;
        color: #E2E8F0; 
    }}
    
    /* Style for the top-row download buttons */
    .download-row {{ margin-bottom: 20px; }}
    </style>
""", unsafe_allow_html=True)

# --- APP INTERFACE ---
st.title("Minutes AI: Multi-Source Synthesis")
st.write(f"Meeting Context Date: **{current_date_str}**")

if "detailed" not in st.session_state: st.session_state.detailed = None
if "concise" not in st.session_state: st.session_state.concise = None

uploaded_files = st.file_uploader("Upload Audio or Text Assets", type=['mp3', 'wav', 'txt'], accept_multiple_files=True)

if uploaded_files and st.button("Merge & Generate Minutes"):
    all_context = []
    for f in uploaded_files:
        if f.name.endswith('.txt'):
            all_context.append(f"Source ({f.name}):\n" + f.read().decode("utf-8"))
    
    with st.spinner("Synthesizing final documents..."):
        # FORCE date injection
        date_instr = f"MANDATORY: Use '{current_date_str}' as the meeting date. Do not use placeholders."
        
        # Detailed pass
        res_det = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[date_instr, PROFESSIONAL_PROMPT, "\n\n".join(all_context)]
        )
        st.session_state.detailed = res_det.text
        
        # Concise pass
        res_con = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[date_instr, CONCISE_PROMPT, res_det.text]
        )
        st.session_state.concise = res_con.text
    st.success("Analysis Complete!")

# --- DISPLAY WITH TOP BUTTONS ---
if st.session_state.detailed:
    t1, t2 = st.tabs(["Detailed Minutes", "Executive Flash Report"])
    
    with t1:
        # BUTTONS AT TOP
        st.markdown('<div class="download-row">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.download_button("Download PDF", create_pdf(st.session_state.detailed, "Detailed Minutes"), "Detailed.pdf", key="pdf_det")
        c2.download_button("Download Word", create_docx(st.session_state.detailed, "Detailed Minutes"), "Detailed.docx", key="word_det")
        c3.download_button("Download Text", create_txt(st.session_state.detailed), "Detailed.txt", key="txt_det")
        st.markdown('</div>', unsafe_allow_html=True)
        
        # DOCUMENT CONTENT
        st.markdown(f'<div class="document-card">{st.session_state.detailed}</div>', unsafe_allow_html=True)

    with t2:
        # BUTTONS AT TOP
        st.markdown('<div class="download-row">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.download_button("Download PDF", create_pdf(st.session_state.concise, "Flash Report"), "FlashReport.pdf", key="pdf_con")
        c2.download_button("Download Word", create_docx(st.session_state.concise, "Flash Report"), "FlashReport.docx", key="word_con")
        c3.download_button("Download Text", create_txt(st.session_state.concise), "FlashReport.txt", key="txt_con")
        st.markdown('</div>', unsafe_allow_html=True)
        
        # DOCUMENT CONTENT
        st.markdown(f'<div class="document-card">{st.session_state.concise}</div>', unsafe_allow_html=True)