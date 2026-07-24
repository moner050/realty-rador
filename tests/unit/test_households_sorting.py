from realty_radar.constants import SortBy
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.domain.listing.models import ListingFilterParams


def test_sort_by_enum_and_filter_params():
    """SortBy enum 세대수 정렬 추가 및 FilterParams 변환 테스트."""
    assert SortBy.HOUSEHOLDS_DESC == "households_desc"
    assert SortBy.HOUSEHOLDS_ASC == "households_asc"

    filter_desc = ListingSearchFilter(sort_by="households_desc")
    assert filter_desc.sort_by == "households_desc"
    assert filter_desc.to_dict()["sort_by"] == "households_desc"

    restored = ListingSearchFilter.from_dict(filter_desc.to_dict())
    assert restored.sort_by == "households_desc"

    filter_asc = ListingSearchFilter(sort_by="households_asc")
    assert filter_asc.sort_by == "households_asc"
