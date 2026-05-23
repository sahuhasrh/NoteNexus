import os
import re

from dotenv import load_dotenv

load_dotenv()


class QuotaExceededError(Exception):
    """Raised when all Gemini models hit rate/quota limits."""


_client = None
_use_legacy = False

_DEFAULT_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]


def _build_model_candidates():
    seen = set()
    candidates = []
    env_model = os.environ.get("GEMINI_MODEL", "").strip()

    for name in [env_model] + _DEFAULT_MODELS:
        if not name or name in seen:
            continue
        if re.search(r"gemini-1\.5|gemini-1\.0", name, re.I):
            continue
        seen.add(name)
        candidates.append(name)
    return candidates


MODEL_CANDIDATES = _build_model_candidates()


def _get_api_key():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment")
    return api_key


def _is_quota_error(exc):
    msg = str(exc).upper()
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg


def _generate_new_sdk(prompt):
    from google import genai
    from google.genai import errors as genai_errors

    global _client
    if _client is None:
        _client = genai.Client(api_key=_get_api_key())

    quota_errors = []
    last_error = None

    for model in MODEL_CANDIDATES:
        try:
            response = _client.models.generate_content(
                model=model,
                contents=prompt,
            )
            if response.text:
                return response.text
            return str(response)
        except genai_errors.ClientError as e:
            last_error = e
            code = getattr(e, "status_code", None)
            if code == 404:
                continue
            if code == 429 or _is_quota_error(e):
                quota_errors.append(e)
                continue
            raise

    if quota_errors:
        raise QuotaExceededError(
            "Gemini free-tier quota exceeded for all models. "
            "Use a new API key or wait for the daily limit to reset."
        ) from quota_errors[-1]
    if last_error:
        raise last_error
    raise RuntimeError(f"No working Gemini model. Tried: {MODEL_CANDIDATES}")


def _generate_legacy_sdk(prompt):
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    quota_errors = []
    last_error = None

    for model_name in MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            last_error = e
            if "404" in str(e) or "not found" in str(e).lower():
                continue
            if _is_quota_error(e):
                quota_errors.append(e)
                continue
            raise

    if quota_errors:
        raise QuotaExceededError("Gemini quota exceeded") from quota_errors[-1]
    if last_error:
        raise last_error
    raise RuntimeError("No working Gemini model available")


def generate_text(prompt):
    global _use_legacy
    if not MODEL_CANDIDATES:
        raise RuntimeError("No Gemini models configured")

    if _use_legacy:
        return _generate_legacy_sdk(prompt)

    try:
        return _generate_new_sdk(prompt)
    except ImportError:
        _use_legacy = True
        return _generate_legacy_sdk(prompt)
