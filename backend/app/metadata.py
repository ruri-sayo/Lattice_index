from __future__ import annotations

import httpx

from .isbn import normalize_isbn


def _join(values: list[str] | None) -> str | None:
    return ", ".join(values) if values else None


async def lookup_openbd(isbn13: str) -> dict | None:
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get("https://api.openbd.jp/v1/get", params={"isbn": isbn13})
        response.raise_for_status()
        payload = response.json()
    if not payload or payload[0] is None:
        return None
    raw = payload[0]
    summary = raw.get("summary") or {}
    onix = raw.get("onix") or {}
    descriptive = onix.get("DescriptiveDetail") or {}
    collateral = onix.get("CollateralDetail") or {}
    text_contents = collateral.get("TextContent") or []
    description = None
    for item in text_contents:
        if item.get("Text"):
            description = item["Text"]
            break
    return {
        "isbn13": isbn13,
        "source": "openbd",
        "title": summary.get("title") or descriptive.get("TitleDetail", {}).get("TitleElement", {}).get("TitleText", {}).get("content"),
        "author": summary.get("author"),
        "publisher": summary.get("publisher"),
        "published_date": summary.get("pubdate"),
        "cover_url": summary.get("cover"),
        "description": description,
        "raw": raw,
    }


async def lookup_google_books(isbn13: str) -> dict | None:
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn13}", "maxResults": 1},
        )
        response.raise_for_status()
        payload = response.json()
    items = payload.get("items") or []
    if not items:
        return None
    raw = items[0]
    info = raw.get("volumeInfo") or {}
    return {
        "isbn13": isbn13,
        "source": "google_books",
        "title": info.get("title"),
        "author": _join(info.get("authors")),
        "publisher": info.get("publisher"),
        "published_date": info.get("publishedDate"),
        "description": info.get("description"),
        "page_count": info.get("pageCount"),
        "category": _join(info.get("categories")),
        "cover_url": (info.get("imageLinks") or {}).get("thumbnail"),
        "raw": raw,
    }


async def lookup_book(isbn: str) -> dict:
    isbn13, _ = normalize_isbn(isbn)
    result = await lookup_openbd(isbn13)
    if result:
        return result
    result = await lookup_google_books(isbn13)
    if result:
        return result
    return {"isbn13": isbn13, "source": "manual", "title": "", "raw": None}

