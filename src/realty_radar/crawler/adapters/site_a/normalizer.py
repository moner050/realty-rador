import html
import re
from decimal import Decimal

from realty_radar.constants import ListingStatus, MortgageStatus, TransactionType
from realty_radar.crawler.base.models import NormalizedListing, RawListing


class SiteANormalizer:
    """한국 부동산 데이터 특화 정규화 유틸리티 (단기임대 매물 감지 탑재)."""

    @staticmethod
    def parse_korean_money(money_str: str | None) -> int | None:
        """'6억 5,000만 원', '6억5000', '3,500' 형태의 한글 금액을 정수(원)로 변환."""
        if not money_str:
            return None

        clean_str = money_str.replace(",", "").replace("원", "").strip()

        if clean_str.isdigit():
            val = int(clean_str)
            if val >= 1_000_000:
                return val
            return val * 10_000

        total_won = 0

        eok_match = re.search(r"(\d+)\s*억", clean_str)
        if eok_match:
            total_won += int(eok_match.group(1)) * 100_000_000

        man_match = re.search(r"(?:억\s*)?(\d+)(?:\s*만)?$", clean_str)
        if man_match and not eok_match:
            total_won += int(man_match.group(1)) * 10_000
        elif man_match and eok_match:
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

        if "단기임대" in raw or "단기" in raw or "월세" in raw or "/" in raw:
            trans_type = TransactionType.MONTHLY_RENT
            clean_raw = raw.replace("단기임대", "").replace("단기", "").replace("월세", "").strip()
            parts = clean_raw.split("/")
            deposit = self.parse_korean_money(parts[0]) if len(parts) > 0 else None
            monthly_rent = self.parse_korean_money(parts[1]) if len(parts) > 1 else None
            return trans_type, None, deposit, monthly_rent

        if "전세" in raw:
            trans_type = TransactionType.JEONSE
            deposit = self.parse_korean_money(raw.replace("전세", "").strip())
            return trans_type, None, deposit, None

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

        exclusive_area = None
        supply_area = None

        exclusive_match = re.search(r"전용\s*(\d+(?:\.\d+)?)", area_raw)
        if exclusive_match:
            exclusive_area = Decimal(exclusive_match.group(1))

        supply_match = re.search(r"공급\s*(\d+(?:\.\d+)?)", area_raw)
        if supply_match:
            supply_area = Decimal(supply_match.group(1))

        if exclusive_area is None and supply_area is None:
            numbers = re.findall(r"(\d+(?:\.\d+)?)", area_raw)
            if not numbers:
                return None, None

            if len(numbers) >= 2:
                supply_area = Decimal(numbers[0])
                exclusive_area = Decimal(numbers[1])
            else:
                exclusive_area = Decimal(numbers[0])

        return exclusive_area, supply_area

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

    def evaluate_short_term_status(self, description: str | None, sale_price: int | None, trans_type: TransactionType, price_raw: str | None = None) -> bool:
        """단기임대 / 단기 깔세 / 지분 / 노이즈 매물 감지 식별."""
        text = f"{description or ''} {price_raw or ''}"

        # 1. 단기 키워드 검색
        short_term_keywords = [
            "단기", "깔세", "월세선납", "1개월", "2개월", "3개월", "6개월", "12개월", "24개월", "36개월",
            "개월 가능", "개월가능", "단기입주", "전입X", "전입x", "전입불가", "전입신고X", "무보증", "보증금없",
            "한달살기", "주세", "일세", "단기임대", "상가지분", "분양권"
        ]
        for kw in short_term_keywords:
            if kw in text:
                return True

        # 2. 매매 거래인데 보증금/매매가가 3,000만원 이하이거나 월세가 0보다 큰 경우 (단기임대/지분 매물)
        if trans_type == TransactionType.SALE and sale_price and sale_price <= 30_000_000:
            return True

        return False

    def normalize(self, raw: RawListing) -> NormalizedListing:
        """RawListing 객체를 NormalizedListing으로 종합 변환."""
        payload = raw.raw_payload or {}

        if "dealPrice" in payload or "warrantyPrice" in payload or "rentPrice" in payload:
            trade_code = payload.get("tradeType", "A1")
            deal_p = payload.get("dealPrice") or 0
            warr_p = payload.get("warrantyPrice") or 0
            rent_p = payload.get("rentPrice") or 0

            if trade_code == "B3" or payload.get("tradeTypeName") == "단기임대":
                trans_type = TransactionType.MONTHLY_RENT
                sale_price = None
                deposit = warr_p
                monthly_rent = rent_p
            elif trade_code == "B2" or (rent_p and rent_p > 0):
                trans_type = TransactionType.MONTHLY_RENT
                sale_price = None
                deposit = warr_p
                monthly_rent = rent_p
            elif trade_code == "B1" or (warr_p and warr_p > 0 and not deal_p):
                trans_type = TransactionType.JEONSE
                sale_price = None
                deposit = warr_p
                monthly_rent = None
    @staticmethod
    def parse_address_components(address_raw: str | None) -> tuple[str | None, str | None]:
        """주소 문자열에서 sido 및 sigungu 정밀 정제 추출."""
        if not address_raw:
            return None, None
        tokens = address_raw.strip().split()
        if not tokens:
            return None, None

        sido_raw = tokens[0]
        sido = None
        if "서울" in sido_raw:
            sido = "서울특별시"
        elif "경기" in sido_raw:
            sido = "경기도"
        elif "인천" in sido_raw:
            sido = "인천광역시"
        elif "부산" in sido_raw:
            sido = "부산광역시"
        elif "대구" in sido_raw:
            sido = "대구광역시"
        elif "대전" in sido_raw:
            sido = "대전광역시"
        elif "광주" in sido_raw:
            sido = "광주광역시"
        elif "울산" in sido_raw:
            sido = "울산광역시"
        elif "세종" in sido_raw:
            sido = "세종특별자치시"
        else:
            sido = sido_raw

        sigungu = None
        if len(tokens) >= 3 and (tokens[1].endswith("시") or tokens[1].endswith("구")) and tokens[2].endswith("구"):
            sigungu = f"{tokens[1]} {tokens[2]}"
        elif len(tokens) >= 2:
            sigungu = tokens[1]

        return sido, sigungu

    def normalize(self, raw: RawListing) -> NormalizedListing:
        """RawListing 객체를 NormalizedListing으로 종합 변환."""
        payload = raw.raw_payload or {}

        if "dealPrice" in payload or "warrantyPrice" in payload or "rentPrice" in payload:
            trade_code = payload.get("tradeType", "A1")
            deal_p = payload.get("dealPrice") or 0
            warr_p = payload.get("warrantyPrice") or 0
            rent_p = payload.get("rentPrice") or 0

            if trade_code == "B3" or payload.get("tradeTypeName") == "단기임대":
                trans_type = TransactionType.MONTHLY_RENT
                sale_price = None
                deposit = warr_p
                monthly_rent = rent_p
            elif trade_code == "B2" or (rent_p and rent_p > 0):
                trans_type = TransactionType.MONTHLY_RENT
                sale_price = None
                deposit = warr_p
                monthly_rent = rent_p
            elif trade_code == "B1" or (warr_p and warr_p > 0 and not deal_p):
                trans_type = TransactionType.JEONSE
                sale_price = None
                deposit = warr_p
                monthly_rent = None
            else:
                trans_type = TransactionType.SALE
                sale_price = deal_p
                deposit = None
                monthly_rent = None
        else:
            trans_type, sale_price, deposit, monthly_rent = self.normalize_price(raw.price_raw)

        if "exclusiveSpace" in payload or "supplySpace" in payload:
            exclusive_area = Decimal(str(payload.get("exclusiveSpace"))) if payload.get("exclusiveSpace") else None
            supply_area = Decimal(str(payload.get("supplySpace"))) if payload.get("supplySpace") else None
        else:
            exclusive_area, supply_area = self.normalize_area(raw.area_raw)

        floor_num, floor_grp, total_fl = self.normalize_floor(raw.floor_raw)
        mortgage_status, mortgage_text = self.evaluate_mortgage_status(raw.description_raw, payload)

        is_short_term = self.evaluate_short_term_status(raw.description_raw, sale_price or deposit, trans_type, raw.price_raw)
        payload["is_short_term"] = is_short_term

        c_name = html.unescape(raw.complex_name_raw) if raw.complex_name_raw else None
        addr_clean = html.unescape(raw.address_raw) if raw.address_raw else None
        desc_clean = html.unescape(raw.description_raw) if raw.description_raw else None

        sido, sigungu = self.parse_address_components(addr_clean)
        c_year = payload.get("construction_year") or payload.get("constructionYear")
        tot_hh = payload.get("total_households") or payload.get("totalHouseholds")
        direction_val = (payload.get("direction") or "").strip() or None

        return NormalizedListing(
            source_code=raw.source_code,
            external_listing_id=raw.external_listing_id,
            source_url=raw.source_url,
            transaction_type=trans_type,
            complex_name_raw=c_name,
            sale_price=sale_price,
            deposit=deposit,
            monthly_rent=monthly_rent,
            exclusive_area=exclusive_area,
            supply_area=supply_area,
            floor_number=floor_num,
            floor_group=floor_grp,
            total_floor=total_fl,
            floor_raw=raw.floor_raw,
            floor_info=raw.floor_raw,
            direction=direction_val,
            address_raw=addr_clean,
            sido=sido,
            sigungu=sigungu,
            construction_year=int(c_year) if c_year else None,
            total_households=int(tot_hh) if tot_hh else None,
            description=desc_clean,
            mortgage_status=mortgage_status,
            mortgage_raw_text=mortgage_text,
            is_short_term=is_short_term,
            listing_status=ListingStatus.ACTIVE,
            first_seen_at=raw.collected_at,
            last_seen_at=raw.collected_at,
            raw_payload=payload,
        )
