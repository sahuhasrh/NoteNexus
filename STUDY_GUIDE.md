# NotesNexus System Design Guide

## Problem

Lecture videos often contain useful slide text, formulas, definitions, and diagrams, but the browser treats the video as pixels. Students have to pause, zoom, and manually retype content. NotesNexus turns video text into selectable browser text and builds a lightweight note-taking layer on top of captured lecture content.

## Product Flow

1. User opens a page with an HTML5 `<video>`.
2. User clicks **Start NotesNexus** in the extension popup.
3. `client/inject.js` captures video frames and sends them to `client/ocr-worker.js`.
4. The worker hashes the frame. If unchanged, it skips all network and backend work.
5. If changed, the worker compresses the frame and sends it to Flask.
6. Flask preprocesses the image, runs Tesseract OCR, extracts key terms, and stores useful slide text.
7. The content script draws transparent selectable text overlays above the video.
8. The popup accumulates lecture key terms across slides and stores them per video URL.
9. User can click **Summarize Notes**, **Ask**, or **Show Slide Timeline**.

## Architecture

```text
Chrome Popup
    |
    v
inject.js on video page
    |
    | ImageBitmap frames
    v
ocr-worker.js
    |-- frame hash
    |-- backpressure queue
    |-- JPEG compression
    |
    | POST /process
    v
Flask Backend
    |-- OpenCV preprocessing
    |-- Tesseract OCR
    |-- YAKE keywords
    |-- SQLite timeline
    |
    v
Popup + video overlays
```

## Frontend Design

### `client/inject.js`

The content script is responsible for page interaction only:

- Finds the page `<video>` element.
- Captures frames to canvas.
- Converts the canvas to `ImageBitmap`.
- Sends frames to the Web Worker.
- Draws transparent selectable text overlays.
- Clears old overlays before every redraw to prevent overlap.

It intentionally does not run OCR, make backend requests, or do heavy frame hashing on the page thread anymore.

### `client/ocr-worker.js`

The worker handles the expensive path:

- Computes a 32x32 grayscale perceptual-ish hash with `OffscreenCanvas`.
- Compares hash distance against the previous frame.
- Skips unchanged frames before any base64 encoding or network call.
- Downscales frames to 50%.
- Converts frames to JPEG at 85% quality.
- Sends changed frames to `/process`.
- Uses a latest-frame-only queue for backpressure.

This keeps video playback smoother because CPU-heavy image processing and request management are outside the main page execution path.

## Performance Optimizations

### 1. Browser-Side Frame Hashing

Earlier designs sent every captured frame to the backend just to learn that nothing changed. The current design hashes frames in the browser worker first.

Impact:

- No base64 encoding for unchanged frames.
- No HTTP request for unchanged frames.
- No backend OCR for unchanged frames.
- Lower CPU, memory, and network usage.

### 2. Web Worker Offloading

Hashing, compression, and network request flow happen in `ocr-worker.js`, not directly in `inject.js`.

Why this matters:

- The video page remains responsive.
- Canvas/image work is less likely to stutter playback.
- The capture loop stays small and predictable.

### 3. Backpressure Queue

OCR can be slower than the capture interval. Instead of letting requests pile up, the worker keeps:

- `processing`: the current frame being processed.
- `pending`: only the latest waiting frame.

If another frame arrives while OCR is running, the older pending frame is dropped. This is the right behavior for live video because stale frames are less valuable than the newest frame.

Benefits:

- Prevents request pileups.
- Avoids memory growth from queued images.
- Protects the Flask server from burst overload.
- Keeps overlays closer to the current video state.

### 4. Image Compression Before Upload

The worker downscales the frame and sends JPEG instead of full-resolution PNG.

Current strategy:

- 50% width and height.
- JPEG quality 0.85.
- Backend still receives enough visual detail for Tesseract after preprocessing.

Why it helps:

- PNG video frames are large.
- JPEG payloads are much smaller.
- Smaller requests mean lower latency and less backend pressure.

### 5. Progressive Slide Reveal Merging

Many lecture slides reveal bullet points one by one. A naive OCR timeline treats each reveal as a new slide. `backend/database.py` compares word overlap and sequence similarity, then updates the latest slide row when the new text is basically the same slide with more content.

Benefits:

- Cleaner slide timeline.
- Better summaries because repeated partial slide text is reduced.
- More accurate slide numbering.

## Backend Design

### `backend/app.py`

Routes:

- `GET /`: health/welcome route.
- `GET /test`: simple status check.
- `POST /process`: OCR one changed frame.
- `POST /summarize`: summarize captured text for the current page.
- `POST /ask`: answer a question using captured text for the current page.
- `GET /timeline`: return slide timeline for a page URL.
- `GET /notes`: return saved summary and full text for a page URL.

### `backend/ocr.py`

OCR pipeline:

1. Decode base64 image.
2. Decode image bytes through OpenCV.
3. Resize 2x for OCR readability.
4. Convert to grayscale.
5. Increase contrast.
6. Apply Otsu thresholding.
7. Run `pytesseract.image_to_data`.
8. Return text, confidence, bounding boxes, and source image dimensions.

The returned image dimensions are important because the frontend uses them to scale OCR boxes back onto the displayed video.

### `backend/database.py`

SQLite stores:

- Slide text.
- Slide number.
- Video timestamp.
- Per-URL summaries.

The backend uses similarity checks to avoid duplicate slides:

- Exact normalized text match.
- Word-overlap match for progressive reveals.
- `SequenceMatcher` fallback for near-duplicate OCR output.

If a new OCR result is the same logical slide but has more text, the existing slide row is updated instead of inserting a duplicate.

### `backend/ner.py`

YAKE is used locally to extract:

- Technical keywords and two-word concepts.
- Proper nouns with a small regex pass.
- Filtered terms that remove common YouTube/UI noise such as subscribe, share, like, channel, notification, and sponsor.

The popup labels this as **Lecture key terms** because keyword extraction is more useful for lecture slides than strict named-entity recognition. Terms accumulate across the lecture instead of disappearing when the slide changes.

### Popup Term Accumulation

`client/src/browser_action/popup.js` keeps a unique list of terms for the active URL. `client/background.js` also stores OCR terms when the popup is closed, so reopening the popup still shows the lecture-wide term list.

Storage key format:

```text
notesnexus_terms_<page_url>
```

Both backend and popup filter common video-platform words so terms like `subscribe`, `share`, and `YouTube channel` do not pollute the lecture concepts.

### `backend/gemini.py`

Gemini is intentionally not called during live capture.

It is only used when the user clicks:

- **Summarize Notes**
- **Ask**

This avoids slow automatic LLM calls, lowers quota usage, and keeps live OCR responsive.

## Data Model

### `slides`

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
url TEXT NOT NULL
text TEXT NOT NULL
slide_number INTEGER
timestamp TEXT
created_at TEXT DEFAULT CURRENT_TIMESTAMP
```

### `sessions`

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
url TEXT NOT NULL UNIQUE
summary TEXT
updated_at TEXT DEFAULT CURRENT_TIMESTAMP
```

## API Details

### `POST /process`

Request:

```json
{
  "imageData": "base64 jpeg",
  "page_url": "https://example.com/lecture",
  "timestamp": "12:34"
}
```

Response:

```json
{
  "saved": true,
  "lines": [
    {
      "text": "Gradient Descent",
      "bounding_box": { "x": 40, "y": 90, "width": 300, "height": 32 },
      "confidence": 87.2
    }
  ],
  "entities": [{ "entity": "Gradient Descent", "label": "KEYWORD" }],
  "full_text": "Gradient Descent ...",
  "slide_number": 3,
  "image_width": 640,
  "image_height": 360
}
```

### `POST /summarize`

Uses all captured text for a page URL and returns structured notes:

- Summary
- Key concepts
- Entities
- Bullet notes

### `POST /ask`

Answers a user question using captured lecture content only.

### `GET /timeline`

Returns the deduplicated slide timeline with timestamps.

### `GET /notes`

Returns saved summary and full captured text.

## Reliability And Failure Handling

- If no video exists, capture exits quietly.
- If a frame is unchanged, no backend request is made.
- If OCR is slower than capture, old pending frames are dropped.
- If backend returns an error, the worker posts an error message instead of crashing the page.
- If the user stops capture, overlays are cleared and worker hash state is reset.
- Old overlays are always removed before drawing new overlays.
- Key terms are accumulated per URL and filtered for common YouTube/UI text.

## Why This Is More Than A Basic OCR Demo

NotesNexus handles real-time constraints that show up in production systems:

- Main-thread protection with workers.
- Load shedding through backpressure.
- Payload reduction through compression.
- Duplicate suppression in persistent storage.
- Explicit expensive-operation boundaries for LLM usage.
- Coordinate mapping between OCR image space and browser layout space.
- Separation of responsibilities between popup, content script, worker, and backend.

## Setup

```powershell
cd E:\Project\NotesNexus
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
cd backend
python app.py
```

If Tesseract is missing, install it from:

```text
https://github.com/UB-Mannheim/tesseract/wiki
```

After changing extension files, reload NotesNexus from `chrome://extensions`.
