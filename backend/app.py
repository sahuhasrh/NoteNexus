import json
import os
import time

import shortuuid
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request
from flask_cors import CORS, cross_origin

from database import get_notes_for_url, init_db, save_note
from ner import ner_spacy
from ocr import paddle_ocr
from rag import ask_question, index_lecture_text
from summarization import summarize_with_fallback

load_dotenv()

sample = None
sample_path = os.path.join(os.path.dirname(__file__), "images", "processpayload2.json")
if os.path.exists(sample_path):
    with open(sample_path, encoding="utf-8") as f:
        sample = json.load(f)

app = Flask(__name__)
CORS(app)

init_db()


@app.route("/", methods=["GET"])
def root():
    return {"message": "Welcome to NotesNexus API"}


@app.route("/test", methods=["GET"])
def test():
    return {"status": "ok"}


@app.route("/new_session", methods=["GET"])
@cross_origin()
def new_session():
    return {"uuid": shortuuid.uuid()}


@app.route("/process", methods=["POST"])
@cross_origin()
def process():
    """
    Payload:
        imageData: base64 image string
        page_url: optional current page URL
    """
    data = request.get_json()

    if data is None and sample:
        imageData = sample["imageData"]
        page_url = ""
    else:
        imageData = data.get("imageData")
        page_url = data.get("page_url", "")

    try:
        paragraphs, lines = paddle_ocr(imageData)
    except Exception as e:
        app.logger.exception("OCR failed")
        return jsonify(
            {
                "error": str(e),
                "full_text": "",
                "lines": [],
                "entities": [],
                "summary": "",
            }
        ), 500

    full_text = " . ".join(paragraphs)
    entities = ner_spacy(full_text) if full_text.strip() else []

    # Summaries are slow (Gemini). Use "Take Notes" -> /summarize instead.
    response = make_response(
        jsonify(
            {
                "full_text": full_text,
                "lines": lines,
                "entities": entities,
                "summary": "",
            }
        )
    )

    return response


@app.route("/summarize", methods=["POST"])
@cross_origin()
def summarize():
    """
    Payload:
        text: string to summarize
        page_url: optional page URL for SQLite persistence
    """
    data = request.get_json() or {}
    text = data.get("text", "")
    page_url = data.get("page_url", "")

    if not text.strip():
        return jsonify({"error": "text is required"}), 400

    entities = ner_spacy(text)
    try:
        summary, used_fallback = summarize_with_fallback(text)
    except Exception as e:
        app.logger.exception("Summarization failed")
        return jsonify({"error": str(e), "summary": "", "entities": entities}), 500

    if page_url:
        save_note(page_url, text, summary, entities)

    return jsonify(
        {
            "summary": summary,
            "entities": entities,
            "used_fallback": used_fallback,
        }
    )


@app.route("/index_notes", methods=["POST"])
@cross_origin()
def index_notes():
    """
    Index accumulated lecture text for RAG Q&A.
    Payload:
        text: all extracted text collected so far
        page_url: current page URL
    """
    data = request.get_json() or {}
    text = data.get("text", "")
    page_url = data.get("page_url", "")

    if not page_url:
        return jsonify({"error": "page_url is required"}), 400
    if not text.strip():
        return jsonify({"error": "text is required"}), 400

    result = index_lecture_text(page_url, text)
    return jsonify(result)


@app.route("/ask", methods=["POST"])
@cross_origin()
def ask():
    """
    RAG Q&A over indexed lecture content.
    Payload:
        question: string
        page_url: string
    """
    data = request.get_json() or {}
    question = data.get("question", "")
    page_url = data.get("page_url", "")
    text = data.get("text", "")

    if not question.strip():
        return jsonify({"error": "question is required"}), 400
    if not page_url:
        return jsonify({"error": "page_url is required"}), 400

    try:
        if text.strip():
            index_lecture_text(page_url, text)
        answer = ask_question(page_url, question)
        return jsonify({"answer": answer})
    except Exception as e:
        app.logger.exception("Ask failed")
        return jsonify({"error": str(e), "answer": ""}), 500


@app.route("/notes", methods=["GET"])
@cross_origin()
def notes():
    """Load previously saved notes for a page URL."""
    page_url = request.args.get("page_url", "")
    if not page_url:
        return jsonify({"error": "page_url is required"}), 400

    saved = get_notes_for_url(page_url)
    return jsonify({"notes": saved})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
