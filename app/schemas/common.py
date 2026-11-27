import math
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


def build_paginated_response(
    items: list[T],
    total: int,
    page: int,
    size: int,
) -> PaginatedResponse[T]:
    pages = math.ceil(total / size) if total > 0 else 0
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def ensure_no_nul_bytes(value: str | None) -> str | None:
    if value is not None and "\x00" in value:
        raise ValueError("Value must not contain NUL bytes")
    return value
