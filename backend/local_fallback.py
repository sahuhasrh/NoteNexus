"""Local fallbacks when Gemini API quota is unavailable."""


def summarize_local(text, max_sentences=10):
    """Build simple structured notes without an external API."""
    if not text or not text.strip():
        return "No text captured yet."

    cleaned = text.replace(" . ", ". ").replace("  ", " ")
    parts = [p.strip() for p in cleaned.split(".") if len(p.strip()) > 15]
    if not parts:
        parts = [cleaned[:800]]

    overview = ". ".join(parts[:2])
    if overview and not overview.endswith("."):
        overview += "."

    bullets = parts[:max_sentences]
    bullet_block = "\n".join(f"- {b}" for b in bullets)

    return (
        "Overview:\n"
        f"{overview}\n\n"
        "Key points:\n"
        f"{bullet_block}\n\n"
        "---\n"
        "Note: Generated locally (Gemini quota unavailable). "
        "Create a new API key at https://aistudio.google.com/apikey "
        "or wait for your free-tier limit to reset."
    )


def ask_from_excerpts(question, excerpts):
    """Return relevant captured excerpts without calling Gemini."""
    if not excerpts:
        return "This was not covered in the captured content."

    joined = "\n\n---\n\n".join(excerpts)
    return (
        f"Question: {question}\n\n"
        "Relevant excerpts from the video (local search, no AI synthesis):\n\n"
        f"{joined}\n\n"
        "---\n"
        "Gemini quota is exhausted. Showing matching text only. "
        "Add a new API key or enable billing for full AI answers."
    )
