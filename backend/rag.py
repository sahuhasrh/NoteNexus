import hashlib
import os

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from gemini_client import QuotaExceededError, generate_text
from local_fallback import ask_from_excerpts

load_dotenv()

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
CHUNK_SIZE = 200
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_embedder = None
_chroma_client = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def collection_name_for_url(page_url):
    return hashlib.md5(page_url.encode("utf-8")).hexdigest()


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    words = text.split()
    if not words:
        return []

    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
    return chunks


def index_lecture_text(page_url, text):
    """Chunk, embed, and store lecture text in ChromaDB."""
    chunks = chunk_text(text)
    if not chunks:
        return {"chunks_indexed": 0}

    embedder = _get_embedder()
    embeddings = embedder.encode(chunks).tolist()

    client = _get_chroma_client()
    name = collection_name_for_url(page_url)

    try:
        client.delete_collection(name)
    except Exception:
        pass

    collection = client.create_collection(name=name)
    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=[str(i) for i in range(len(chunks))],
    )
    return {"chunks_indexed": len(chunks)}


def _retrieve_excerpts(page_url, question):
    client = _get_chroma_client()
    name = collection_name_for_url(page_url)

    try:
        collection = client.get_collection(name=name)
    except Exception:
        return None

    embedder = _get_embedder()
    query_embedding = embedder.encode([question]).tolist()
    n_results = min(3, collection.count())
    if n_results == 0:
        return []

    results = collection.query(query_embeddings=query_embedding, n_results=n_results)
    return results.get("documents", [[]])[0] or []


def ask_question(page_url, question):
    """Retrieve top chunks; answer with Gemini or local excerpt fallback."""
    excerpts = _retrieve_excerpts(page_url, question)

    if excerpts is None:
        return (
            "No indexed notes for this video yet. "
            "Click **Take Notes** in the popup (after capturing text), then try Ask again."
        )
    if not excerpts:
        return (
            "No indexed notes for this video yet. "
            "Click **Take Notes** in the popup, then try Ask again."
        )

    chunk_1 = excerpts[0] if len(excerpts) > 0 else ""
    chunk_2 = excerpts[1] if len(excerpts) > 1 else ""
    chunk_3 = excerpts[2] if len(excerpts) > 2 else ""

    prompt = (
        "Answer this question using only these excerpts "
        "from a lecture video. If answer is not present "
        "say 'This was not covered in the captured content.'\n\n"
        f"Excerpts:\n{chunk_1}\n{chunk_2}\n{chunk_3}\n\n"
        f"Question: {question}"
    )

    try:
        return generate_text(prompt)
    except QuotaExceededError:
        return ask_from_excerpts(question, excerpts)
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return ask_from_excerpts(question, excerpts)
        raise
