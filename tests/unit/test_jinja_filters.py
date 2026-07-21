from realty_radar.web.jinja_filters import (
    korean_mortgage,
    korean_price,
    korean_source,
    korean_status,
    korean_tx_type,
)


def test_korean_tx_type_filter():
    """거래 유형 영문 코드 한글 변환 필터 단위 테스트."""
    assert korean_tx_type("SALE") == "매매"
    assert korean_tx_type("JEONSE") == "전세"
    assert korean_tx_type("MONTHLY_RENT") == "월세"
    assert korean_tx_type("MONTHLY") == "월세"


def test_korean_mortgage_filter():
    """융자 상태 영문 코드 한글 변환 필터 단위 테스트."""
    assert korean_mortgage("EXPLICIT_NONE") == "융자금 없음 명시"
    assert korean_mortgage("EXPLICIT_EXISTS") == "융자금 있음"
    assert korean_mortgage("UNKNOWN") == "확인 불가"


def test_korean_source_filter():
    """출처 사이트 코드 한글 변환 필터 단위 테스트."""
    assert korean_source("SITE_A") == "네이버부동산"
    assert korean_source("SITE_B") == "아실"


def test_korean_status_filter():
    """상태 코드 한글 변환 필터 단위 테스트."""
    assert korean_status("ACTIVE") == "매물 진행 중"
    assert korean_status("PENDING") == "대기 중"
    assert korean_status("RUNNING") == "수집 진행 중"
    assert korean_status("SUCCESS") == "수집 완료"


def test_korean_price_filter():
    """원화 금액 한글 억/천만 단위 표현 필터 테스트."""
    assert korean_price(650_000_000) == "6억 5,000만 원"
    assert korean_price(1_200_000_000) == "12억 원"
    assert korean_price(50_000_000) == "5,000만 원"
    assert korean_price(None) == "가격 미정"
