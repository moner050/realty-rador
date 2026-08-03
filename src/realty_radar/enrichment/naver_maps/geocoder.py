"""NAVER Maps REST 지오코딩 클라이언트."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import IntEnum

import httpx

from realty_radar.config import settings
from realty_radar.infrastructure.database.models.v2 import (
    GEOCODE_STATUS_FAILED,
    GEOCODE_STATUS_NOT_FOUND,
    GEOCODE_STATUS_OK,
)


class GeocodeStatus(IntEnum):
    OK = GEOCODE_STATUS_OK
    NOT_FOUND = GEOCODE_STATUS_NOT_FOUND
    FAILED = GEOCODE_STATUS_FAILED
    NOT_CONFIGURED = 4


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    status: GeocodeStatus
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class NaverGeocoder:
    """서버 전용 NAVER Maps 주소 지오코더."""

    endpoint = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.client_id = client_id if client_id is not None else settings.naver_map_client_id
        self.client_secret = client_secret if client_secret is not None else settings.naver_map_client_secret
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def geocode(self, address: str) -> GeocodeResult:
        if not self.is_configured:
            return GeocodeResult(GeocodeStatus.NOT_CONFIGURED)

        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout_seconds) as client:
                response = client.get(
                    self.endpoint,
                    params={"query": address},
                    headers={
                        "Accept": "application/json",
                        "x-ncp-apigw-api-key-id": self.client_id,
                        "x-ncp-apigw-api-key": self.client_secret,
                    },
                )
        except httpx.HTTPError:
            return GeocodeResult(GeocodeStatus.FAILED)

        if response.status_code != 200:
            return GeocodeResult(GeocodeStatus.FAILED)

        try:
            payload = response.json()
            addresses = payload.get("addresses") or []
            if not addresses:
                return GeocodeResult(GeocodeStatus.NOT_FOUND)
            first = addresses[0]
            return GeocodeResult(
                GeocodeStatus.OK,
                latitude=Decimal(str(first["y"])),
                longitude=Decimal(str(first["x"])),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return GeocodeResult(GeocodeStatus.FAILED)
