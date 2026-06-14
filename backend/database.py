import os
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher

DB_PATH = os.path.join(os.path.dirname(__file__), "notes.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS slides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            text TEXT NOT NULL,
            slide_number INTEGER,
            timestamp TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            summary TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def _normalize_text(text):
    return " ".join((text or "").lower().split())


def _word_set(text):
    words = []
    for word in _normalize_text(text).split():
        word = word.strip(".,:;!?()[]{}\"'")
        if len(word) >= 3:
            words.append(word)
    return set(words)


def _is_same_slide(previous_text, next_text):
    previous = _normalize_text(previous_text)
    current = _normalize_text(next_text)
    if not previous or not current:
        return False
    if previous == current:
        return True
    previous_words = _word_set(previous)
    current_words = _word_set(current)
    smaller = min(len(previous_words), len(current_words))
    if smaller >= 6:
        overlap = len(previous_words & current_words) / smaller
        if overlap >= 0.72:
            return True
    return SequenceMatcher(None, previous, current).ratio() >= 0.9


def _better_slide_text(previous_text, next_text):
    if len(_normalize_text(next_text)) > len(_normalize_text(previous_text)):
        return next_text
    return previous_text


def save_slide(url, text, timestamp):
    conn = get_connection()
    last = conn.execute(
        """
        SELECT id, text, slide_number
        FROM slides
        WHERE url=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (url,),
    ).fetchone()
    if last and _is_same_slide(last[1], text):
        merged_text = _better_slide_text(last[1], text)
        if merged_text != last[1]:
            conn.execute(
                "UPDATE slides SET text=? WHERE id=?",
                (merged_text, last[0]),
            )
            conn.commit()
        conn.close()
        return False, last[2]

    slide_number = (last[2] if last else 0) + 1
    conn.execute(
        "INSERT INTO slides (url, text, slide_number, timestamp) VALUES (?, ?, ?, ?)",
        (url, text, slide_number, timestamp),
    )
    conn.commit()
    conn.close()
    return True, slide_number


def get_all_text(url):
    conn = get_connection()
    rows = conn.execute(
        "SELECT text, slide_number, timestamp FROM slides WHERE url=? ORDER BY slide_number",
        (url,),
    ).fetchall()
    conn.close()
    return rows


def get_full_text(url):
    rows = _dedupe_rows(get_all_text(url))
    return " ".join(row[0] for row in rows)


def _dedupe_rows(rows):
    unique_rows = []
    last_text = None
    for row in rows:
        text = row[0]
        if last_text is not None and _is_same_slide(last_text, text):
            continue
        unique_rows.append(row)
        last_text = text
    return unique_rows


def get_slide_timeline(url):
    rows = _dedupe_rows(get_all_text(url))
    timeline = []
    for index, row in enumerate(rows, start=1):
        text, _slide_number, timestamp = row
        preview = text[:60] + ("..." if len(text) > 60 else "")
        timeline.append(
            {"text": preview, "slide_number": index, "timestamp": timestamp}
        )
    return timeline


def save_summary(url, summary):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO sessions (url, summary, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            summary=excluded.summary,
            updated_at=excluded.updated_at
        """,
        (url, summary, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_summary(url):
    conn = get_connection()
    row = conn.execute("SELECT summary FROM sessions WHERE url=?", (url,)).fetchone()
    conn.close()
    return row[0] if row else None


init_db()
