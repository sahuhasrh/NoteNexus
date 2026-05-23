# NotesNexus — Technical Study Guide

## Project Overview

NotesNexus is a Chrome extension that makes on-screen video text selectable and copyable, like a normal webpage. It captures video frames, runs local OCR on a Flask backend, and draws transparent HTML overlays aligned to detected text regions.

It solves the problem of taking notes from fast-moving lecture videos where pausing and retyping slides is tedious. It works on any site that renders video in an HTML5 `<video>` element, including YouTube, Google Meet, and Discord, because those platforms expose standard `<video>` elements that support `captureStream()` and `ImageCapture`.

---

## Core Mechanism — How Text Selection on Video Works

1. **Frame capture (`client/inject.js`)**  
   Every 3 seconds, the content script finds `document.querySelector("video")`, calls `video.captureStream()`, grabs one frame with `ImageCapture.grabFrame()`, and draws it to a hidden off-screen canvas (`#ghost`).

2. **Send to Flask**  
   The canvas is exported as a base64 PNG data URL. The prefix `data:image/png;base64,` is stripped and the raw base64 string is POSTed to `http://localhost:8000/process` as `{ "imageData": "<base64>" }`.

3. **PaddleOCR (`backend/ocr.py`)**  
   Flask decodes base64 → PIL image → numpy array. PaddleOCR returns polygons and text per detection. Each polygon is converted to `{ x, y, width, height }` plus `text`, matching the format GCP Vision used.

4. **Coordinate scaling (`client/inject.js`)**  
   OCR coordinates are in native frame pixels. The script scales them to the displayed video size:
   - `wScale = video.offsetWidth / frameWidth`
   - `hScale = video.offsetHeight / frameHeight`
   - Overlay position: `x * wScale`, `y * hScale`, etc.

5. **HTML overlays**  
   For each line, a `<div>` is created with `position: absolute`, `color: transparent`, `userSelect: text`, and `fontSize` set from bounding box height. The div is placed at the scaled screen position over the video. Transparent text sits on top of visible video text so the user can drag-select and copy.

6. **Live video**  
   The interval loop re-grabs frames and only redraws overlays when detected text changes (`isDifferent`), so overlays track new slides without breaking the core selection behavior.

---

## Architecture Diagram

```
[Chrome Extension — client/]
      |
      | video frame (base64)
      v
[Flask Backend :8000]
      |
      ├── PaddleOCR → text + bounding boxes
      |       ↓
      |   returned to extension
      |       ↓
      |   HTML divs drawn over video
      |
      ├── Gemini 1.5 Flash → structured summary
      |
      ├── spaCy → named entities (key topics)
      |
      ├── sentence-transformers → embeddings
      |         ↓
      |     ChromaDB (local vector store)
      |
      ├── POST /ask → RAG → Gemini → answer
      |
      └── SQLite (notes.db) → saved notes
```

---

## Complete File Structure

### Repository layout

| Path | Purpose |
|------|---------|
| `client/` | **Working Chrome extension** (load this in Chrome) |
| `client2.0/` | Older/experimental fork (“Injecta”); not the primary extension |
| `backend/` | Flask API server |
| `test/` | Manual test page (unchanged) |
| `requirements.txt` | Python dependencies |
| `STUDY_GUIDE.md` | This document |

---

### `client/manifest.json`

Chrome MV2 manifest for NotesNexus.

- **Permissions:** `https://*/*`, `http://*/*`, `activeTab`, `tabs`, `storage` — needed to inject scripts, read tab URLs, and persist popup UI state.
- **background.js:** Runs persistently; injects `inject.js` when popup signals capture.
- **browser_action:** Popup at `src/browser_action/browser_action.html`.

---

### `client/inject.js` (core overlay — do not modify behavior)

**Classes**

| Class | Role |
|-------|------|
| `Rect(x, y, width, height, value)` | Stores one text region and its string |
| `Canvas` | Manages overlay divs and clearing |

**Functions**

| Function | Inputs | Returns | Description |
|----------|--------|---------|-------------|
| `getAPI(data)` | `data`: data URL string | `Promise<object>` | Strips data-URL prefix, POSTs base64 to `/process`, returns JSON |
| `isDifferent(seen, incoming)` | `seen`: object map, `incoming`: Rect[] | `boolean` | True if any new text line appeared |
| `main()` | none | void | Creates ghost canvas, starts 3s interval loop |

**`Canvas.showRects(rects)`**  
- Input: `Rect[]`  
- Creates absolutely positioned transparent `<div>` elements over the video using scaled coordinates.  
- Sets `z-index` high and `userSelect: text` so text is selectable.

---

### `client/background.js`

| Listener | Trigger | Action |
|----------|---------|--------|
| `chrome.runtime.onMessage` | `{ myPopupIsOpen: true }` | `chrome.tabs.executeScript` with `inject.js` |
| `chrome.browserAction.onClicked` | Toolbar click (no popup) | Injects `inject.js` |

---

### `client/src/browser_action/popup.js`

| Function | Inputs | Returns | Description |
|----------|--------|---------|-------------|
| `getActiveTabUrl()` | none | `Promise<string>` | Queries active tab URL for SQLite/RAG keys |
| `appendAccumulatedText(newText)` | `string` | void | Appends OCR text to `chrome.storage.local` |
| `loadSavedNotes(pageUrl)` | URL string | `Promise<void>` | GET `/notes` and fills popup lists |

**Event handlers**

- **Capture button:** Sends `{ myPopupIsOpen: true }` to background → inject starts.
- **`chrome.runtime.onMessage`:** Receives OCR results from inject; updates notes, entities, summary UI.
- **Take Notes:** POST `/index_notes` + `/summarize` with accumulated text.
- **Ask:** POST `/ask` with question + tab URL.

---

### `client/src/browser_action/browser_action.html`

Popup UI: capture button, Take Notes, Q&A input, notes/entities/summary tabs.

---

### `client/src/content/content.js`

Legacy content script; responds to `report_back` messages with page HTML. Not used by the main overlay flow.

---

### `client/js/framegrab.js`

Early prototype of frame grab + overlay logic; superseded by `inject.js`.

---

### `backend/app.py`

Flask application entry point.

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `root()` | none | JSON welcome | Health check |
| `test()` | none | JSON | Simple test route |
| `new_session()` | none | `{ uuid }` | Session id (legacy) |
| `process()` | POST JSON | OCR + NER + summary | Main frame processing |
| `summarize()` | POST JSON | summary + entities | Gemini summarization |
| `index_notes()` | POST JSON | chunk count | RAG indexing |
| `ask()` | POST JSON | `{ answer }` | RAG Q&A |
| `notes()` | GET `page_url` | saved notes list | SQLite load |

---

### `backend/ocr.py`

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `paddle_ocr(image_content)` | base64 string | `(paragraphs, lines)` | Runs PaddleOCR; maps boxes to GCP-compatible format |
| `gcp_ocr` | alias | same | Backward-compatible name for `app.py` |

**Line format (unchanged for extension):**

```json
{
  "text": "Hello world",
  "bounding_box": { "x": 10, "y": 20, "width": 200, "height": 24 }
}
```

---

### `backend/summarization.py`

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `summarize_gemini(text)` | `str` | `str` | Calls Gemini 1.5 Flash with lecture-assistant prompt |
| `summarize_bart(text)` | `str` | `str` | Alias → `summarize_gemini` |

---

### `backend/ner.py` (unchanged)

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `ner_spacy(text)` | `str` | `list[{entity, label}]` | spaCy NER on English text |

---

### `backend/rag.py`

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `chunk_text(text)` | text, optional sizes | `list[str]` | 200-word chunks, 50-word overlap |
| `index_lecture_text(page_url, text)` | URL, text | `{ chunks_indexed }` | Embeds chunks, stores in ChromaDB |
| `ask_question(page_url, question)` | URL, question | `str` | Top-3 retrieval + Gemini answer |

---

### `backend/database.py`

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `init_db()` | none | void | Creates `notes` table if missing |
| `save_note(...)` | url, text, summary, entities | void | INSERT into SQLite |
| `get_notes_for_url(page_url)` | URL | `list[dict]` | SELECT notes for URL |

---

## Every API Route

### `GET /`

- **Input:** none  
- **Output:** `{ "message": "Welcome to NotesNexus API" }`  
- **Steps:** Return static JSON.

---

### `POST /process`

- **Input JSON:**
  ```json
  {
    "imageData": "<base64 PNG without data-URL prefix>",
    "page_url": "https://www.youtube.com/watch?v=..."
  }
  ```
- **Output JSON:**
  ```json
  {
    "full_text": "line1 . line2",
    "lines": [{ "text": "...", "bounding_box": { "x", "y", "width", "height" } }],
    "entities": [{ "entity": "Einstein", "label": "PERSON" }],
    "summary": "structured notes from Gemini"
  }
  ```
- **Steps:**
  1. Parse JSON body (`flask.request`)
  2. `paddle_ocr(imageData)` — PaddleOCR + Pillow + numpy
  3. Join paragraphs into `full_text`
  4. `ner_spacy(full_text)` — spaCy
  5. `summarize_gemini(full_text)` — google-generativeai
  6. Return JSON; on response close, `save_note()` if `page_url` provided — sqlite3

---

### `POST /summarize`

- **Input JSON:**
  ```json
  { "text": "accumulated lecture text", "page_url": "https://..." }
  ```
- **Output JSON:**
  ```json
  { "summary": "...", "entities": [...] }
  ```
- **Steps:**
  1. Validate `text`
  2. `ner_spacy(text)` — spaCy
  3. `summarize_gemini(text)` — Gemini with lecture-assistant prompt
  4. `save_note()` if `page_url` set — SQLite
  5. Return JSON

---

### `POST /index_notes`

- **Input JSON:**
  ```json
  { "text": "all captured text", "page_url": "https://..." }
  ```
- **Output JSON:**
  ```json
  { "chunks_indexed": 12 }
  ```
- **Steps:**
  1. `chunk_text()` — 200 words, 50 overlap
  2. `SentenceTransformer.encode()` — all-MiniLM-L6-v2
  3. ChromaDB create/replace collection named `md5(page_url)`
  4. `collection.add(documents, embeddings, ids)`

---

### `POST /ask`

- **Input JSON:**
  ```json
  { "question": "What is photosynthesis?", "page_url": "https://..." }
  ```
- **Output JSON:**
  ```json
  { "answer": "..." }
  ```
- **Steps:**
  1. Load ChromaDB collection for `md5(page_url)`
  2. Embed question with sentence-transformers
  3. `collection.query(n_results=3)`
  4. Build Gemini prompt with top 3 excerpts
  5. Return `answer` text

---

### `GET /notes?page_url=...`

- **Input:** query param `page_url`  
- **Output:** `{ "notes": [ { id, page_url, raw_text, summary, entities, created_at } ] }`  
- **Steps:** `get_notes_for_url()` from SQLite

---

## RAG Pipeline Detail

**What RAG is:** Retrieval-Augmented Generation — retrieve relevant snippets first, then ask the LLM to answer using only those snippets.

**Why not send full text to Gemini:** Long lectures exceed context limits, add latency/cost, and dilute focus. Chunking + retrieval sends only the 3 most relevant passages.

**Chunking:** 200 words per chunk, 50-word overlap so concepts split across chunk boundaries still appear in at least one chunk.

**all-MiniLM-L6-v2:** Outputs **384-dimensional** dense vectors per sentence/chunk.

**ChromaDB:** Stores embeddings locally; cosine similarity search returns top-3 chunks for a question embedding.

**Gemini prompt (word for word):**

```
Answer this question using only these excerpts from a lecture video. If answer is not present say 'This was not covered in the captured content.'

Excerpts:
{chunk_1}
{chunk_2}
{chunk_3}

Question: {question}
```

---

## Chrome Extension Architecture

### manifest.json permissions

| Permission | Why |
|------------|-----|
| `https://*/*`, `http://*/*` | Inject on video sites |
| `activeTab` | Access current tab when user clicks extension |
| `tabs` | Read tab URL for RAG/SQLite keys |
| `storage` | Persist popup HTML and accumulated OCR text |

### Messaging flow

**Popup → Background (start capture):**

```javascript
chrome.runtime.sendMessage({ myPopupIsOpen: true });
```

**Background → inject.js:**

```javascript
chrome.tabs.executeScript(null, { file: "./inject.js" });
```

**inject.js → Popup (OCR results):**

```javascript
chrome.runtime.sendMessage(response); // full /process JSON
```

**Popup listener:**

```javascript
chrome.runtime.onMessage.addListener((msg) => {
  // msg.lines, msg.entities, msg.summary, msg.full_text
});
```

---

## Complete Data Flow

1. User opens YouTube video — page loads `<video>`.
2. User clicks **Start NotesNexus** — `popup.js` sends `{ myPopupIsOpen: true }`.
3. `background.js` injects `inject.js` into the tab.
4. `inject.js` `main()` starts 3s `setInterval`.
5. `ImageCapture.grabFrame()` captures current frame → hidden canvas → `toDataURL()`.
6. `getAPI()` POSTs base64 to Flask `/process`.
7. Flask runs PaddleOCR → lines + boxes; spaCy → entities; Gemini → summary.
8. JSON returned to inject; scales boxes; `Canvas.showRects()` draws transparent divs.
9. If text changed, `chrome.runtime.sendMessage(response)` to popup.
10. Popup appends lines to notes list, entities to topics, summary; stores `accumulated_text`.
11. User clicks **Take Notes** — popup POSTs `/index_notes` (ChromaDB) and `/summarize` (SQLite).
12. User types question, clicks **Ask** — popup POSTs `/ask` with tab URL.
13. Flask retrieves top 3 chunks, Gemini answers — `{ answer }` shown in `#ask-answer`.
14. User revisits same URL — popup `GET /notes` loads prior summary/entities from SQLite.

---

## All Libraries

| Library | Role | File | Call |
|---------|------|------|------|
| PaddleOCR | OCR | `ocr.py` | `PaddleOCR().ocr(image_np, cls=True)` |
| Pillow | Decode images | `ocr.py` | `Image.open(io.BytesIO(...))` |
| numpy | Array for OCR | `ocr.py` | `np.array(image)` |
| google-generativeai | Summaries + RAG answers | `summarization.py`, `rag.py` | `genai.GenerativeModel(...).generate_content(...)` |
| spaCy | NER | `ner.py` | `nlp(text)` |
| sentence-transformers | Embeddings | `rag.py` | `SentenceTransformer.encode(...)` |
| chromadb | Vector store | `rag.py` | `PersistentClient`, `collection.add/query` |
| sqlite3 | Notes persistence | `database.py` | `INSERT` / `SELECT` |
| flask / flask-cors | HTTP API | `app.py` | routes, `CORS(app)` |
| python-dotenv | Env vars | `app.py`, modules | `load_dotenv()` |

---

## Environment Variables

| Variable | Used in | How to get | If missing |
|----------|---------|------------|------------|
| `GEMINI_API_KEY` | `summarization.py`, `rag.py` | [Google AI Studio](https://aistudio.google.com) | Summaries and `/ask` fail with clear error |

Copy `backend/.env.example` to `backend/.env` and set your key.

---

## Setup

```bash
cd E:\Project\NotesNexus
python -m venv env
env\Scripts\activate          # Windows
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# backend/.env
GEMINI_API_KEY=your_key_here

cd backend
python app.py
```

Load unpacked extension: Chrome → Extensions → Developer mode → Load unpacked → select `client/`.

---

## client2.0 (not primary)

Experimental fork with name “Injecta”, incomplete popup wiring, and `inject-2.0.js` without deduplication logic. Use **`client/`** for development.
