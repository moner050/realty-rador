"""v2 검색 응답 DTO."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ComplexGroupItem:
    complex_id: int
    complex_name: str
    address: str
    household_count: int
    construction_year: int
    min_price: int
    max_price: int
    listing_count: int
    listings: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class SearchResult:
    items: list[Any]
    next_cursor: str | None
    has_more: bool
    grouped_items: list[ComplexGroupItem] = field(default_factory=list)
    is_grouped: bool = False
