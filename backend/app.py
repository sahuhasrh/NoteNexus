from flask import Flask, jsonify, request
from flask_cors import CORS

from database import (
    get_full_text,
    get_slide_timeline,
    get_summary,
    save_slide,
    save_summary,
)
from gemini import answer_question, summarize
from ner import extract_entities
from ocr import run_ocr

app = Flask(__name__)
CORS(app)


@app.route("/", methods=["GET"])
def root():
    return jsonify({"message": "Welcome to NotesNexus API"})


@app.route("/test", methods=["GET"])
def test():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json() or {}
    image_data = data.get("imageData")
    page_url = data.get("page_url", "unknown")
    video_timestamp = data.get("timestamp", "0:00")

    try:
        ocr_result = run_ocr(image_data)
    except Exception as exc:
        app.logger.exception("OCR failed")
        return jsonify({"error": str(exc), "lines": [], "entities": [], "full_text": ""}), 500

    full_text = ocr_result["full_text"]
    lines = ocr_result["lines"]

    if not full_text.strip():
        return jsonify(
            {
                "lines": [],
                "entities": [],
                "full_text": "",
                "slide_number": 0,
                "image_width": ocr_result["image_width"],
                "image_height": ocr_result["image_height"],
            }
        )

    entities = extract_entities(full_text)
    saved, slide_num = save_slide(page_url, full_text, video_timestamp)

    return jsonify(
        {
            "saved": saved,
            "lines": lines,
            "entities": entities,
            "full_text": full_text,
            "slide_number": slide_num,
            "image_width": ocr_result["image_width"],
            "image_height": ocr_result["image_height"],
        }
    )


@app.route("/summarize", methods=["POST"])
def summarize_route():
    data = request.get_json() or {}
    page_url = data.get("page_url", "unknown")
    full_text = get_full_text(page_url)
    result = summarize(full_text)
    if isinstance(result, dict) and "summary" in result:
        save_summary(page_url, result.get("summary", ""))
    return jsonify(result)


@app.route("/ask", methods=["POST"])
def ask_route():
    data = request.get_json() or {}
    question = data.get("question", "")
    page_url = data.get("page_url", "unknown")
    full_text = get_full_text(page_url)
    answer = answer_question(question, full_text)
    return jsonify({"answer": answer})


@app.route("/timeline", methods=["GET"])
def timeline():
    page_url = request.args.get("page_url", "unknown")
    slides = get_slide_timeline(page_url)
    return jsonify({"timeline": slides})


@app.route("/notes", methods=["GET"])
def notes():
    page_url = request.args.get("page_url", "unknown")
    summary = get_summary(page_url)
    full_text = get_full_text(page_url)
    return jsonify({"summary": summary, "full_text": full_text})


if __name__ == "__main__":
    app.run(port=8000, debug=True)
