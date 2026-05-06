from __future__ import annotations

import re


FULL_WIDTH_DIGITS = str.maketrans("０１２３４５６７８９Ｘｘ", "0123456789XX")


class ISBNError(ValueError):
    pass


def _clean_isbn(value: str) -> str:
    return re.sub(r"[\s\-‐‑‒–—―]+", "", value.translate(FULL_WIDTH_DIGITS)).upper()


def _is_valid_isbn10(value: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", value):
        return False
    total = 0
    for index, char in enumerate(value):
        digit = 10 if char == "X" else int(char)
        total += (10 - index) * digit
    return total % 11 == 0


def _is_valid_isbn13(value: str) -> bool:
    if not re.fullmatch(r"\d{13}", value):
        return False
    total = sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(value[:12]))
    check = (10 - (total % 10)) % 10
    return check == int(value[-1])


def _isbn10_to_isbn13(value: str) -> str:
    prefix = "978" + value[:9]
    total = sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(prefix))
    return prefix + str((10 - (total % 10)) % 10)


def normalize_isbn(value: str) -> tuple[str, str | None]:
    cleaned = _clean_isbn(value)
    if len(cleaned) == 10:
        if not _is_valid_isbn10(cleaned):
            raise ISBNError("ISBN-10のチェックディジットが不正です。")
        return _isbn10_to_isbn13(cleaned), cleaned
    if len(cleaned) == 13:
        if not cleaned.startswith(("978", "979")):
            raise ISBNError("ISBN-13は978または979で始まる必要があります。")
        if not _is_valid_isbn13(cleaned):
            raise ISBNError("ISBN-13のチェックディジットが不正です。")
        return cleaned, None
    raise ISBNError("ISBNは10桁または13桁で入力してください。")


def looks_like_isbn(value: str) -> bool:
    cleaned = _clean_isbn(value)
    return bool(re.fullmatch(r"\d{9}[\dX]|\d{13}", cleaned))

