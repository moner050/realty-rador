"""단지 주소를 검증 좌표로 보강하는 명시적 배치 작업."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import md5
from typing import Iterable, Protocol

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from realty_radar.enrichment.naver_maps.geocoder import GeocodeResult, GeocodeStatus
from realty_radar.infrastructure.database.models.v2 import (
    GEOCODE_STATUS_FAILED,
    GEOCODE_STATUS_NOT_FOUND,
    GEOCODE_STATUS_OK,
    GEOCODE_STATUS_PENDING,
    ComplexCurrent,
)


class Geocoder(Protocol):
    is_configured: bool

    def geocode(self, address: str) -> GeocodeResult: ...


@dataclass(frozen=True, slots=True)
class GeocodeBackfillStats:
    selected_count: int = 0
    external_request_count: int = 0
    reused_count: int = 0
    ok_count: int = 0
    not_found_count: int = 0
    failed_count: int = 0


class ComplexGeocodeBackfill:
    """PENDING 또는 재시도 시각이 지난 FAILED 단지만 지오코딩한다."""

    retry_delay = timedelta(hours=6)

    def __init__(self, session: Session, geocoder: Geocoder):
        self.session = session
        self.geocoder = geocoder

    def run(
        self,
        *,
        batch_size: int,
        now: datetime,
        complex_ids: Iterable[int] | None = None,
        max_requests: int | None = None,
    ) -> GeocodeBackfillStats:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not self.geocoder.is_configured:
            raise RuntimeError("NAVER_MAP_CLIENT_ID and NAVER_MAP_CLIENT_SECRET are required")

        statement = select(ComplexCurrent).where(
            or_(
                ComplexCurrent.geocode_status == GEOCODE_STATUS_PENDING,
                and_(
                    ComplexCurrent.geocode_status == GEOCODE_STATUS_FAILED,
                    ComplexCurrent.geocode_retry_after.is_not(None),
                    ComplexCurrent.geocode_retry_after <= now,
                ),
            )
        )
        if complex_ids is not None:
            statement = statement.where(ComplexCurrent.complex_id.in_(sorted({int(item) for item in complex_ids})))
        candidates = self.session.scalars(
            statement.order_by(ComplexCurrent.complex_id).limit(batch_size)
        ).all()

        cached_coordinates_by_address = {
            address: (latitude, longitude)
            for address, latitude, longitude in self.session.execute(
                select(ComplexCurrent.address, ComplexCurrent.latitude, ComplexCurrent.longitude).where(
                    ComplexCurrent.geocode_status == GEOCODE_STATUS_OK,
                    ComplexCurrent.address.in_({candidate.address for candidate in candidates}),
                )
            ).all()
        }
        outcomes_by_address: dict[str, GeocodeResult] = {}
        external_request_count = 0
        reused_count = 0
        ok_count = 0
        not_found_count = 0
        failed_count = 0
        for candidate in candidates:
            cached_coordinates = cached_coordinates_by_address.get(candidate.address)
            if cached_coordinates is not None:
                result = GeocodeResult(GeocodeStatus.OK, *cached_coordinates)
                reused_count += 1
            elif candidate.address in outcomes_by_address:
                result = outcomes_by_address[candidate.address]
                reused_count += 1
            else:
                if max_requests is not None and external_request_count >= max_requests:
                    break
                external_request_count += 1
                result = self.geocoder.geocode(candidate.address)
                outcomes_by_address[candidate.address] = result
            candidate.geocode_attempted_at = now
            if result.status is GeocodeStatus.OK:
                candidate.latitude = result.latitude
                candidate.longitude = result.longitude
                candidate.geocode_status = GEOCODE_STATUS_OK
                candidate.geocoded_address_hash = _address_hash(candidate.address)
                candidate.geocoded_at = now
                candidate.geocode_retry_after = None
                ok_count += 1
            elif result.status is GeocodeStatus.NOT_FOUND:
                candidate.latitude = None
                candidate.longitude = None
                candidate.geocode_status = GEOCODE_STATUS_NOT_FOUND
                candidate.geocoded_address_hash = _address_hash(candidate.address)
                candidate.geocoded_at = now
                candidate.geocode_retry_after = None
                not_found_count += 1
            else:
                candidate.latitude = None
                candidate.longitude = None
                candidate.geocode_status = GEOCODE_STATUS_FAILED
                candidate.geocoded_address_hash = None
                candidate.geocoded_at = None
                candidate.geocode_retry_after = now + self.retry_delay
                failed_count += 1

        return GeocodeBackfillStats(
            selected_count=len(candidates),
            external_request_count=external_request_count,
            reused_count=reused_count,
            ok_count=ok_count,
            not_found_count=not_found_count,
            failed_count=failed_count,
        )


def _address_hash(address: str) -> bytes:
    return md5(address.encode("utf-8"), usedforsecurity=False).digest()
