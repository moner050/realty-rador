# -*- coding: utf-8 -*-
import pytest
from realty_radar.domain.listing.filters import ListingSearchFilter

def test_single_floor_filter_parsing():
    filter_dto = ListingSearchFilter(floor="저층")
    assert filter_dto.floor == "저층"
    assert filter_dto.parsed_floors == ["저층"]

    dict_data = filter_dto.to_dict()
    assert dict_data["floor"] == "저층"

    restored = ListingSearchFilter.from_dict(dict_data)
    assert restored.floor == "저층"
    assert restored.parsed_floors == ["저층"]

def test_multi_floor_filter_parsing():
    filter_dto1 = ListingSearchFilter(floor="저층,중층,탑층")
    assert set(filter_dto1.parsed_floors) == {"저층", "중층", "탑층"}

def test_exclude_first_floor_filter_parsing():
    filter_dto = ListingSearchFilter(exclude_first_floor=True)
    assert filter_dto.exclude_first_floor is True

    dict_data = filter_dto.to_dict()
    assert dict_data["exclude_first_floor"] is True

    restored = ListingSearchFilter.from_dict(dict_data)
    assert restored.exclude_first_floor is True

    filter_dto2 = ListingSearchFilter(floors=["1층제외", "고층"])
    assert "1층제외" in filter_dto2.parsed_floors
