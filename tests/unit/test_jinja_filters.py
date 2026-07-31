from datetime import datetime, timezone

from realty_radar.web.jinja_filters import (
    korean_money,
    korean_mortgage,
    korean_price,
    korean_source,
    korean_status,
    korean_tx_type,
    kst_datetime,
    scheduler_duration,
    to_pyeong,
    tojson_filter,
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
    assert korean_money(650_000_000) == "6억 5,000만 원"


def test_to_pyeong_filter():
    """면적(㎡) -> 평수 환산 필터 테스트."""
    assert to_pyeong(84.67) == "약 25.6평"
    assert to_pyeong(105.80) == "약 32평"
    assert to_pyeong(None) == "-"


def test_tojson_filter():
    """tojson JSON 직렬화 커스텀 필터 테스트."""
    assert tojson_filter([{"name": "홍길동", "amount": 100}]) == '[{"name": "홍길동", "amount": 100}]'
    assert tojson_filter(None) == '[]'


def test_kst_datetime_filter():
    """kst_datetime KST 시각 변환 필터 테스트."""
    utc_dt = datetime(2026, 7, 31, 6, 0, 0, tzinfo=timezone.utc)
    # KST는 UTC+9 -> 15:00:00
    assert kst_datetime(utc_dt) == "07/31 15:00:00"
    assert kst_datetime(None) == "-"


def test_scheduler_duration_filter():
    """scheduler_duration 소요시간 계산 필터 테스트."""
    class DummyLog:
        started_at = datetime(2026, 7, 31, 6, 0, 0)
        finished_at = datetime(2026, 7, 31, 6, 2, 35)

    assert scheduler_duration(DummyLog()) == "2분 35초"
    assert scheduler_duration(None) == "-"

