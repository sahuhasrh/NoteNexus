# Must set before any Paddle import (fixes Windows oneDNN / PIR crashes)
import os
import threading

os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"

import base64
import io

import numpy as np
from PIL import Image

_ocr = None
_ocr_lock = threading.Lock()


def _get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR

        # Angle classifier causes crashes under concurrent calls on Windows.
        _ocr = PaddleOCR(
            use_angle_cls=False,
            lang="en",
            show_log=False,
            use_gpu=False,
        )
    return _ocr


def _parse_ocr_result(result):
    """Normalize PaddleOCR 2.x result into lines with GCP-compatible boxes."""
    lines = []
    if not result:
        return lines

    items = result[0] if isinstance(result, list) and result else result
    if not items:
        return lines

    for item in items:
        if not item or len(item) < 2:
            continue
        box = item[0]
        text_part = item[1]
        if isinstance(text_part, (list, tuple)):
            text = text_part[0]
        else:
            text = str(text_part)

        if not text or not box:
            continue

        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x = int(min(xs))
        y = int(min(ys))
        width = int(max(xs) - min(xs))
        height = int(max(ys) - min(ys))

        lines.append(
            {
                "text": text,
                "bounding_box": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
            }
        )

    return lines


def paddle_ocr(image_content):
    """Run PaddleOCR on a base64 image and return GCP-compatible format."""
    if not image_content:
        return [], []

    content = base64.b64decode(image_content)
    image = Image.open(io.BytesIO(content)).convert("RGB")
    image_np = np.array(image)

    with _ocr_lock:
        ocr = _get_ocr()
        result = ocr.ocr(image_np, cls=False)

    lines = _parse_ocr_result(result)
    paragraphs = []
    if lines:
        paragraphs.append(" ".join(line["text"] for line in lines))

    return paragraphs, lines


gcp_ocr = paddle_ocr
