from decimal import Decimal
from realty_radar.domain.complex.matching import ComplexMatchEngine, normalize_complex_name


def test_normalize_complex_name():
    """단지명 정규화 함수 단위 테스트."""
    assert normalize_complex_name("여의도 시범 (아파트)") == "여의도 시범"
    assert normalize_complex_name("여의도 시범아파트 1동") == "여의도 시범아파트"
    assert normalize_complex_name("삼풍 2차 단지") == "삼풍"


def test_complex_match_engine_calculation():
    """단지 매칭 점수 산출 단위 테스트."""
    engine = ComplexMatchEngine()

    candidates = [
        {"id": 1, "official_name": "여의도 시범아파트", "normalized_name": "여의도 시범아파트", "road_address": "서울 영등포구 여의도동 1"},
        {"id": 2, "official_name": "여의도 광장아파트", "normalized_name": "여의도 광장아파트", "road_address": "서울 영등포구 여의도동 2"},
    ]

    # 주소 일치 (+99.99점)
    result_address = engine.evaluate_candidates("여의도 시범아파트 1동", "서울 영등포구 여의도동 1", candidates)
    assert result_address.complex_id == 1
    assert result_address.match_score == Decimal("99.99")
    assert result_address.requires_manual_review is False

    # 이름 완전 일치 (+95점)
    result_name = engine.evaluate_candidates("여의도 시범아파트 1동", None, candidates)
    assert result_name.complex_id == 1
    assert result_name.match_score == Decimal("95.00")
