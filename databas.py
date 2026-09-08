import sqlite3
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "radar.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def create_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            score INTEGER NOT NULL,
            price REAL NOT NULL,
            reasons TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_signal(symbol, score, price, reasons):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO signals
        (symbol, score, price, reasons, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            symbol,
            int(score),
            float(price),
            reasons,
            datetime.now(timezone.utc).isoformat()
        )
    )

    conn.commit()
    conn.close()


def get_signals(limit=100):
    conn = get_connection()
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM signals
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def clear_old_signals():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM signals
        WHERE id NOT IN (
            SELECT id
            FROM signals
            ORDER BY id DESC
            LIMIT 1000
        )
    """)

    conn.commit()
    conn.close()
