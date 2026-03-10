import streamlit as st
import tempfile
import os
import io
from datetime import datetime
from docx import Document
from fpdf import FPDF
from dotenv import load_dotenv
from google import genai

# 1. Setup & Contextual Date Injection
load_dotenv()
client = genai.Client()
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

# --- ENHANCED EXPORT ENGINES ---

def create_pdf(text, title="Official Document"):
    """
    FIXED PDF ENGINE: Uses multi_cell with explicit width to prevent truncation.
    Strips Markdown bolding and headers that confuse FPDF width calculations.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Title Header
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(190, 10, title, ln=True, align='C')
    pdf.ln(10)

    # Sanitize for Latin-1 and remove formatting artifacts
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-')
    text = "".join(i for i in text if ord(i) < 256)

    pdf.set_font("Helvetica", size=11)
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        
        # Strip Markdown characters to ensure correct width calculation
        clean_line = line.replace('**', '').replace('#', '').strip()
        
        if clean_line:
            try:
                # 190mm is standard width for A4 with margins; multi_cell handles wrapping
                pdf.multi_cell(w=190, h=7, txt=clean_line, border=0, align='L')
            except:
                continue
    return bytes(pdf.output())

def create_docx(text, title="Meeting Minutes"):
    """Creates professional Word document without formatting artifacts."""
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
    """Clean text export."""
    return text.replace('**', '').replace('# ', '').encode('utf-8')

# --- UI CONFIGURATION ---
st.set_page_config(page_title="Minutes AI Pro", layout="centered")

st.markdown(f"""
    <style>
    .stApp {{ background-color: #0F172A; color: #F8FAFC; }}
    
    /* Suppress ghost UI artifacts */
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
    </style>
""", unsafe_allow_html=True)

# --- MAIN APP ---
st.title("Minutes AI: Document Synthesis")
st.write(f"Meeting Context Date: **{current_date_str}**")

if "detailed" not in st.session_state: st.session_state.detailed = None
if "concise" not in st.session_state: st.session_state.concise = None

files = st.file_uploader("Upload Notes (TXT)", type=['txt'], accept_multiple_files=True)

if files and st.button("Generate Minutes & Flash Report"):
    all_context = []
    for f in files:
        all_context.append(f.read().decode("utf-8"))
    
    with st.spinner("Synthesizing..."):
        # Explicit date injection to fix [Current Date] placeholder
        date_instr = f"MANDATORY: Use '{current_date_str}' as the actual meeting date."
        
        # Detailed synthesis
        res_det = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[date_instr, PROFESSIONAL_PROMPT, "\n\n".join(all_context)]
        )
        st.session_state.detailed = res_det.text
        
        # Concise report
        res_con = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[date_instr, CONCISE_PROMPT, res_det.text]
        )
        st.session_state.concise = res_con.text
    st.success("Documents Ready!")

# --- DISPLAY WITH TOP EXPORT BUTTONS ---
if st.session_state.detailed:
    t1, t2 = st.tabs(["Detailed Minutes", "Executive Flash Report"])
    
    with t1:
        # Export buttons at top to prevent scrolling
        c1, c2, c3 = st.columns(3)
        c1.download_button("Download PDF", create_pdf(st.session_state.detailed, "Detailed Minutes"), "Detailed.pdf", key="d_pdf")
        c2.download_button("Download Word", create_docx(st.session_state.detailed, "Detailed Minutes"), "Detailed.docx", key="d_word")
        c3.download_button("Download Text", create_txt(st.session_state.detailed), "Detailed.txt", key="d_txt")
        
        st.markdown(f'<div class="document-card">{st.session_state.detailed}</div>', unsafe_allow_html=True)

    with t2:
        c1, c2, c3 = st.columns(3)
        c1.download_button("Download PDF", create_pdf(st.session_state.concise, "Flash Report"), "FlashReport.pdf", key="c_pdf")
        c2.download_button("Download Word", create_docx(st.session_state.concise, "Flash Report"), "FlashReport.docx", key="c_word")
        c3.download_button("Download Text", create_txt(st.session_state.concise), "FlashReport.txt", key="c_txt")
        
        st.markdown(f'<div class="document-card">{st.session_state.concise}</div>', unsafe_allow_html=True)