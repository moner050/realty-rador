import re
from decimal import Decimal

from realty_radar.constants import ListingStatus, MortgageStatus, TransactionType
from realty_radar.crawler.base.models import NormalizedListing, RawListing


class SiteANormalizer:
    """한국 부동산 데이터 특화 정규화 유틸리티."""

    @staticmethod
    def parse_korean_money(money_str: str | None) -> int | None:
        """'6억 5,000만 원', '6억5000', '3,500' 형태의 한글 금액을 정수(원)로 변환."""
        if not money_str:
            return None

        clean_str = money_str.replace(",", "").replace("원", "").strip()
        total_won = 0

        # '억' 단위 추출
        eok_match = re.search(r"(\d+)\s*억", clean_str)
        if eok_match:
            total_won += int(eok_match.group(1)) * 100_000_000

        # '억' 이후 4자리 '만' 단위 추출
        man_match = re.search(r"(?:억\s*)?(\d+)(?:\s*만)?$", clean_str)
        if man_match and not eok_match:
            # 억이 없는 경우
            total_won += int(man_match.group(1)) * 10_000
        elif man_match and eok_match:
            # 억 뒤에 남아있는 숫자 (예: 6억 5000 -> 5000만)
            rem_str = clean_str.split("억")[-1].strip()
            num_match = re.search(r"^(\d+)", rem_str)
            if num_match:
                val = int(num_match.group(1))
                if val < 10000:
                    total_won += val * 10_000
                else:
                    total_won += val

        return total_won if total_won > 0 else None

    def normalize_price(self, price_raw: str | None) -> tuple[TransactionType, int | None, int | None, int | None]:
        """거래 유형 및 가격 (매매가, 보증금, 월세) 정규화."""
        if not price_raw:
            return TransactionType.SALE, None, None, None

        raw = price_raw.strip()

        if "월세" in raw:
            trans_type = TransactionType.MONTHLY_RENT
            # '월세 1억/50' 구문 분리
            parts = raw.replace("월세", "").strip().split("/")
            deposit = self.parse_korean_money(parts[0]) if len(parts) > 0 else None
            monthly_rent = self.parse_korean_money(parts[1]) if len(parts) > 1 else None
            return trans_type, None, deposit, monthly_rent

        if "전세" in raw:
            trans_type = TransactionType.JEONSE
            deposit = self.parse_korean_money(raw.replace("전세", "").strip())
            return trans_type, None, deposit, None

        # 기본 매매
        trans_type = TransactionType.SALE
        sale_price = self.parse_korean_money(raw.replace("매매", "").strip())
        return trans_type, sale_price, None, None

    def normalize_floor(self, floor_raw: str | None) -> tuple[int | None, str | None, int | None]:
        """층 정보 정규화 (예: '중/25층', '7/25층', '고층')."""
        if not floor_raw:
            return None, None, None

        clean = floor_raw.strip()
        floor_number = None
        floor_group = None
        total_floor = None

        total_match = re.search(r"(\d+)\s*층$", clean)
        if total_match:
            total_floor = int(total_match.group(1))

        parts = clean.split("/")
        first_part = parts[0].strip()

        if first_part in ["저", "중", "고"]:
            floor_group = first_part
        elif first_part.isdigit():
            floor_number = int(first_part)
            if total_floor and total_floor > 0:
                ratio = floor_number / total_floor
                if ratio <= 0.33:
                    floor_group = "저"
                elif ratio <= 0.66:
                    floor_group = "중"
                else:
                    floor_group = "고"

        return floor_number, floor_group, total_floor

    def normalize_area(self, area_raw: str | None) -> tuple[Decimal | None, Decimal | None]:
        """면적 정규화 (전용면적, 공급면적)."""
        if not area_raw:
            return None, None

        numbers = re.findall(r"(\d+(?:\.\d+)?)", area_raw)
        if not numbers:
            return None, None

        if len(numbers) >= 2:
            supply_area = Decimal(numbers[0])
            exclusive_area = Decimal(numbers[1])
            return exclusive_area, supply_area

        exclusive_area = Decimal(numbers[0])
        return exclusive_area, None

    def evaluate_mortgage_status(self, description: str | None, raw_payload: dict) -> tuple[MortgageStatus, str | None]:
        """매물 설명 및 태그 문구 기반 융자 상태 키워드 분석."""
        text = f"{description or ''} {raw_payload.get('mortgage_text_raw', '')}"

        if not text.strip():
            return MortgageStatus.UNKNOWN, None

        none_keywords = ["융자없음", "융자 없음", "융자무", "근저당 없음", "근저당없음", "대출없음"]
        for kw in none_keywords:
            if kw in text:
                return MortgageStatus.EXPLICIT_NONE, kw

        exists_keywords = ["융자있음", "융자 있음", "근저당", "채권최고액", "융자 30%", "대출있음"]
        for kw in exists_keywords:
            if kw in text:
                return MortgageStatus.EXPLICIT_EXISTS, kw

        return MortgageStatus.UNKNOWN, None

    def normalize(self, raw: RawListing) -> NormalizedListing:
        """RawListing 객체를 NormalizedListing으로 종합 변환."""
        trans_type, sale_price, deposit, monthly_rent = self.normalize_price(raw.price_raw)
        floor_num, floor_grp, total_fl = self.normalize_floor(raw.floor_raw)
        exclusive_area, supply_area = self.normalize_area(raw.area_raw)
        mortgage_status, mortgage_text = self.evaluate_mortgage_status(raw.description_raw, raw.raw_payload)

        return NormalizedListing(
            source_code=raw.source_code,
            external_listing_id=raw.external_listing_id,
            source_url=raw.source_url,
            transaction_type=trans_type,
            complex_name_raw=raw.complex_name_raw,
            sale_price=sale_price,
            deposit=deposit,
            monthly_rent=monthly_rent,
            exclusive_area=exclusive_area,
            supply_area=supply_area,
            floor_number=floor_num,
            floor_group=floor_grp,
            total_floor=total_fl,
            address_raw=raw.address_raw,
            description=raw.description_raw,
            mortgage_status=mortgage_status,
            mortgage_raw_text=mortgage_text,
            listing_status=ListingStatus.ACTIVE,
            first_seen_at=raw.collected_at,
            last_seen_at=raw.collected_at,
            raw_payload=raw.raw_payload,
        )
