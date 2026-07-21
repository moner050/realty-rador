from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from realty_radar.constants import ListingStatus, MortgageStatus, TransactionType


@dataclass
class SourceSearchRequest:
    """사이트 검색 요청 DTO."""

    source_code: str
    region_name: str
    transaction_types: list[TransactionType] = field(default_factory=list)
    limit: int = 50


@dataclass
class RawListing:
    """크롤러가 수집한 원본 데이터 모델."""

    source_code: str
    external_listing_id: str
    source_url: str
    complex_name_raw: str | None = None
    address_raw: str | None = None
    price_raw: str | None = None
    area_raw: str | None = None
    floor_raw: str | None = None
    description_raw: str | None = None
    collected_at: datetime = field(default_factory=datetime.now)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedListing:
    """정규화된 매물 데이터 모델."""

    source_code: str
    external_listing_id: str
    source_url: str
    transaction_type: TransactionType
    complex_name_raw: str | None = None
    sale_price: int | None = None
    deposit: int | None = None
    monthly_rent: int | None = None
    exclusive_area: Decimal | None = None
    supply_area: Decimal | None = None
    floor_number: int | None = None
    floor_group: str | None = None
    total_floor: int | None = None
    direction: str | None = None
    address_raw: str | None = None
    description: str | None = None
    mortgage_status: MortgageStatus = MortgageStatus.UNKNOWN
    mortgage_amount: int | None = None
    mortgage_raw_text: str | None = None
    mortgage_confidence: Decimal | None = None
    listing_status: ListingStatus = ListingStatus.ACTIVE
    first_seen_at: datetime = field(default_factory=datetime.now)
    last_seen_at: datetime = field(default_factory=datetime.now)
    raw_payload: dict[str, Any] = field(default_factory=dict)
