# -*- coding: utf-8 -*-
import pytest
from realty_radar.domain.listing.filters import ListingSearchFilter

def test_direction_filter_dto_parsing():
    # 단일 방향 테스트
    filter_dto = ListingSearchFilter(direction="남향")
    assert filter_dto.direction == "남향"
    assert filter_dto.parsed_directions == ["남향"]

    dict_data = filter_dto.to_dict()
    assert dict_data["direction"] == "남향"

    restored = ListingSearchFilter.from_dict(dict_data)
    assert restored.direction == "남향"
    assert restored.parsed_directions == ["남향"]

def test_multi_direction_filter_parsing():
    # 다중 방향 콤마 구분자 및 리스트 테스트
    filter_dto1 = ListingSearchFilter(direction="남향,남동향,동향")
    assert set(filter_dto1.parsed_directions) == {"남향", "남동향", "동향"}

    filter_dto2 = ListingSearchFilter(directions=["남향", "서향"])
    assert set(filter_dto2.parsed_directions) == {"남향", "서향"}

    dict_data = filter_dto2.to_dict()
    assert dict_data["directions"] == ["남향", "서향"]

    restored = ListingSearchFilter.from_dict(dict_data)
    assert set(restored.parsed_directions) == {"남향", "서향"}
