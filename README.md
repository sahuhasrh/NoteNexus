# NotesNexus

NotesNexus is a Chrome extension and Flask backend that makes text inside lecture videos selectable, searchable, and summarizable. It captures video frames, runs OCR only when the slide changes, draws invisible selectable text overlays on top of the video, and lets users generate notes or ask questions from captured lecture content.

## Highlights

- Select and copy text directly from video lectures.
- Browser-side frame hashing avoids unnecessary backend calls.
- Web Worker offloads frame hashing, compression, and OCR requests away from the page UI thread.
- Backpressure queue keeps only the latest pending frame when OCR is slow.
- JPEG downscaling reduces frame payload size before upload.
- SQLite timeline merges progressive slide reveals into one logical slide.
- Lecture key terms accumulate across slides and filter common YouTube UI noise.
- Gemini is called only on explicit user actions: summarize or ask.

## Tech Stack

- Chrome Extension Manifest V3
- JavaScript, Web Workers, OffscreenCanvas
- Flask, SQLite
- Tesseract OCR through `pytesseract`
- OpenCV + NumPy preprocessing
- YAKE keyword extraction
- Gemini API for summaries and Q&A

## Supported Platforms

NotesNexus works on browser-based video platforms that expose an accessible HTML5 `<video>` element.

Expected to work:

- YouTube
- Google Meet in browser
- Zoom web
- Microsoft Teams web
- Discord web
- Coursera, Udemy, edX
- Vimeo, Loom

Limitations:

- Native desktop apps like Zoom desktop or Teams desktop are not supported.
- Some DRM-protected or restricted video sites may block frame capture.
- Platforms without a normal `<video>` element cannot be captured by the extension.

## Quick Start

```powershell
cd E:\Project\NotesNexus
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install Tesseract for Windows if needed:

```text
https://github.com/UB-Mannheim/tesseract/wiki
```

Create `backend\.env`:

```text
GEMINI_API_KEY=your_key_here
```

Start backend:

```powershell
cd E:\Project\NotesNexus\backend
python app.py
```

Load the extension from `client/` in `chrome://extensions`.

## Docs

See [STUDY_GUIDE.md](STUDY_GUIDE.md) for the full system design, performance optimizations, data flow, API routes, and implementation notes.
