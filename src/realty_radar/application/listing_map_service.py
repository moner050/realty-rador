"""현재 검색 결과를 검증된 단지 지도 마커로 변환한다."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from realty_radar.domain.listing.models import SearchResult
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.infrastructure.database.models.v2 import (
    GEOCODE_STATUS_OK,
    ComplexCurrent,
    ListingCurrent,
)


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
            "kind": "marker",
            "complex_id": self.complex_id,
            "complex_name": self.complex_name,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "listing_count": self.listing_count,
            "min_price": self.min_price,
            "max_price": self.max_price,
        }


@dataclass(frozen=True, slots=True)
class ListingMapCluster:
    latitude: float
    longitude: float
    west: float
    south: float
    east: float
    north: float
    complex_count: int
    listing_count: int
    min_price: int
    max_price: int

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "kind": "cluster",
            "latitude": self.latitude,
            "longitude": self.longitude,
            "west": self.west,
            "south": self.south,
            "east": self.east,
            "north": self.north,
            "complex_count": self.complex_count,
            "listing_count": self.listing_count,
            "min_price": self.min_price,
            "max_price": self.max_price,
        }


@dataclass(frozen=True, slots=True)
class ListingMapViewport:
    markers: tuple[ListingMapMarker, ...]
    clusters: tuple[ListingMapCluster, ...]
    matching_complex_count: int
    mapped_complex_count: int
    unmapped_complex_count: int
    bounds: tuple[float, float, float, float] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "markers": [marker.to_dict() for marker in self.markers],
            "clusters": [cluster.to_dict() for cluster in self.clusters],
            "matching_complex_count": self.matching_complex_count,
            "mapped_complex_count": self.mapped_complex_count,
            "unmapped_complex_count": self.unmapped_complex_count,
            "bounds": self.bounds,
        }


def map_cell_size(zoom: int) -> Decimal:
    if zoom <= 7:
        return Decimal("0.50")
    if zoom <= 9:
        return Decimal("0.10")
    if zoom <= 11:
        return Decimal("0.02")
    return Decimal("0.005")


def cluster_map_complexes(
    complexes: tuple[ListingMapMarker, ...], zoom: int
) -> tuple[tuple[ListingMapMarker, ...], tuple[ListingMapCluster, ...]]:
    cell_size = map_cell_size(zoom)
    cells: dict[tuple[int, int], list[ListingMapMarker]] = {}
    for complex_marker in sorted(complexes, key=lambda marker: marker.complex_id):
        latitude = Decimal(str(complex_marker.latitude))
        longitude = Decimal(str(complex_marker.longitude))
        key = (
            int((latitude / cell_size).to_integral_value(rounding=ROUND_FLOOR)),
            int((longitude / cell_size).to_integral_value(rounding=ROUND_FLOOR)),
        )
        cells.setdefault(key, []).append(complex_marker)

    markers: list[ListingMapMarker] = []
    clusters: list[ListingMapCluster] = []
    for _, members in sorted(cells.items()):
        if len(members) == 1:
            markers.append(members[0])
            continue
        latitudes = [Decimal(str(member.latitude)) for member in members]
        longitudes = [Decimal(str(member.longitude)) for member in members]
        clusters.append(
            ListingMapCluster(
                latitude=float(sum(latitudes) / len(latitudes)),
                longitude=float(sum(longitudes) / len(longitudes)),
                west=float(min(longitudes)),
                south=float(min(latitudes)),
                east=float(max(longitudes)),
                north=float(max(latitudes)),
                complex_count=len(members),
                listing_count=sum(member.listing_count for member in members),
                min_price=min(member.min_price for member in members),
                max_price=max(member.max_price for member in members),
            )
        )
    return tuple(sorted(markers, key=lambda marker: marker.complex_id)), tuple(clusters)


class ListingMapService:
    """목록 hot query와 분리된 단지 좌표 batch lookup."""

    def __init__(self, session: Session):
        self.session = session

    def build_viewport(
        self,
        filters: ListingSearchFilter,
        applicant: Any,
        zoom: int,
    ) -> ListingMapViewport:
        from realty_radar.application.listing_search_service import ListingSearchService

        if filters.only_eligible_loans or filters.only_purchase_affordable:
            return self._build_stream_viewport(filters, applicant, zoom)

        statement, _ = ListingSearchService(self.session).map_candidate_rows(filters, applicant)
        return self._build_sql_viewport(statement, filters, zoom)

    def _build_sql_viewport(
        self,
        statement,
        filters: ListingSearchFilter,
        zoom: int,
    ) -> ListingMapViewport:
        candidates = statement.with_only_columns(
            ListingCurrent.complex_id,
            ListingCurrent.article_id,
            ListingCurrent.complex_name,
            ListingCurrent.address,
            ListingCurrent.primary_price,
            maintain_column_froms=True,
        ).cte("map_candidates")
        matching_complex_count = self.session.scalar(
            select(func.count(func.distinct(candidates.c.complex_id)))
        ) or 0
        aggregates = (
            select(
                candidates.c.complex_id,
                func.min(candidates.c.article_id).label("first_article_id"),
                func.count().label("listing_count"),
                func.min(candidates.c.primary_price).label("min_price"),
                func.max(candidates.c.primary_price).label("max_price"),
            )
            .group_by(candidates.c.complex_id)
            .cte("map_complex_aggregates")
        )
        first_text = (
            select(
                candidates.c.complex_id,
                candidates.c.complex_name,
                candidates.c.address,
            )
            .join(
                aggregates,
                and_(
                    aggregates.c.complex_id == candidates.c.complex_id,
                    aggregates.c.first_article_id == candidates.c.article_id,
                ),
            )
            .cte("map_first_listing_text")
        )
        aggregate_statement = (
            select(
                aggregates.c.complex_id,
                first_text.c.complex_name,
                first_text.c.address,
                ComplexCurrent.latitude,
                ComplexCurrent.longitude,
                aggregates.c.listing_count,
                aggregates.c.min_price,
                aggregates.c.max_price,
            )
            .join(first_text, first_text.c.complex_id == aggregates.c.complex_id)
            .join(ComplexCurrent, ComplexCurrent.complex_id == aggregates.c.complex_id)
            .where(
                ComplexCurrent.geocode_status == GEOCODE_STATUS_OK,
                ComplexCurrent.latitude.is_not(None),
                ComplexCurrent.longitude.is_not(None),
            )
            .order_by(aggregates.c.complex_id)
        )
        complexes = tuple(
            ListingMapMarker(
                complex_id=row.complex_id,
                complex_name=row.complex_name,
                address=row.address,
                latitude=float(row.latitude),
                longitude=float(row.longitude),
                listing_count=row.listing_count,
                min_price=row.min_price,
                max_price=row.max_price,
            )
            for row in self.session.execute(aggregate_statement)
        )
        markers, clusters = cluster_map_complexes(complexes, zoom)
        bounds = (
            (float(filters.map_west), float(filters.map_south), float(filters.map_east), float(filters.map_north))
            if filters.has_map_bounds
            else None
        )
        return ListingMapViewport(
            markers=markers,
            clusters=clusters,
            matching_complex_count=matching_complex_count,
            mapped_complex_count=len(complexes),
            unmapped_complex_count=matching_complex_count - len(complexes),
            bounds=bounds,
        )

    def _build_stream_viewport(
        self,
        filters: ListingSearchFilter,
        applicant: Any,
        zoom: int,
    ) -> ListingMapViewport:
        from realty_radar.application.listing_search_service import ListingSearchService

        summaries: dict[int, dict[str, Any]] = {}
        for row in ListingSearchService(self.session).stream_map_matching_rows(filters, applicant):
            summary = summaries.setdefault(
                row.complex_id,
                {
                    "complex_name": row.complex_name,
                    "address": row.address,
                    "listing_count": 0,
                    "min_price": row.primary_price,
                    "max_price": row.primary_price,
                },
            )
            summary["listing_count"] += 1
            summary["min_price"] = min(summary["min_price"], row.primary_price)
            summary["max_price"] = max(summary["max_price"], row.primary_price)

        coordinates = {
            row.complex_id: row
            for row in self.session.scalars(
                select(ComplexCurrent).where(
                    ComplexCurrent.complex_id.in_(summaries),
                    ComplexCurrent.geocode_status == GEOCODE_STATUS_OK,
                    ComplexCurrent.latitude.is_not(None),
                    ComplexCurrent.longitude.is_not(None),
                )
            )
        } if summaries else {}
        complexes = tuple(
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
            for complex_id, summary in sorted(summaries.items())
            if (coordinate := coordinates.get(complex_id)) is not None
        )
        markers, clusters = cluster_map_complexes(complexes, zoom)
        bounds = (
            (float(filters.map_west), float(filters.map_south), float(filters.map_east), float(filters.map_north))
            if filters.has_map_bounds
            else None
        )
        return ListingMapViewport(
            markers=markers,
            clusters=clusters,
            matching_complex_count=len(summaries),
            mapped_complex_count=len(complexes),
            unmapped_complex_count=len(summaries) - len(complexes),
            bounds=bounds,
        )

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

    def complex_ids(self, result: SearchResult) -> list[int]:
        return list(self._summaries(result))

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
