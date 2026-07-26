"""SITE_A article JSON을 저장 전용 정수 코드로 정규화한다."""
from __future__ import annotations

import re
from dataclasses import dataclass

from realty_radar.application.listing_batch_writer import IncomingListing


TRADE_TYPE_CODES = {"A1": 1, "B1": 2, "B2": 3, "B3": 4}
DIRECTION_CODES = {
    "남": 1,
    "남동": 2,
    "동": 3,
    "북동": 4,
    "북": 5,
    "북서": 6,
    "서": 7,
    "남서": 8,
}


@dataclass(frozen=True, slots=True)
class SiteAComplexData:
    complex_id: int
    region_code: int
    name: str
    normalized_name: str
    address: str
    construction_year: int = 0
    household_count: int = 0


def normalize_complex_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()


def parse_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def parse_area_x100(value: object) -> int:
    if value is None:
        return 0
    text = str(value).replace(",", "").strip()
    try:
        return max(0, round(float(text) * 100))
    except ValueError:
        return 0


def parse_nullable_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    return None


def parse_korean_money(value: object) -> int:
    """SITE_A의 억/만 단위 가격을 원 단위 unsigned integer로 바꾼다."""
    if value is None:
        return 0
    raw = str(value).replace(",", "").replace("원", "").strip()
    if not raw:
        return 0
    if raw.isdigit():
        number = int(raw)
        return number if number >= 1_000_000 else number * 10_000

    result = 0
    eok = re.search(r"(\d+(?:\.\d+)?)\s*억", raw)
    if eok:
        result += round(float(eok.group(1)) * 100_000_000)
        remainder = raw[eok.end() :].strip()
        remainder_match = re.search(r"(\d+(?:\.\d+)?)", remainder)
        if remainder_match:
            result += round(float(remainder_match.group(1)) * 10_000)
        return result

    man = re.search(r"(\d+(?:\.\d+)?)\s*만?", raw)
    return round(float(man.group(1)) * 10_000) if man else 0


def parse_floor(value: object) -> tuple[int | None, int | None, int, bool]:
    raw = "" if value is None else str(value).strip()
    numbers = [int(item) for item in re.findall(r"-?\d+", raw)]
    floor_no = numbers[0] if numbers else None
    total_floor = numbers[1] if len(numbers) >= 2 and numbers[1] > 0 else None
    if "지하" in raw or raw.upper().startswith("B") or (floor_no is not None and floor_no < 0):
        band = 5
    elif "저" in raw:
        band = 1
    elif "중" in raw:
        band = 2
    elif "고" in raw:
        band = 3
    elif floor_no is None or total_floor is None:
        band = 0
    elif floor_no == total_floor:
        band = 4
    elif floor_no * 3 <= total_floor:
        band = 1
    elif floor_no * 3 >= total_floor * 2:
        band = 3
    else:
        band = 2
    return floor_no, total_floor, band, floor_no is not None and floor_no == total_floor


def parse_direction_code(value: object) -> int:
    raw = "" if value is None else str(value).replace("향", "").replace(" ", "")
    for direction in sorted(DIRECTION_CODES, key=len, reverse=True):
        if direction in raw:
            return DIRECTION_CODES[direction]
    return 0


class SiteAArticleParser:
    """articleNo/complexNo/cortarNo를 권위 키로 요구하는 strict parser."""

    def parse(self, article: dict, complex_data: SiteAComplexData) -> IncomingListing | None:
        article_id = parse_positive_int(article.get("articleNo"))
        if article_id is None:
            return None

        article_complex_id = parse_positive_int(article.get("complexNo"))
        if article_complex_id is not None and article_complex_id != complex_data.complex_id:
            return None
        article_region_code = parse_positive_int(article.get("cortarNo"))
        if article_region_code is not None and article_region_code != complex_data.region_code:
            return None

        trade_key = str(article.get("tradeTypeCode") or article.get("tradeTypeCd") or "").upper()
        trade_type = TRADE_TYPE_CODES.get(trade_key)
        if trade_type is None:
            trade_name = str(article.get("tradeTypeName") or "")
            trade_type = 1 if trade_name == "매매" else 2 if trade_name == "전세" else 3 if trade_name == "월세" else 4 if trade_name == "단기임대" else None
        if trade_type is None:
            return None

        floor_no, total_floor, floor_band, is_top_floor = parse_floor(article.get("floorInfo"))
        description = str(article.get("articleFeatureDesc") or "").strip() or None
        building_name = str(article.get("buildingName") or "").strip() or None
        direction = article.get("direction") or article.get("directionInfo") or article.get("directionStandard")

        return IncomingListing(
            article_id=article_id,
            complex_id=complex_data.complex_id,
            region_code=complex_data.region_code,
            complex_name=complex_data.name,
            normalized_complex_name=complex_data.normalized_name,
            address=complex_data.address,
            construction_year=complex_data.construction_year,
            household_count=complex_data.household_count,
            trade_type=trade_type,
            primary_price=parse_korean_money(article.get("dealOrWarrantPrc")),
            monthly_rent=parse_korean_money(article.get("rentPrc")),
            supply_area_x100=parse_area_x100(article.get("area1")),
            exclusive_area_x100=parse_area_x100(article.get("area2")),
            floor_no=floor_no,
            total_floor=total_floor,
            floor_band=floor_band,
            direction_code=parse_direction_code(direction),
            mortgage_code=0,
            is_top_floor=is_top_floor,
            is_short_term=trade_type == 4,
            is_direct_trade=parse_nullable_bool(article.get("isDirectTrade")),
            is_safe_lessor_hug=parse_nullable_bool(article.get("isSafeLessorOfHug")),
            building_name=building_name[:40] if building_name else None,
            description=description[:1000] if description else None,
        )
