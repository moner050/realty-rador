"""다중 지역 선택 및 강남역 통근시간 퀵 필터 테스트."""
from __future__ import annotations

import pytest
from realty_radar.domain.listing.commute_map import get_sigungu_codes_within_commute, GANGNAM_COMMUTE_MINUTES_MAP
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.web.routes.home import parse_search_filter


def test_commute_map_gangnam():
    """강남역 통근 룩업 맵 60분/90분 반환 테스트."""
    codes_60 = get_sigungu_codes_within_commute(60, "gangnam")
    codes_90 = get_sigungu_codes_within_commute(90, "gangnam")

    # 강남구(11680), 서초구(11650), 마포구(11440), 분당구(41135), 과천시(41290), 구리시(41310)는 60분 이내에 포함되어야 함
    assert 11680 in codes_60
    assert 11650 in codes_60
    assert 11440 in codes_60
    assert 41135 in codes_60
    assert 41290 in codes_60
    assert 41310 in codes_60

    # 일산동구(41285), 남양주시(41360), 화성시(41590)는 1시간 40분 소요 등 외곽 이슈로 60분 이내에서 제외되어야 함
    assert 41285 not in codes_60
    assert 41360 not in codes_60
    assert 41590 not in codes_60

    # 90분 이내에는 일산동구(41285), 남양주시(41360), 파주시(41480), 인천 부평구(28237) 등이 정상 포함되어야 함
    assert 41285 in codes_90
    assert 41360 in codes_90
    assert 41480 in codes_90
    assert 28237 in codes_90

    # 90분 이내는 60분 이내를 모두 포함해야 함
    assert len(codes_90) > len(codes_60)
    assert set(codes_60).issubset(set(codes_90))


def test_listing_search_filter_multiple_regions():
    """ListingSearchFilter 시도 및 시군구 다중 파싱 테스트."""
    filter_obj = ListingSearchFilter(
        sido_codes=[11, 41],
        sigungu_codes=[11680, 11650, 41135],
        max_commute_gangnam=60,
    )

    assert filter_obj.sido_codes == [11, 41]
    assert filter_obj.sigungu_codes == [11650, 11680, 41135]
    assert filter_obj.max_commute_gangnam == 60


def test_parse_search_filter_commute_clean_separation():
    """home.py의 parse_search_filter에서 max_commute_gangnam 설정 시 sigungu_codes 오염 없이 깔끔히 분리 유지되는지 테스트."""
    parsed = parse_search_filter(
        sigungu_codes=["11680"],
        max_commute_gangnam="60",
    )

    # UI 칩 폭발 방지: 사용자가 명시한 11680만 sigungu_codes에 깔끔히 유지되고, 수십 개 코드로 오염되지 않음
    assert parsed.sigungu_codes == [11680]
    assert parsed.max_commute_gangnam == 60


def test_parse_search_filter_commute_only():
    """sigungu_codes 지정 없이 max_commute_gangnam만 지정했을 때 파싱 테스트."""
    parsed = parse_search_filter(
        max_commute_gangnam="60",
    )

    assert parsed.sigungu_codes is None
    assert parsed.max_commute_gangnam == 60


def test_parse_search_filter_sido_codes_only():
    """시/도 전체 선택(sido_codes)만 있을 때 정상 파싱 테스트."""
    parsed = parse_search_filter(
        sido_codes=["11"],
    )

    assert parsed.sido_codes == [11]
    assert parsed.sigungu_codes is None


def test_parse_search_filter_sido_and_sigungu_combined():
    """시/도 전체(sido_codes) + 개별 시군구(sigungu_codes) 복합 파싱 테스트."""
    parsed = parse_search_filter(
        sido_codes=["11"],
        sigungu_codes=["41135"],
    )

    # 서울 전체 + 분당구 개별 선택
    assert parsed.sido_codes == [11]
    assert parsed.sigungu_codes is not None
    assert 41135 in parsed.sigungu_codes


def test_listing_search_filter_sido_codes_only_no_sigungu():
    """ListingSearchFilter sido_codes만 설정 시 sigungu_codes 없이 동작 확인."""
    filter_obj = ListingSearchFilter(
        sido_codes=[11, 28],
    )

    assert filter_obj.sido_codes == [11, 28]
    assert filter_obj.sigungu_codes is None


def test_listing_search_filter_sido_and_sigungu_coexist():
    """ListingSearchFilter sido_codes와 sigungu_codes 동시 존재 시 둘 다 유지."""
    filter_obj = ListingSearchFilter(
        sido_codes=[11],
        sigungu_codes=[41135, 41131],
    )

    assert filter_obj.sido_codes == [11]
    assert filter_obj.sigungu_codes == [41131, 41135]
