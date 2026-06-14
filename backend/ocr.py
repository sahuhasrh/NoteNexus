import base64

import cv2
import numpy as np
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

def _decode_base64_image(base64_img):
    if not base64_img:
        raise ValueError("imageData is required")
    if "," in base64_img:
        base64_img = base64_img.split(",", 1)[1]
    img_bytes = base64.b64decode(base64_img)
    img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image data")
    return img


def preprocess(base64_img):
    img = _decode_base64_image(base64_img)
    original_height, original_width = img.shape[:2]
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary, original_width, original_height


def run_ocr(base64_img):
    processed, image_width, image_height = preprocess(base64_img)
    data = pytesseract.image_to_data(
        processed,
        output_type=pytesseract.Output.DICT,
        config="--psm 6",
    )
    lines = []
    for i, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if text and conf > 60:
            x = data["left"][i] // 2
            y = data["top"][i] // 2
            w = data["width"][i] // 2
            h = data["height"][i] // 2
            lines.append(
                {
                    "text": text,
                    "bounding_box": {"x": x, "y": y, "width": w, "height": h},
                    "confidence": conf,
                }
            )
    full_text = " ".join(line["text"] for line in lines)
    return {
        "lines": lines,
        "full_text": full_text,
        "image_width": image_width,
        "image_height": image_height,
    }
