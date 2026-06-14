import json
import os
import time

from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def summarize(text):
    if not text or len(text.strip()) < 50:
        return {"error": "Not enough content captured yet."}

    prompt = f"""
You are a lecture note assistant. Given raw OCR text from lecture slides produce structured notes.

Return ONLY a valid JSON object with exactly these fields:

{{
  "summary": "2-3 sentence overview",
  "key_concepts": ["concept1", "concept2"],
  "entities": [{{"entity":"name","label":"PERSON/ORG/CONCEPT"}}],
  "bullet_notes": ["note1","note2"]
}}

OCR TEXT:
{text}
"""

    try:
        response = None

        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                break
            except Exception as e:
                print(f"Gemini attempt {attempt + 1} failed:", e)

                if attempt == 2:
                    raise

                time.sleep(2)

        raw = response.text.strip()

        if raw.startswith("```json"):
            raw = raw.replace("```json", "", 1)

        if raw.endswith("```"):
            raw = raw[:-3]

        raw = raw.strip()

        return json.loads(raw)

    except Exception as e:
        print("Summarization Error:", e)

        return {
            "summary": "Gemini service is temporarily unavailable.",
            "key_concepts": [],
            "entities": [],
            "bullet_notes": [],
        }


def answer_question(question, context_text):
    if not context_text or len(context_text.strip()) < 50:
        return "No lecture content captured yet."

    prompt = f"""
You are a lecture assistant. Answer the question using only the lecture content provided.

If answer is not in content say:
"This was not covered in the captured lecture content."

LECTURE CONTENT:
{context_text}

QUESTION:
{question}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        return response.text

    except Exception as e:
        print("Question Answering Error:", e)
        return "Gemini service is temporarily unavailable. Please try again."