from __future__ import annotations

import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("LATTICE_DB_PATH", ROOT_DIR / "data" / "lattice_index.sqlite3"))
DATA_DIR = DB_PATH.parent


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              isbn13 TEXT UNIQUE,
              isbn10 TEXT,
              title TEXT NOT NULL,
              title_kana TEXT,
              subtitle TEXT,
              series_name TEXT,
              series_kana TEXT,
              volume_number TEXT,
              author TEXT,
              illustrator TEXT,
              translator TEXT,
              publisher TEXT,
              label TEXT,
              category TEXT,
              published_date TEXT,
              page_count INTEGER,
              description TEXT,
              cover_url TEXT,
              metadata_source TEXT NOT NULL DEFAULT 'manual',
              metadata_raw_json TEXT,
              normalized_search_text TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS locations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE NOT NULL,
              sort_order INTEGER NOT NULL DEFAULT 0,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS copies (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              book_id INTEGER NOT NULL,
              ownership_status TEXT NOT NULL DEFAULT 'owned',
              location_id INTEGER,
              location_detail TEXT,
              condition TEXT,
              acquired_date TEXT,
              last_seen_at TEXT,
              memo TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(book_id) REFERENCES books(id),
              FOREIGN KEY(location_id) REFERENCES locations(id)
            );

            CREATE TABLE IF NOT EXISTS tags (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS book_tags (
              book_id INTEGER NOT NULL,
              tag_id INTEGER NOT NULL,
              PRIMARY KEY (book_id, tag_id),
              FOREIGN KEY(book_id) REFERENCES books(id),
              FOREIGN KEY(tag_id) REFERENCES tags(id)
            );
            """
        )
        try:
            db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS book_search
                USING fts5(
                  title,
                  title_kana,
                  series_name,
                  series_kana,
                  author,
                  illustrator,
                  publisher,
                  label,
                  description,
                  normalized_search_text,
                  tokenize='trigram'
                )
                """
            )
        except sqlite3.OperationalError:
            db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS book_search
                USING fts5(
                  title,
                  title_kana,
                  series_name,
                  series_kana,
                  author,
                  illustrator,
                  publisher,
                  label,
                  description,
                  normalized_search_text
                )
                """
            )

        created_at = now_iso()
        for order, name in enumerate(("家", "実家", "不明")):
            db.execute(
                """
                INSERT OR IGNORE INTO locations(name, sort_order, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (name, order, created_at, created_at),
            )


def normalize_search_text(*parts: object) -> str:
    text = " ".join(str(part) for part in parts if part)
    return (
        text.lower()
        .replace("　", " ")
        .replace("-", "")
        .replace("ー", "")
        .replace("・", "")
        .strip()
    )


def sync_book_search(db: sqlite3.Connection, book_id: int) -> None:
    book = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not book:
        return
    db.execute("DELETE FROM book_search WHERE rowid = ?", (book_id,))
    db.execute(
        """
        INSERT INTO book_search(
          rowid, title, title_kana, series_name, series_kana, author,
          illustrator, publisher, label, description, normalized_search_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            book_id,
            book["title"],
            book["title_kana"],
            book["series_name"],
            book["series_kana"],
            book["author"],
            book["illustrator"],
            book["publisher"],
            book["label"],
            book["description"],
            book["normalized_search_text"],
        ),
    )
