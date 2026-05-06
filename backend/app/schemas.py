from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


OwnershipStatus = Literal["owned", "disposed", "lost", "sold"]
Condition = Literal["new", "good", "damaged", "unknown"]


class CopyCreate(BaseModel):
    location_id: int | None = None
    location_detail: str | None = None
    condition: Condition | None = "unknown"
    acquired_date: str | None = None
    memo: str | None = None


class BookCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    isbn13: str | None = None
    isbn10: str | None = None
    title: str = Field(min_length=1)
    title_kana: str | None = None
    subtitle: str | None = None
    series_name: str | None = None
    series_kana: str | None = None
    volume_number: str | None = None
    author: str | None = None
    illustrator: str | None = None
    translator: str | None = None
    publisher: str | None = None
    label: str | None = None
    category: str | None = None
    published_date: str | None = None
    page_count: int | None = None
    description: str | None = None
    cover_url: str | None = None
    metadata_source: str = "manual"
    metadata_raw_json: dict[str, Any] | None = None
    duplicate_action: Literal["add_copy"] | None = None
    copy_: CopyCreate = Field(default_factory=CopyCreate, alias="copy")


class LookupRequest(BaseModel):
    isbn: str


class CopyUpdate(BaseModel):
    ownership_status: OwnershipStatus | None = None
    location_id: int | None = None
    location_detail: str | None = None
    condition: Condition | None = None
    acquired_date: str | None = None
    last_seen_at: str | None = None
    memo: str | None = None


class LocationCreate(BaseModel):
    name: str = Field(min_length=1)
    sort_order: int = 0


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    sort_order: int | None = None
    is_active: bool | None = None
