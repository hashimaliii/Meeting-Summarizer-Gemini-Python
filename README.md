# Enterprise Meeting Summarizer

A sleek, enterprise-grade web application built with Streamlit and the latest Google GenAI SDK (Gemini 2.5 Flash). This tool ingests raw meeting audio (or text transcripts) and automatically generates highly structured, boardroom-ready meeting minutes, extracting key decisions, data points, and actionable items.

## Features

* **Direct Audio Processing:** Bypasses standard file size limits by utilizing Gemini's native File API. Easily handles large audio files (like 65MB+ `.m4a` files) without complex chunking or FFmpeg dependencies.
* **Modern AI Architecture:** Powered by Google's `gemini-2.5-flash` model via the modern `google-genai` SDK for maximum speed and reliability.
* **Professional Formatting:** Utilizes a strict low-temperature prompt architecture to ensure the AI acts as a Corporate Secretary, generating factual, exhaustive, and highly structured minutes.
* **Multi-Format Export:** Instantly download the generated minutes in three standard corporate formats:
  * Plain Text (`.txt`)
  * Microsoft Word (`.docx`)
  * Portable Document Format (`.pdf`)
* **Enterprise UI:** A clean, minimal, emoji-free user interface.

## Prerequisites

To run this application, you must have:
* **Python 3.10+** installed.
* A free Gemini API key from [Google AI Studio](https://aistudio.google.com/).

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/hashimaliii/Meeting-Summarizer-Gemini-Python.git
   cd meeting-summarizer-gemini-python
   ```

2. **Install the required dependencies:**
   It is recommended to use a virtual environment. Once activated, run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure your API Key:**
   Create a file named `.env` in the root directory of the project. Add your Google Gemini API key to this file:
   ```env
   GEMINI_API_KEY=your_actual_api_key_goes_here
   ```
   *Note: The `.env` file is included in the `.gitignore` to ensure your key is never pushed to version control.*

## Usage

1. Start the Streamlit server from your terminal:
   ```bash
   python -m streamlit run app.py
   ```
2. Your default web browser will open to the application interface.
3. Drag and drop a supported file format (`.mp3`, `.m4a`, `.wav`, or `.txt`) into the upload zone.
4. Wait for the analysis to complete. Review the generated document and select your preferred export format at the bottom of the page.

## License

This project is open-source and available under the MIT License.