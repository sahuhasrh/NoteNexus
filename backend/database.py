import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "notes.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_url TEXT,
            raw_text TEXT,
            summary TEXT,
            entities TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()


def save_note(page_url, raw_text, summary, entities):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO notes (page_url, raw_text, summary, entities)
        VALUES (?, ?, ?, ?);
        """,
        (page_url, raw_text, summary, json.dumps(entities)),
    )
    conn.commit()
    conn.close()


def get_notes_for_url(page_url):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, page_url, raw_text, summary, entities, created_at
        FROM notes
        WHERE page_url = ?
        ORDER BY created_at DESC;
        """,
        (page_url,),
    ).fetchall()
    conn.close()

    notes = []
    for row in rows:
        notes.append(
            {
                "id": row["id"],
                "page_url": row["page_url"],
                "raw_text": row["raw_text"],
                "summary": row["summary"],
                "entities": json.loads(row["entities"]) if row["entities"] else [],
                "created_at": row["created_at"],
            }
        )
    return notes
