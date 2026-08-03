"""현재 검색 결과를 검증된 단지 지도 마커로 변환한다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.domain.listing.models import SearchResult
from realty_radar.infrastructure.database.models.v2 import GEOCODE_STATUS_OK, ComplexCurrent


@dataclass(frozen=True, slots=True)
class ListingMapMarker:
    complex_id: int
    complex_name: str
    address: str
    latitude: float
    longitude: float
    listing_count: int
    min_price: int
    max_price: int

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "complex_id": self.complex_id,
            "complex_name": self.complex_name,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "listing_count": self.listing_count,
            "min_price": self.min_price,
            "max_price": self.max_price,
        }


class ListingMapService:
    """목록 hot query와 분리된 단지 좌표 batch lookup."""

    def __init__(self, session: Session):
        self.session = session

    def build_markers(self, result: SearchResult) -> list[ListingMapMarker]:
        summaries = self._summaries(result)
        if not summaries:
            return []

        complex_ids = list(summaries)
        coordinates = {
            row.complex_id: row
            for row in self.session.scalars(
                select(ComplexCurrent).where(
                    ComplexCurrent.complex_id.in_(complex_ids),
                    ComplexCurrent.geocode_status == GEOCODE_STATUS_OK,
                    ComplexCurrent.latitude.is_not(None),
                    ComplexCurrent.longitude.is_not(None),
                )
            ).all()
        }
        markers: list[ListingMapMarker] = []
        for complex_id, summary in summaries.items():
            coordinate = coordinates.get(complex_id)
            if coordinate is None:
                continue
            markers.append(
                ListingMapMarker(
                    complex_id=complex_id,
                    complex_name=summary["complex_name"],
                    address=summary["address"],
                    latitude=float(coordinate.latitude),
                    longitude=float(coordinate.longitude),
                    listing_count=summary["listing_count"],
                    min_price=summary["min_price"],
                    max_price=summary["max_price"],
                )
            )
        return markers

    @staticmethod
    def _summaries(result: SearchResult) -> dict[int, dict[str, Any]]:
        if result.is_grouped:
            return {
                group.complex_id: {
                    "complex_name": group.complex_name,
                    "address": group.address,
                    "listing_count": group.listing_count,
                    "min_price": group.min_price,
                    "max_price": group.max_price,
                }
                for group in result.grouped_items
            }

        summaries: dict[int, dict[str, Any]] = {}
        for item in result.items:
            current = summaries.setdefault(
                item.complex_id,
                {
                    "complex_name": item.complex_name,
                    "address": item.address,
                    "listing_count": 0,
                    "min_price": item.primary_price,
                    "max_price": item.primary_price,
                },
            )
            current["listing_count"] += 1
            current["min_price"] = min(current["min_price"], item.primary_price)
            current["max_price"] = max(current["max_price"], item.primary_price)
        return summaries
