from realty_radar.domain.listing.filters import ListingSearchFilter


def test_advanced_filter_dto_properties():
    """고급 필터 DTO 속성 파싱 검증."""
    filters = ListingSearchFilter(
        min_construction_year=2015,
        min_households=500,
        recent_days=3,
        exclude_unknown_mortgage=True,
    )

    assert filters.min_construction_year == 2015
    assert filters.min_households == 500
    assert filters.recent_days == 3
    assert filters.exclude_unknown_mortgage is True
