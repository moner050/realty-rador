from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import md5

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from realty_radar.enrichment.naver_maps.backfill import (
    ComplexGeocodeBackfill,
    run_geocode_sweep,
)
from realty_radar.enrichment.naver_maps.geocoder import GeocodeResult, GeocodeStatus
from realty_radar.infrastructure.database.models.base import Base
from realty_radar.infrastructure.database.models.v2 import (
    GEOCODE_STATUS_FAILED,
    GEOCODE_STATUS_OK,
    GEOCODE_STATUS_PENDING,
    ComplexCurrent,
)


class StaticGeocoder:
    is_configured = True

    def __init__(self, results):
        self.results = results

    def geocode(self, address):
        return self.results[address]


class CountingGeocoder(StaticGeocoder):
    def __init__(self, results):
        super().__init__(results)
        self.calls = []

    def geocode(self, address):
        self.calls.append(address)
        return super().geocode(address)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _session_factory_with_pending_complexes(count):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add_all(
            [_complex(index, f"address {index}") for index in range(1, count + 1)]
        )
        session.commit()
    return factory


def _status_counts(session):
    return {
        status: sum(
            complex_current.geocode_status == status
            for complex_current in session.query(ComplexCurrent).all()
        )
        for status in (GEOCODE_STATUS_OK, GEOCODE_STATUS_PENDING)
    }


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


def test_backfill_calls_geocoder_once_for_two_pending_complexes_with_same_address():
    session = _session()
    address = "?쒖슱?밸퀎??媛뺤꽌援??뚯뒪?몃줈 1"
    session.add_all([_complex(1, address), _complex(2, address)])
    session.commit()
    geocoder = CountingGeocoder(
        {address: GeocodeResult(GeocodeStatus.OK, Decimal("37.55"), Decimal("126.85"))}
    )

    stats = ComplexGeocodeBackfill(session, geocoder).run(
        batch_size=10,
        now=datetime(2026, 8, 4, 7, 0),
    )

    assert geocoder.calls == [address]
    assert stats.external_request_count == 1
    assert stats.reused_count == 1
    assert {
        session.get(ComplexCurrent, 1).geocode_status,
        session.get(ComplexCurrent, 2).geocode_status,
    } == {GEOCODE_STATUS_OK}


def test_backfill_reuses_an_existing_ok_coordinate_without_calling_geocoder():
    session = _session()
    address = "?쒖슱?밸퀎??媛뺤꽌援??뚯뒪?몃줈 1"
    cached = _complex(1, address, status=GEOCODE_STATUS_OK)
    cached.latitude, cached.longitude = Decimal("37.55"), Decimal("126.85")
    session.add_all([cached, _complex(2, address)])
    session.commit()
    geocoder = CountingGeocoder({})

    stats = ComplexGeocodeBackfill(session, geocoder).run(
        batch_size=10,
        now=datetime(2026, 8, 4, 7, 0),
    )

    assert geocoder.calls == []
    assert stats.external_request_count == 0
    assert stats.reused_count == 1
    assert session.get(ComplexCurrent, 2).latitude == Decimal("37.5500000")


def test_geocode_sweep_commits_each_batch_and_stops_at_request_budget():
    factory = _session_factory_with_pending_complexes(3)
    geocoder = CountingGeocoder(
        {
            f"address {index}": GeocodeResult(
                GeocodeStatus.OK,
                Decimal(f"37.{index}"),
                Decimal(f"126.{index}"),
            )
            for index in range(1, 4)
        }
    )

    stats = run_geocode_sweep(
        factory,
        geocoder,
        now=datetime(2026, 8, 4, 7, 0),
        batch_size=1,
        max_batches=3,
        max_requests=2,
    )

    assert stats.batch_count == 2
    assert stats.external_request_count == 2
    with factory() as session:
        assert _status_counts(session) == {
            GEOCODE_STATUS_OK: 2,
            GEOCODE_STATUS_PENDING: 1,
        }


@pytest.mark.parametrize(
    ("batch_size", "max_batches", "max_requests"),
    [(0, 1, 1), (1, 0, 1), (1, 1, 0)],
)
def test_geocode_sweep_rejects_non_positive_limits(batch_size, max_batches, max_requests):
    with pytest.raises(ValueError):
        run_geocode_sweep(
            _session_factory_with_pending_complexes(1),
            CountingGeocoder({}),
            now=datetime(2026, 8, 4, 7, 0),
            batch_size=batch_size,
            max_batches=max_batches,
            max_requests=max_requests,
        )
