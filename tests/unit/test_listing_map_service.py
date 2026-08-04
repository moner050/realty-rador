from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_map_service import (
    ListingMapMarker,
    ListingMapService,
    cluster_map_complexes,
)
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.domain.listing.models import ComplexGroupItem, SearchResult
from realty_radar.infrastructure.database.models.base import Base
from realty_radar.infrastructure.database.models.v2 import (
    GEOCODE_STATUS_OK,
    ComplexCurrent,
    ListingCurrent,
)


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


def _listing(article_id, complex_id, price):
    observed_at = datetime(2026, 8, 3, 6, 0)
    return ListingCurrent(
        article_id=article_id,
        complex_id=complex_id,
        region_code=1150010200,
        complex_name=f"test complex {complex_id}",
        address=f"test address {complex_id}",
        trade_type=1,
        primary_price=price,
        state_hash=bytes([article_id]) * 16,
        last_seen_job_id=1,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        last_changed_at=observed_at,
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
            "kind": "marker",
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


def test_map_viewport_aggregates_all_matching_complexes_even_when_listing_page_size_is_one():
    session = _session()
    session.add_all(
        [
            _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
            _complex(2, latitude=Decimal("37.5100000"), longitude=Decimal("126.8100000"), status=GEOCODE_STATUS_OK),
            _complex(3),
            _listing(1, 1, 510_000_000),
            _listing(2, 1, 500_000_000),
            _listing(3, 2, 600_000_000),
            _listing(4, 3, 700_000_000),
        ]
    )
    session.commit()

    viewport = ListingMapService(session).build_viewport(
        ListingSearchFilter(page_size=1), applicant=None, zoom=7
    )

    assert viewport.matching_complex_count == 3
    assert viewport.mapped_complex_count == 2
    assert viewport.unmapped_complex_count == 1
    assert viewport.markers == ()
    assert [
        (cluster.complex_count, cluster.listing_count, cluster.min_price, cluster.max_price)
        for cluster in viewport.clusters
    ] == [(2, 3, 500_000_000, 600_000_000)]


def test_sql_map_viewport_matches_reference_stream_for_ordinary_filters():
    session = _session()
    session.add_all(
        [
            _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
            _complex(2, latitude=Decimal("37.5100000"), longitude=Decimal("126.8100000"), status=GEOCODE_STATUS_OK),
            _complex(3),
            _listing(1, 1, 510_000_000),
            _listing(2, 1, 500_000_000),
            _listing(3, 2, 600_000_000),
            _listing(4, 3, 700_000_000),
        ]
    )
    session.commit()
    service = ListingMapService(session)
    filters = ListingSearchFilter()

    expected = service._build_stream_viewport(filters, None, zoom=14)

    assert service.build_viewport(filters, None, zoom=14) == expected


def test_sql_map_viewport_uses_lowest_article_text_when_complex_text_differs():
    session = _session()
    first_listing = _listing(1, 1, 510_000_000)
    first_listing.complex_name = "z first complex"
    first_listing.address = "z first address"
    later_listing = _listing(2, 1, 500_000_000)
    later_listing.complex_name = "a later complex"
    later_listing.address = "a later address"
    session.add_all(
        [
            _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
            first_listing,
            later_listing,
        ]
    )
    session.commit()
    service = ListingMapService(session)
    filters = ListingSearchFilter()

    expected = service._build_stream_viewport(filters, None, zoom=14)
    actual = service.build_viewport(filters, None, zoom=14)

    assert actual == expected
    assert (actual.markers[0].complex_name, actual.markers[0].address) == (
        "z first complex",
        "z first address",
    )


def test_ordinary_map_viewport_does_not_stream_listing_entities(monkeypatch):
    session = _session()
    session.add_all(
        [
            _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
            _complex(2, latitude=Decimal("37.5100000"), longitude=Decimal("126.8100000"), status=GEOCODE_STATUS_OK),
            _complex(3),
            _listing(1, 1, 510_000_000),
            _listing(2, 2, 600_000_000),
            _listing(3, 3, 700_000_000),
        ]
    )
    session.commit()
    from realty_radar.application.listing_search_service import ListingSearchService

    monkeypatch.setattr(
        ListingSearchService,
        "stream_map_matching_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not stream entities")),
    )

    viewport = ListingMapService(session).build_viewport(ListingSearchFilter(), None, zoom=14)

    assert viewport.matching_complex_count == 3


def test_ordinary_map_viewport_projects_only_aggregate_candidate_columns():
    session = _session()
    session.add_all(
        [
            _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
            _listing(1, 1, 510_000_000),
        ]
    )
    session.commit()
    select_statements = []

    def capture_selects(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            select_statements.append(statement.lower())

    event.listen(session.bind, "before_cursor_execute", capture_selects)
    try:
        ListingMapService(session).build_viewport(ListingSearchFilter(), None, zoom=14)
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_selects)

    assert select_statements
    assert all("listing_current.description" not in statement for statement in select_statements)
    assert all("listing_current.building_name" not in statement for statement in select_statements)


def test_policy_map_viewport_keeps_stream_fallback(monkeypatch):
    session = _session()
    from realty_radar.application.listing_search_service import ListingSearchService

    original = ListingSearchService.stream_map_matching_rows
    calls = 0

    def spy(self, filters, applicant):
        nonlocal calls
        calls += 1
        yield from original(self, filters, applicant)

    monkeypatch.setattr(ListingSearchService, "stream_map_matching_rows", spy)

    viewport = ListingMapService(session).build_viewport(
        ListingSearchFilter(only_eligible_loans=True), None, zoom=14
    )

    assert calls == 1
    assert viewport.matching_complex_count == 0


def test_map_viewport_returns_single_markers_after_zoomed_in_cell_split():
    session = _session()
    session.add_all(
        [
            _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
            _complex(2, latitude=Decimal("37.5100000"), longitude=Decimal("126.8100000"), status=GEOCODE_STATUS_OK),
            _listing(1, 1, 500_000_000),
            _listing(2, 2, 600_000_000),
        ]
    )
    session.commit()

    viewport = ListingMapService(session).build_viewport(ListingSearchFilter(), applicant=None, zoom=14)

    assert [marker.complex_id for marker in viewport.markers] == [1, 2]
    assert viewport.clusters == ()


def test_cluster_map_complexes_keeps_grid_boundary_memberships_predictable():
    markers, clusters = cluster_map_complexes(
        (
            ListingMapMarker(
                complex_id=1,
                complex_name="one",
                address="one",
                latitude=37.5000,
                longitude=126.8000,
                listing_count=1,
                min_price=500_000_000,
                max_price=500_000_000,
            ),
            ListingMapMarker(
                complex_id=2,
                complex_name="two",
                address="two",
                latitude=37.5049,
                longitude=126.8049,
                listing_count=2,
                min_price=510_000_000,
                max_price=520_000_000,
            ),
            ListingMapMarker(
                complex_id=3,
                complex_name="three",
                address="three",
                latitude=37.5050,
                longitude=126.8050,
                listing_count=1,
                min_price=600_000_000,
                max_price=600_000_000,
            ),
        ),
        zoom=14,
    )

    assert [marker.complex_id for marker in markers] == [3]
    assert [cluster.to_dict() for cluster in clusters] == [
        {
            "kind": "cluster",
            "latitude": 37.50245,
            "longitude": 126.80245,
            "west": 126.8,
            "south": 37.5,
            "east": 126.8049,
            "north": 37.5049,
            "complex_count": 2,
            "listing_count": 3,
            "min_price": 500_000_000,
            "max_price": 520_000_000,
        }
    ]


def test_map_viewport_applies_verified_coordinate_bounds_to_matching_complexes():
    session = _session()
    session.add_all(
        [
            _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
            _complex(2, latitude=Decimal("37.6000000"), longitude=Decimal("126.9000000"), status=GEOCODE_STATUS_OK),
            _listing(1, 1, 500_000_000),
            _listing(2, 2, 600_000_000),
        ]
    )
    session.commit()

    viewport = ListingMapService(session).build_viewport(
        ListingSearchFilter(
            map_west=Decimal("126.8000000"),
            map_south=Decimal("37.5000000"),
            map_east=Decimal("126.8500000"),
            map_north=Decimal("37.5500000"),
        ),
        applicant=None,
        zoom=14,
    )

    assert viewport.matching_complex_count == 1
    assert [marker.complex_id for marker in viewport.markers] == [1]
    assert viewport.bounds == (126.8, 37.5, 126.85, 37.55)
