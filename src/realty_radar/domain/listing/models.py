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
class SearchDiagnostics:
    mode: str = "normal"
    sql_count: int = 0
    candidate_count: int = 0
    db_time_ms: float = 0.0
    loan_evaluation_time_ms: float = 0.0
    total_time_ms: float = 0.0


@dataclass(slots=True)
class SearchResult:
    items: list[Any]
    next_cursor: str | None
    has_more: bool
    previous_cursor: str | None = None
    has_previous: bool = False
    grouped_items: list[ComplexGroupItem] = field(default_factory=list)
    is_grouped: bool = False
    diagnostics: SearchDiagnostics = field(default_factory=SearchDiagnostics)
