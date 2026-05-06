from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .database import DB_PATH, connect, init_db, normalize_search_text, now_iso, sync_book_search
from .isbn import ISBNError, looks_like_isbn, normalize_isbn
from .metadata import lookup_book
from .schemas import BookCreate, CopyUpdate, LocationCreate, LocationUpdate, LookupRequest


app = FastAPI(title="Lattice Index API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


def row_to_dict(row: Any) -> dict:
    return dict(row) if row is not None else {}


COPY_SELECT = """
SELECT
  c.id AS copy_id,
  c.book_id,
  b.title,
  b.title_kana,
  b.subtitle,
  b.series_name,
  b.series_kana,
  b.volume_number,
  b.author,
  b.illustrator,
  b.translator,
  b.publisher,
  b.label,
  b.category,
  b.published_date,
  b.page_count,
  b.description,
  b.cover_url,
  b.isbn13,
  b.isbn10,
  b.metadata_source,
  c.location_id,
  l.name AS location_name,
  c.location_detail,
  c.ownership_status,
  c.condition,
  c.acquired_date,
  c.last_seen_at,
  c.memo,
  c.created_at,
  c.updated_at
FROM copies c
JOIN books b ON b.id = c.book_id
LEFT JOIN locations l ON l.id = c.location_id
"""


def normalize_payload_isbn(payload: BookCreate) -> tuple[str | None, str | None]:
    if not payload.isbn13:
        return None, payload.isbn10
    try:
        return normalize_isbn(payload.isbn13)
    except ISBNError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/books/lookup")
async def books_lookup(request: LookupRequest) -> dict:
    try:
        return await lookup_book(request.isbn)
    except ISBNError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/books")
def create_book(payload: BookCreate) -> dict:
    isbn13, isbn10 = normalize_payload_isbn(payload)
    timestamp = now_iso()
    with connect() as db:
        existing = None
        if isbn13:
            existing = db.execute("SELECT * FROM books WHERE isbn13 = ?", (isbn13,)).fetchone()
        if existing and payload.duplicate_action != "add_copy":
            copies = db.execute(
                """
                SELECT c.id AS copy_id, l.name AS location_name, c.location_detail
                FROM copies c
                LEFT JOIN locations l ON l.id = c.location_id
                WHERE c.book_id = ?
                ORDER BY c.created_at DESC
                """,
                (existing["id"],),
            ).fetchall()
            return {
                "status": "duplicate",
                "message": "この本はすでに登録されています。",
                "existing_book_id": existing["id"],
                "existing_copies": [row_to_dict(row) for row in copies],
            }

        if existing:
            book_id = existing["id"]
        else:
            normalized = normalize_search_text(
                payload.title,
                payload.title_kana,
                payload.series_name,
                payload.series_kana,
                payload.volume_number,
                payload.author,
                payload.publisher,
                payload.label,
                isbn13,
            )
            cursor = db.execute(
                """
                INSERT INTO books(
                  isbn13, isbn10, title, title_kana, subtitle, series_name, series_kana,
                  volume_number, author, illustrator, translator, publisher, label, category,
                  published_date, page_count, description, cover_url, metadata_source,
                  metadata_raw_json, normalized_search_text, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    isbn13,
                    isbn10 or payload.isbn10,
                    payload.title,
                    payload.title_kana,
                    payload.subtitle,
                    payload.series_name,
                    payload.series_kana,
                    payload.volume_number,
                    payload.author,
                    payload.illustrator,
                    payload.translator,
                    payload.publisher,
                    payload.label,
                    payload.category,
                    payload.published_date,
                    payload.page_count,
                    payload.description,
                    payload.cover_url,
                    payload.metadata_source,
                    json.dumps(payload.metadata_raw_json, ensure_ascii=False) if payload.metadata_raw_json else None,
                    normalized,
                    timestamp,
                    timestamp,
                ),
            )
            book_id = cursor.lastrowid
            sync_book_search(db, book_id)

        copy = payload.copy_
        cursor = db.execute(
            """
            INSERT INTO copies(
              book_id, ownership_status, location_id, location_detail, condition,
              acquired_date, memo, created_at, updated_at
            )
            VALUES (?, 'owned', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book_id,
                copy.location_id,
                copy.location_detail,
                copy.condition,
                copy.acquired_date,
                copy.memo,
                timestamp,
                timestamp,
            ),
        )
        return {"status": "created", "book_id": book_id, "copy_id": cursor.lastrowid}


@app.get("/api/copies")
def list_copies(
    location: str | None = None,
    include_inactive: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    where = ["1 = 1"]
    params: list[Any] = []
    if not include_inactive:
        where.append("c.ownership_status = 'owned'")
    if location:
        where.append("l.name = ?")
        params.append(location)
    params.append(limit)
    with connect() as db:
        rows = db.execute(
            f"{COPY_SELECT} WHERE {' AND '.join(where)} ORDER BY c.created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/api/copies/{copy_id}")
def get_copy(copy_id: int) -> dict:
    with connect() as db:
        copy = db.execute(f"{COPY_SELECT} WHERE c.id = ?", (copy_id,)).fetchone()
        if not copy:
            raise HTTPException(status_code=404, detail="コピーが見つかりません。")
        related = db.execute(
            f"{COPY_SELECT} WHERE c.book_id = ? AND c.id != ? ORDER BY c.created_at DESC",
            (copy["book_id"], copy_id),
        ).fetchall()
        result = row_to_dict(copy)
        result["related_copies"] = [row_to_dict(row) for row in related]
        return result


@app.patch("/api/copies/{copy_id}")
def update_copy(copy_id: int, payload: CopyUpdate) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return get_copy(copy_id)
    updates["updated_at"] = now_iso()
    columns = ", ".join(f"{key} = ?" for key in updates)
    with connect() as db:
        cursor = db.execute(
            f"UPDATE copies SET {columns} WHERE id = ?",
            [*updates.values(), copy_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="コピーが見つかりません。")
    return get_copy(copy_id)


@app.get("/api/search")
def search(q: str | None = None, isbn: str | None = None, location: str | None = None, include_inactive: bool = False) -> list[dict]:
    terms: list[str] = []
    if q:
        terms = [term for term in q.replace("　", " ").split(" ") if term]
    where = ["1 = 1"]
    params: list[Any] = []
    if not include_inactive:
        where.append("c.ownership_status = 'owned'")
    if location:
        where.append("l.name = ?")
        params.append(location)
    if isbn or (q and looks_like_isbn(q)):
        try:
            isbn13, _ = normalize_isbn(isbn or q or "")
        except ISBNError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        where.append("b.isbn13 = ?")
        params.append(isbn13)
    else:
        for term in terms:
            like = f"%{term}%"
            where.append(
                """
                (
                  b.title LIKE ? OR b.title_kana LIKE ? OR b.series_name LIKE ? OR
                  b.series_kana LIKE ? OR b.author LIKE ? OR b.publisher LIKE ? OR
                  b.label LIKE ? OR b.isbn13 LIKE ? OR l.name LIKE ? OR
                  c.location_detail LIKE ? OR c.memo LIKE ? OR
                  b.normalized_search_text LIKE ?
                )
                """
            )
            normalized_like = f"%{normalize_search_text(term)}%"
            params.extend([like, like, like, like, like, like, like, like, like, like, like, normalized_like])
    with connect() as db:
        rows = db.execute(
            f"{COPY_SELECT} WHERE {' AND '.join(where)} ORDER BY c.created_at DESC LIMIT 200",
            params,
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/api/locations")
def list_locations(include_inactive: bool = False) -> list[dict]:
    where = "" if include_inactive else "WHERE is_active = 1"
    with connect() as db:
        rows = db.execute(f"SELECT * FROM locations {where} ORDER BY sort_order, id").fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/api/locations")
def create_location(payload: LocationCreate) -> dict:
    timestamp = now_iso()
    with connect() as db:
        try:
            cursor = db.execute(
                """
                INSERT INTO locations(name, sort_order, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (payload.name, payload.sort_order, timestamp, timestamp),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail="同じ名前の所在地がすでにあります。") from exc
        return row_to_dict(db.execute("SELECT * FROM locations WHERE id = ?", (cursor.lastrowid,)).fetchone())


@app.patch("/api/locations/{location_id}")
def update_location(location_id: int, payload: LocationUpdate) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if "is_active" in updates:
        updates["is_active"] = 1 if updates["is_active"] else 0
    updates["updated_at"] = now_iso()
    columns = ", ".join(f"{key} = ?" for key in updates)
    with connect() as db:
        cursor = db.execute(f"UPDATE locations SET {columns} WHERE id = ?", [*updates.values(), location_id])
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="所在地が見つかりません。")
        return row_to_dict(db.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone())


@app.get("/api/export/json")
def export_json() -> dict:
    with connect() as db:
        return {
            "exported_at": now_iso(),
            "books": [row_to_dict(row) for row in db.execute("SELECT * FROM books ORDER BY id").fetchall()],
            "copies": [row_to_dict(row) for row in db.execute("SELECT * FROM copies ORDER BY id").fetchall()],
            "locations": [row_to_dict(row) for row in db.execute("SELECT * FROM locations ORDER BY id").fetchall()],
            "tags": [row_to_dict(row) for row in db.execute("SELECT * FROM tags ORDER BY id").fetchall()],
        }


@app.get("/api/export/csv")
def export_csv() -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "isbn13",
            "title",
            "series_name",
            "volume_number",
            "author",
            "publisher",
            "label",
            "category",
            "location_name",
            "location_detail",
            "ownership_status",
            "memo",
        ]
    )
    with connect() as db:
        rows = db.execute(f"{COPY_SELECT} ORDER BY c.created_at DESC").fetchall()
    for row in rows:
        writer.writerow(
            [
                row["isbn13"],
                row["title"],
                row["series_name"],
                row["volume_number"],
                row["author"],
                row["publisher"],
                row["label"],
                row["category"],
                row["location_name"],
                row["location_detail"],
                row["ownership_status"],
                row["memo"],
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=lattice-index.csv"},
    )


@app.post("/api/backup")
def backup_sqlite() -> FileResponse:
    init_db()
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"lattice-index-{now_iso().replace(':', '').replace('+', '_')}.sqlite3"
    shutil.copy2(DB_PATH, target)
    return FileResponse(target, filename=target.name, media_type="application/octet-stream")
