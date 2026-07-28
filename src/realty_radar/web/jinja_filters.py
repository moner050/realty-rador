import json
from decimal import Decimal
from typing import Any


def korean_tx_type(val: Any) -> str:
    """거래 유형 영문 코드(SALE, JEONSE, MONTHLY_RENT)를 한글로 변환."""
    if not val:
        return "미정"
    str_val = val.value if hasattr(val, "value") else str(val)
    mapping = {
        "SALE": "매매",
        "JEONSE": "전세",
        "MONTHLY_RENT": "월세",
        "MONTHLY": "월세",
    }
    return mapping.get(str_val.upper(), str_val)


def korean_mortgage(val: Any) -> str:
    """융자 상태 영문 코드를 한글 명칭으로 변환."""
    if not val:
        return "확인 불가"
    str_val = val.value if hasattr(val, "value") else str(val)
    mapping = {
        "EXPLICIT_NONE": "융자금 없음 명시",
        "EXPLICIT_EXISTS": "융자금 있음",
        "UNKNOWN": "확인 불가",
    }
    return mapping.get(str_val.upper(), str_val)


def korean_status(val: Any) -> str:
    """매물 및 작업 상태 영문 코드를 한글로 변환."""
    if not val:
        return "-"
    str_val = val.value if hasattr(val, "value") else str(val)
    mapping = {
        "ACTIVE": "매물 진행 중",
        "STALE": "미발견 매물",
        "REMOVED": "삭제된 매물",
        "SOLD_OR_CONTRACTED": "거래 완료",
        "PENDING": "대기 중",
        "RUNNING": "수집 진행 중",
        "SUCCESS": "수집 완료",
        "FAILED": "실패",
        "RETRY_WAIT": "재시도 대기",
    }
    return mapping.get(str_val.upper(), str_val)


def korean_source(val: Any) -> str:
    """SITE_A 수집 출처의 한글 표시명을 반환한다."""
    if not val:
        return "기타 출처"
    str_val = val.value if hasattr(val, "value") else str(val)
    mapping = {
        "SITE_A": "네이버부동산",
    }
    return mapping.get(str_val.upper(), str_val)


def korean_price(price_val: Any) -> str:
    """원화 수치를 억/천만 단위 한글 금액표현으로 변환."""
    if price_val is None or price_val == "":
        return "가격 미정"
    try:
        val = int(Decimal(str(price_val)))
    except (ValueError, TypeError):
        return str(price_val)

    if val <= 0:
        return "0원"

    eok = val // 100_000_000
    remainder = val % 100_000_000
    man = remainder // 10_000

    parts = []
    if eok > 0:
        parts.append(f"{eok}억")
    if man > 0:
        parts.append(f"{man:,}만")

    if not parts:
        return f"{val:,}원"

    return " ".join(parts) + " 원"


# korean_money 별칭
korean_money = korean_price


def comma_number(val: Any) -> str:
    """숫자 또는 금액 수치에 천 단위 콤마(,) 추가."""
    if val is None or val == "":
        return "0"
    try:
        num = int(Decimal(str(val)))
        return f"{num:,}"
    except (ValueError, TypeError):
        return str(val)


def to_pyeong(area_val: Any) -> str:
    """㎡ 면적 수치를 평수(1㎡ = 0.3025평)로 계산하여 변환 (예: 84.67 -> 약 25.6평)."""
    if area_val is None or area_val == "":
        return "-"
    try:
        val = float(str(area_val))
        pyeong = round(val * 0.3025, 1)
        if pyeong.is_integer():
            return f"약 {int(pyeong)}평"
        return f"약 {pyeong}평"
    except (ValueError, TypeError):
        return "-"


def tojson_filter(val: Any) -> str:
    """객체/리스트/딕셔너리를 안전한 JSON 문자열로 직렬화."""
    if val is None:
        return "[]"
    try:
        return json.dumps(val, ensure_ascii=False)
    except Exception:
        return "[]"


def register_jinja_filters(templates: Any) -> None:
    """Jinja2Templates 객체에 한글 변환, 평수 변환 커스텀 필터 일괄 등록."""
    templates.env.filters["korean_tx_type"] = korean_tx_type
    templates.env.filters["korean_mortgage"] = korean_mortgage
    templates.env.filters["korean_status"] = korean_status
    templates.env.filters["korean_source"] = korean_source
    templates.env.filters["korean_price"] = korean_price
    templates.env.filters["korean_money"] = korean_money
    templates.env.filters["comma_number"] = comma_number
    templates.env.filters["to_pyeong"] = to_pyeong
    templates.env.filters["tojson"] = tojson_filter
