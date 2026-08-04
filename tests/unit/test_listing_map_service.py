from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_map_service import ListingMapService
from realty_radar.domain.listing.models import ComplexGroupItem, SearchResult
from realty_radar.infrastructure.database.models.base import Base
from realty_radar.infrastructure.database.models.v2 import GEOCODE_STATUS_OK, ComplexCurrent


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _complex(complex_id, *, latitude=None, longitude=None, status=0):
    observed_at = datetime(2026, 8, 3, 6, 0)
    return ComplexCurrent(
        complex_id=complex_id,
        region_code=1150010200,
        name=f"테스트 아파트 {complex_id}",
        normalized_name=f"테스트아파트{complex_id}",
        address=f"서울특별시 강서구 테스트로 {complex_id}",
        latitude=latitude,
        longitude=longitude,
        geocode_status=status,
        state_hash=bytes([complex_id]) * 16,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        updated_at=observed_at,
    )


def test_normal_result_builds_one_verified_marker_per_complex_with_one_coordinate_query():
    session = _session()
    session.add(
        _complex(
            1,
            latitude=Decimal("37.5500000"),
            longitude=Decimal("126.8500000"),
            status=GEOCODE_STATUS_OK,
        )
    )
    session.commit()
    result = SearchResult(
        items=[
            SimpleNamespace(
                complex_id=1,
                complex_name="테스트 아파트 1",
                address="서울특별시 강서구 테스트로 1",
                primary_price=510_000_000,
            ),
            SimpleNamespace(
                complex_id=1,
                complex_name="테스트 아파트 1",
                address="서울특별시 강서구 테스트로 1",
                primary_price=500_000_000,
            ),
        ],
        next_cursor=None,
        has_more=False,
    )
    select_count = 0

    def count_selects(conn, cursor, statement, parameters, context, executemany):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(session.bind, "before_cursor_execute", count_selects)
    try:
        markers = ListingMapService(session).build_markers(result)
    finally:
        event.remove(session.bind, "before_cursor_execute", count_selects)

    assert select_count == 1
    assert [marker.to_dict() for marker in markers] == [
        {
            "complex_id": 1,
            "complex_name": "테스트 아파트 1",
            "address": "서울특별시 강서구 테스트로 1",
            "latitude": 37.55,
            "longitude": 126.85,
            "listing_count": 2,
            "min_price": 500_000_000,
            "max_price": 510_000_000,
        }
    ]


def test_grouped_result_uses_group_listing_count_and_price_range():
    session = _session()
    session.add(
        _complex(
            1,
            latitude=Decimal("37.5500000"),
            longitude=Decimal("126.8500000"),
            status=GEOCODE_STATUS_OK,
        )
    )
    session.commit()
    result = SearchResult(
        items=[],
        next_cursor=None,
        has_more=False,
        is_grouped=True,
        grouped_items=[
            ComplexGroupItem(
                complex_id=1,
                complex_name="테스트 아파트 1",
                address="서울특별시 강서구 테스트로 1",
                household_count=500,
                construction_year=2020,
                min_price=500_000_000,
                max_price=510_000_000,
                listing_count=2,
            )
        ],
    )

    markers = ListingMapService(session).build_markers(result)

    assert [(marker.complex_id, marker.listing_count, marker.min_price, marker.max_price) for marker in markers] == [
        (1, 2, 500_000_000, 510_000_000)
    ]


def test_marker_payload_excludes_unverified_coordinate_instead_of_inventing_one():
    session = _session()
    session.add(_complex(1))
    session.commit()
    result = SearchResult(
        items=[
            SimpleNamespace(
                complex_id=1,
                complex_name="테스트 아파트 1",
                address="서울특별시 강서구 테스트로 1",
                primary_price=500_000_000,
            )
        ],
        next_cursor=None,
        has_more=False,
    )

    markers = ListingMapService(session).build_markers(result)

    assert markers == []


def test_complex_ids_returns_each_normal_result_complex_once_in_result_order():
    session = _session()
    result = SearchResult(
        items=[
            SimpleNamespace(complex_id=7, complex_name="단지 7", address="서울 7", primary_price=700_000_000),
            SimpleNamespace(complex_id=3, complex_name="단지 3", address="서울 3", primary_price=300_000_000),
            SimpleNamespace(complex_id=7, complex_name="단지 7", address="서울 7", primary_price=710_000_000),
        ],
        next_cursor=None,
        has_more=False,
    )

    assert ListingMapService(session).complex_ids(result) == [7, 3]
