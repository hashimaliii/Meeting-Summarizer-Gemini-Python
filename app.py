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

# Load environment variables from the .env file
load_dotenv()

# Initialize the GenAI Client
client = genai.Client()

# Fetch the system prompt from the .env file
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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

def create_docx(text):
    """Converts markdown text into a properly formatted Word document."""
    doc = Document()
    for line in text.split('\n'):
        if line.startswith('# '):
            doc.add_heading(line.replace('# ', '').strip(), level=1)
        elif line.startswith('## '):
            doc.add_heading(line.replace('## ', '').strip(), level=2)
        elif line.startswith('### '):
            doc.add_heading(line.replace('### ', '').strip(), level=3)
        elif line.strip():
            p = doc.add_paragraph()
            if line.startswith('* ') or line.startswith('- '):
                p.style = 'List Bullet'
                line = line[2:]
            
            parts = line.split('**')
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    p.add_run(part).bold = True
                else:
                    p.add_run(part)
    
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

def create_pdf(text):
    """Converts markdown text into a cleanly formatted PDF document safely."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=11)
    
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-')
    
    for line in text.split('\n'):
        line = line.strip()
        
        if not line:
            pdf.ln(6)
            continue
            
        if line.startswith('---') or line.startswith('***') or line.startswith('___'):
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 10, "_" * 40, ln=True, align='C')
            pdf.set_text_color(0, 0, 0)
            continue

        try:
            if line.startswith('# '):
                pdf.set_font("Helvetica", 'B', 16)
                pdf.multi_cell(0, 10, line.replace('# ', '').strip() or " ")
                pdf.set_font("Helvetica", size=11)
            elif line.startswith('## '):
                pdf.set_font("Helvetica", 'B', 14)
                pdf.multi_cell(0, 10, line.replace('## ', '').strip() or " ")
                pdf.set_font("Helvetica", size=11)
            elif line.startswith('### '):
                pdf.set_font("Helvetica", 'B', 12)
                pdf.multi_cell(0, 8, line.replace('### ', '').strip() or " ")
                pdf.set_font("Helvetica", size=11)
            else:
                clean_line = line.replace('**', '')
                pdf.multi_cell(0, 6, clean_line)
        except Exception:
            safe_line = " ".join([line[i:i+70] for i in range(0, len(line), 70)])
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 6, safe_line.replace('**', ''))
            
    return bytes(pdf.output())

def process_audio_with_gemini(uploaded_file):
    """Chunks large audio files, processes each part, and synthesizes a final document."""
    file_extension = uploaded_file.name.split('.')[-1].lower()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_audio:
        temp_audio.write(uploaded_file.read())
        temp_audio_path = temp_audio.name

    try:
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        status_text.info("Loading audio file for analysis (this may take a moment for massive files)...")
        audio = AudioSegment.from_file(temp_audio_path)
        
        chunk_length_ms = 45 * 60 * 1000
        total_chunks = math.ceil(len(audio) / chunk_length_ms)
        
        all_summaries = []
        
        for i in range(total_chunks):
            status_text.info(f"Analyzing Part {i+1} of {total_chunks}...")
            progress_bar.progress(i / total_chunks)
            
            start_time = i * chunk_length_ms
            end_time = min((i + 1) * chunk_length_ms, len(audio))
            chunk = audio[start_time:end_time]
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as chunk_temp:
                chunk.export(chunk_temp.name, format="mp3")
                chunk_path = chunk_temp.name
            
            audio_file = client.files.upload(file=chunk_path)
            
            chunk_prompt = "You are a transcriber. Please listen to this portion of a larger meeting. Provide a highly exhaustive summary of every topic discussed, every data point mentioned, and every task assigned in this specific chunk."
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[chunk_prompt, audio_file],
                config=types.GenerateContentConfig(temperature=0.2)
            )
            
            all_summaries.append(response.text)
            
            client.files.delete(name=audio_file.name)
            os.remove(chunk_path)
            
        progress_bar.progress(0.9)
        status_text.info("Synthesizing all parts into the final Official Minutes...")
        
        combined_text = "\n\n--- NEXT PART OF MEETING ---\n\n".join(all_summaries)
        final_prompt = f"{PROFESSIONAL_PROMPT}\n\nHere are the detailed notes from each part of the meeting. Synthesize them into ONE cohesive, perfectly formatted final document:\n\n{combined_text}"
        
        final_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=final_prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        
        progress_bar.progress(1.0)
        status_text.success("Enterprise analysis complete!")
        return final_response.text

    except Exception as e:
        st.error(f"System Error: {e}")
        return None
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

def process_text_with_gemini(text_content):
    try:
        full_prompt = f"{PROFESSIONAL_PROMPT}\n\nTranscript to analyze:\n{text_content}"
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        return response.text
    except Exception as e:
        st.error(f"System Error: {e}")
        return None

# --- UI Configuration & Styling ---
st.set_page_config(page_title="Enterprise Meeting Summarizer", layout="centered", page_icon="📄")

# Forced Dark Mode with Yellow Accents CSS
st.markdown("""
    <style>
    /* Force dark background if config.toml failed */
    .stApp { background-color: #0F172A; color: #F8FAFC; font-family: 'Inter', 'Segoe UI', sans-serif; }
    
    /* Headers */
    .main-header { font-weight: 700; font-size: 2.75rem; color: #F8FAFC; margin-bottom: 0px; letter-spacing: -0.025em; }
    .sub-header { font-size: 1.15rem; color: #94A3B8; margin-bottom: 2.5rem; line-height: 1.6; }
    
    /* File Uploader */
    [data-testid="stFileUploadDropzone"] { background-color: #1E293B !important; border: 2px dashed #475569 !important; border-radius: 8px; padding: 2rem; }
    [data-testid="stFileUploadDropzone"]:hover { border-color: #FACC15 !important; }
    
    /* Main Generate Button - Forced Yellow */
    div.stButton > button:first-child { 
        background-color: #FACC15 !important; 
        color: #0F172A !important; 
        font-weight: 700 !important; 
        border-radius: 6px !important; 
        border: none !important; 
        padding: 0.5rem 2rem !important; 
    }
    div.stButton > button:first-child:hover { background-color: #EAB308 !important; }
    
    /* Download Buttons */
    .stDownloadButton button { border-radius: 6px !important; font-weight: 500 !important; width: 100% !important; color: #F8FAFC !important; border: 1px solid #475569 !important; background-color: transparent !important; }
    .stDownloadButton button:hover { border-color: #FACC15 !important; color: #FACC15 !important; }
    
    /* Document Card Output - Dark mode with Yellow Top Bar */
    .document-card { 
        background-color: #1E293B; 
        border: 1px solid #334155; 
        border-top: 4px solid #FACC15; /* Yellow Accent Line */
        border-radius: 8px; 
        padding: 2rem; 
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3); 
        margin-top: 2rem; 
        margin-bottom: 2rem; 
        color: #E2E8F0; 
    }
    </style>
""", unsafe_allow_html=True)

# Initialize Session State
if "meeting_docs" not in st.session_state:
    st.session_state.meeting_docs = None

st.markdown('<div class="main-header">Enterprise Meeting Summarizer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Upload an audio recording or transcript to generate boardroom-ready meeting minutes.</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("Select File", type=['txt', 'mp3', 'wav', 'm4a'], label_visibility="collapsed")

if uploaded_file is not None:
    # Render the Generate button
    if st.button("Generate Minutes"):
        file_extension = uploaded_file.name.split('.')[-1].lower()
        
        if file_extension == 'txt':
            transcript_text = uploaded_file.read().decode("utf-8")
            with st.spinner("Drafting official minutes..."):
                st.session_state.meeting_docs = process_text_with_gemini(transcript_text)
            
        elif file_extension in ['mp3', 'wav', 'm4a']:
            st.session_state.meeting_docs = process_audio_with_gemini(uploaded_file)

# Display Results if they exist in Session State
if st.session_state.meeting_docs:
    st.markdown('<div class="document-card">', unsafe_allow_html=True)
    st.markdown(st.session_state.meeting_docs)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("### Export Options")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.download_button(
            label="Download TXT",
            data=st.session_state.meeting_docs,
            file_name="Meeting_Minutes.txt",
            mime="text/plain"
        )
        
    with col2:
        docx_data = create_docx(st.session_state.meeting_docs)
        st.download_button(
            label="Download Word",
            data=docx_data,
            file_name="Meeting_Minutes.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
    with col3:
        pdf_data = create_pdf(st.session_state.meeting_docs)
        st.download_button(
            label="Download PDF",
            data=pdf_data,
            file_name="Meeting_Minutes.pdf",
            mime="application/pdf"
        )