from gemini_client import QuotaExceededError, generate_text
from local_fallback import summarize_local


def summarize_gemini(text):
    """Generate structured lecture notes using Gemini."""
    prompt = (
        "You are a lecture assistant. Given this text extracted "
        "from a lecture video, produce structured notes with:\n"
        "- One paragraph overview\n"
        "- Key points as bullet points\n"
        "- Important terms and their definitions\n"
        "- Any numbers, stats, or formulas mentioned\n\n"
        f"Text: {text}"
    )
    return generate_text(prompt)


def summarize_with_fallback(text):
    """
    Try Gemini; on quota/error use local summary.
    Returns (summary_text, used_fallback: bool).
    """
    try:
        return summarize_gemini(text), False
    except QuotaExceededError:
        return summarize_local(text), True
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return summarize_local(text), True
        raise


def summarize_bart(original_text):
    summary, _ = summarize_with_fallback(original_text)
    return summary
