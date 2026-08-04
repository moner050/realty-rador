from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import md5

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.enrichment.naver_maps.backfill import ComplexGeocodeBackfill
from realty_radar.enrichment.naver_maps.geocoder import GeocodeResult, GeocodeStatus
from realty_radar.infrastructure.database.models.base import Base
from realty_radar.infrastructure.database.models.v2 import (
    GEOCODE_STATUS_FAILED,
    GEOCODE_STATUS_PENDING,
    ComplexCurrent,
)


class StaticGeocoder:
    is_configured = True

    def __init__(self, results):
        self.results = results

    def geocode(self, address):
        return self.results[address]


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _complex(complex_id, address, *, status=GEOCODE_STATUS_PENDING, retry_after=None):
    observed_at = datetime(2026, 8, 3, 6, 0)
    return ComplexCurrent(
        complex_id=complex_id,
        region_code=1150010200,
        name=f"테스트 아파트 {complex_id}",
        normalized_name=f"테스트아파트{complex_id}",
        address=address,
        geocode_status=status,
        geocode_retry_after=retry_after,
        state_hash=bytes([complex_id]) * 16,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        updated_at=observed_at,
    )


def test_backfill_updates_pending_coordinate_without_touching_failed_row_before_retry():
    session = _session()
    now = datetime(2026, 8, 3, 7, 0)
    pending_address = "서울특별시 강서구 테스트로 1"
    failed_address = "서울특별시 강서구 테스트로 2"
    session.add_all(
        [
            _complex(1, pending_address),
            _complex(2, failed_address, status=GEOCODE_STATUS_FAILED, retry_after=now + timedelta(hours=1)),
        ]
    )
    session.commit()

    stats = ComplexGeocodeBackfill(
        session,
        StaticGeocoder(
            {
                pending_address: GeocodeResult(
                    GeocodeStatus.OK,
                    latitude=Decimal("37.5500000"),
                    longitude=Decimal("126.8500000"),
                )
            }
        ),
    ).run(batch_size=10, now=now)
    session.commit()

    refreshed_pending = session.get(ComplexCurrent, 1)
    refreshed_failed = session.get(ComplexCurrent, 2)
    assert stats.selected_count == 1
    assert stats.ok_count == 1
    assert refreshed_pending.latitude == Decimal("37.5500000")
    assert refreshed_pending.longitude == Decimal("126.8500000")
    assert refreshed_pending.geocode_status == GeocodeStatus.OK
    assert refreshed_pending.geocoded_address_hash == md5(pending_address.encode("utf-8"), usedforsecurity=False).digest()
    assert refreshed_pending.geocoded_at == now
    assert refreshed_pending.geocode_retry_after is None
    assert refreshed_failed.geocode_status == GEOCODE_STATUS_FAILED


def test_backfill_delays_failed_geocode_retry_for_six_hours():
    session = _session()
    now = datetime(2026, 8, 3, 7, 0)
    address = "서울특별시 강서구 테스트로 1"
    session.add(_complex(1, address))
    session.commit()

    stats = ComplexGeocodeBackfill(
        session,
        StaticGeocoder({address: GeocodeResult(GeocodeStatus.FAILED)}),
    ).run(batch_size=10, now=now)
    session.commit()

    refreshed = session.get(ComplexCurrent, 1)
    assert stats.failed_count == 1
    assert refreshed.geocode_status == GEOCODE_STATUS_FAILED
    assert refreshed.geocode_attempted_at == now
    assert refreshed.geocode_retry_after == now + timedelta(hours=6)


def test_backfill_only_geocodes_requested_pending_complexes():
    session = _session()
    now = datetime(2026, 8, 3, 7, 0)
    addresses = {
        1: "서울특별시 강서구 테스트로 1",
        2: "서울특별시 강서구 테스트로 2",
        3: "서울특별시 강서구 테스트로 3",
    }
    session.add_all([_complex(complex_id, address) for complex_id, address in addresses.items()])
    session.commit()

    stats = ComplexGeocodeBackfill(
        session,
        StaticGeocoder(
            {
                addresses[1]: GeocodeResult(GeocodeStatus.OK, Decimal("37.5500000"), Decimal("126.8500000")),
                addresses[3]: GeocodeResult(GeocodeStatus.OK, Decimal("37.5600000"), Decimal("126.8600000")),
            }
        ),
    ).run(batch_size=10, now=now, complex_ids=[3, 1])

    assert stats.selected_count == 2
    assert session.get(ComplexCurrent, 1).geocode_status == GeocodeStatus.OK
    assert session.get(ComplexCurrent, 2).geocode_status == GEOCODE_STATUS_PENDING
    assert session.get(ComplexCurrent, 3).geocode_status == GeocodeStatus.OK
