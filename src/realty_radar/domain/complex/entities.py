from dataclasses import dataclass
from decimal import Decimal
from realty_radar.constants import MatchMethod


@dataclass
class ComplexMatchResult:
    """단지 매칭 결과 DTO."""

    complex_id: int | None
    match_score: Decimal
    match_method: MatchMethod
    alias_used: str | None = None
    requires_manual_review: bool = False
