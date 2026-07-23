"""사이트 A HTML 및 API JSON 파싱 전문 클래스."""
import re
from datetime import datetime
from selectolax.parser import HTMLParser

from realty_radar.crawler.base.exceptions import ParseException
from realty_radar.crawler.base.models import RawListing


class SiteAParser:
    """사이트 A HTML 및 API JSON 파싱 전문 클래스."""

    SOURCE_CODE = "SITE_A"

    def parse_new_article_json(
        self,
        item: dict,
        source_code: str = "SITE_A",
        default_complex_name: str = "",
        default_address: str = "",
        total_households: int | None = None,
        construction_year: int | None = None,
    ) -> RawListing | None:
        """new.land.naver.com /api/articles/complex/ 응답 JSON 객체 → RawListing 정밀 변환."""
        if not item or not isinstance(item, dict):
            return None

        article_no = str(item.get("articleNo", ""))
        if not article_no:
            return None

        base_cpx = item.get("articleName") or default_complex_name
        dong_name = str(item.get("buildingName") or "").strip()
        if dong_name and dong_name not in base_cpx:
            dong_str = f"{dong_name}동" if not dong_name.endswith("동") else dong_name
            complex_name_full = f"{base_cpx} {dong_str}"
        else:
            complex_name_full = base_cpx

        trade_type = item.get("tradeTypeName") or ""
        price_str = item.get("dealOrWarrantPrc") or ""
        rent_prc = item.get("rentPrc")
        if trade_type == "단기임대" or item.get("tradeTypeCd") == "B3":
            if rent_prc and str(rent_prc) != "0":
                price_raw = f"단기임대 {price_str}/{rent_prc}"
            else:
                price_raw = f"단기임대 {price_str}".strip()
        elif rent_prc and str(rent_prc) != "0":
            price_raw = f"{trade_type} {price_str}/{rent_prc}"
        else:
            price_raw = f"{trade_type} {price_str}".strip()

        area1 = item.get("area1")
        area2 = item.get("area2")
        if area1 and area2:
            area_raw = f"전용 {area2}㎡ / 공급 {area1}㎡"
        elif area2:
            area_raw = f"전용 {area2}㎡"
        else:
            area_raw = None

        floor_info = item.get("floorInfo")
        floor_raw = f"{floor_info}층" if floor_info and "층" not in str(floor_info) else floor_info

        desc_raw = item.get("detailDescription") or item.get("articleFeatureDesc")

        full_addr = default_address

        # 네이버 부동산 웹페이지 원본 상세 표준 접속 URL (fin.land.naver.com 사용)
        source_url = f"https://fin.land.naver.com/articles/{article_no}"

        raw_payload = {
            "new_article_json": item,
            "tradeTypeName": trade_type,
            "dealOrWarrantPrc": price_str,
            "area1": area1,
            "area2": area2,
            "floorInfo": floor_raw,
            "total_households": total_households,
            "construction_year": construction_year,
        }

        return RawListing(
            source_code=source_code,
            external_listing_id=article_no,
            source_url=source_url,
            complex_name_raw=complex_name_full,
            address_raw=full_addr,
            price_raw=price_raw,
            area_raw=area_raw,
            floor_raw=floor_raw,
            description_raw=desc_raw,
            collected_at=datetime.now(),
            raw_payload=raw_payload,
        )

    def parse_fin_article_json(
        self,
        item: dict,
        source_code: str = "SITE_A",
        default_complex_name: str = "",
        default_address: str = "",
        total_households: int | None = None,
        construction_year: int | None = None,
    ) -> RawListing | None:
        """fin.land.naver.com front-api/v1/complex/article/list 응답 객체 → RawListing 정밀 변환."""
        if not item or not isinstance(item, dict):
            return None

        if "articleNo" in item and "articleName" in item and "dealOrWarrantPrc" in item:
            return self.parse_new_article_json(item, source_code, default_complex_name, default_address, total_households, construction_year)

        info = item.get("representativeArticleInfo") or {}
        if not info:
            info = item

        article_no = str(info.get("articleNumber", "") or info.get("articleNo", ""))
        if not article_no:
            return None

        base_cpx = info.get("complexName") or info.get("articleName") or default_complex_name
        dong_name = str(info.get("dongName") or "").strip()
        if dong_name and dong_name not in base_cpx:
            dong_str = f"{dong_name}동" if not dong_name.endswith("동") else dong_name
            complex_name_full = f"{base_cpx} {dong_str}"
        else:
            complex_name_full = base_cpx

        trade_type = info.get("tradeType", "A1")
        price_info = item.get("priceInfo") or info.get("priceInfo") or {}

        deal_price = price_info.get("dealPrice") or 0
        warranty_price = price_info.get("warrantyPrice") or 0
        rent_price = price_info.get("rentPrice") or 0

        trade_type_name = info.get("tradeTypeName") or info.get("tradeTypeTitle") or ""
        if trade_type == "B3" or trade_type_name == "단기임대":
            price_raw = f"단기임대 {warranty_price // 10000 if warranty_price >= 10000 else warranty_price}/{rent_price // 10000 if rent_price >= 10000 else rent_price}"
        elif trade_type == "B2" or (rent_price and rent_price > 0):
            price_raw = f"월세 {warranty_price // 10000 if warranty_price >= 10000 else warranty_price}/{rent_price // 10000 if rent_price >= 10000 else rent_price}"
        elif trade_type == "B1" or (warranty_price and warranty_price > 0 and not deal_price):
            price_raw = f"전세 {warranty_price}"
        else:
            price_raw = f"매매 {deal_price}"

        space_info = info.get("spaceInfo") or {}
        supply_space = space_info.get("supplySpace")
        exclusive_space = space_info.get("exclusiveSpace")
        if supply_space and exclusive_space:
            area_raw = f"공급 {supply_space}㎡ / 전용 {exclusive_space}㎡"
        elif exclusive_space:
            area_raw = f"전용 {exclusive_space}㎡"
        else:
            area_raw = None

        article_detail = info.get("articleDetail") or {}
        floor_detail = article_detail.get("floorDetailInfo") or info.get("floorDetailInfo") or {}

        floor_info = (
            article_detail.get("floorInfo")
            or info.get("floorInfo")
            or item.get("floorInfo")
        )

        if not floor_info and floor_detail:
            target_fl = floor_detail.get("targetFloor")
            total_fl = floor_detail.get("totalFloor")
            if target_fl and total_fl:
                floor_info = f"{target_fl}/{total_fl}"
            elif target_fl:
                floor_info = f"{target_fl}"

        if floor_info:
            floor_str = str(floor_info).strip()
            floor_raw = f"{floor_str}층" if "층" not in floor_str else floor_str
        else:
            floor_raw = None

        building_info = info.get("buildingInfo") or item.get("buildingInfo") or {}
        conj_date = str(building_info.get("buildingConjunctionDate") or "").strip()
        parsed_const_year = construction_year
        if conj_date and len(conj_date) >= 4 and conj_date[:4].isdigit():
            parsed_const_year = int(conj_date[:4])

        desc_text = article_detail.get("articleFeatureDescription") or ""
        direction = article_detail.get("directionStandard") or article_detail.get("direction") or ""
        desc_parts = [p for p in [desc_text, direction] if p]
        description_raw = ", ".join(desc_parts) if desc_parts else None

        verification_info = info.get("verificationInfo") or {}
        confirm_date_str = verification_info.get("articleConfirmDate") or ""
        try:
            collected_at = datetime.strptime(confirm_date_str, "%Y-%m-%d") if confirm_date_str else datetime.now()
        except ValueError:
            collected_at = datetime.now()

        addr_info = item.get("address") or {}
        city = addr_info.get("city", "")
        division = addr_info.get("division", "")
        sector = addr_info.get("sector", "")
        full_addr = f"{city} {division} {sector}".strip() or default_address

        source_url = f"https://fin.land.naver.com/articles/{article_no}"

        raw_payload = {
            "fin_article_json": item,
            "tradeType": trade_type,
            "dealPrice": deal_price,
            "warrantyPrice": warranty_price,
            "rentPrice": rent_price,
            "supplySpace": supply_space,
            "exclusiveSpace": exclusive_space,
            "brokerInfo": info.get("brokerInfo") or {},
            "dongName": dong_name,
            "floorInfo": floor_raw,
            "total_households": total_households,
            "construction_year": parsed_const_year,
        }

        return RawListing(
            source_code=source_code,
            external_listing_id=article_no,
            source_url=source_url,
            complex_name_raw=complex_name_full,
            address_raw=full_addr,
            price_raw=price_raw,
            area_raw=area_raw,
            floor_raw=floor_raw,
            description_raw=description_raw,
            collected_at=collected_at,
            raw_payload=raw_payload,
        )

    def parse_article_json(
        self,
        article: dict,
        source_code: str = "SITE_A",
        complex_name: str = "",
        dong_address: str = "",
        total_households: int | None = None,
        construction_year: int | None = None,
    ) -> RawListing | None:
        """이전 API 응답 파싱 별칭 메서드."""
        return self.parse_fin_article_json(article, source_code, complex_name, dong_address, total_households, construction_year)

    def parse_scraped_text(
        self,
        raw_text: str,
        source_code: str = "SITE_A",
        default_complex_name: str = "",
        default_address: str = "",
        external_listing_id: str = "",
        source_url: str = "",
    ) -> RawListing | None:
        """DOM 스크래핑 텍스트(lines) 정밀 추출 (하위 호환용)."""
        if not raw_text or not raw_text.strip():
            return None

        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        if not lines:
            return None

        complex_name = default_complex_name
        price_str = None
        area_str = None
        floor_str = None
        desc_str = None

        if lines:
            complex_name = lines[0]

        for line in lines[1:]:
            if any(k in line for k in ["매매", "전세", "월세"]):
                price_str = line
                break

        for line in lines:
            if "m²" in line or "㎡" in line or "층" in line:
                area_match = re.search(r"(\d+(?:\.\d+)?(?:\/\d+(?:\.\d+)?)?\s*(?:m²|㎡))", line)
                if area_match:
                    area_str = area_match.group(1)

                floor_match = re.search(r"((?:저|중|고|\d+)(?:\/\d+)?\s*층)", line)
                if floor_match:
                    floor_str = floor_match.group(1)

        desc_lines = []
        for line in lines[1:]:
            if price_str and line == price_str:
                continue
            if "m²" in line or "㎡" in line or "확인매물" in line or "네이버" in line:
                continue
            desc_lines.append(line)

        if desc_lines:
            desc_str = " ".join(desc_lines[:2])

        if not price_str and not area_str:
            return None

        return RawListing(
            source_code=source_code,
            external_listing_id=external_listing_id or f"{source_code}-{hash(raw_text) & 0xFFFFFFFF}",
            source_url=source_url or "https://fin.land.naver.com",
            complex_name_raw=complex_name or default_complex_name,
            address_raw=default_address,
            price_raw=price_str,
            area_raw=area_str,
            floor_raw=floor_str,
            description_raw=desc_str,
            collected_at=datetime.now(),
            raw_payload={"scraped_text": raw_text},
        )

    def parse_listing_cards(self, html_content: str, base_url: str = "https://site-a.com") -> list[RawListing]:
        """검색 결과 HTML 페이지에서 매물 카드 목록 추출."""
        raw_listings: list[RawListing] = []

        try:
            tree = HTMLParser(html_content)
            card_nodes = tree.css("div.listing-card, div.item-card, article.item")

            for node in card_nodes:
                listing_id = node.attributes.get("data-id") or node.attributes.get("id")
                if not listing_id:
                    continue

                link_node = node.css_first("a.card-link, a.item-link, a")
                source_url = base_url
                if link_node and link_node.attributes.get("href"):
                    href = link_node.attributes["href"]
                    source_url = href if href.startswith("http") else f"{base_url}{href}"

                complex_node = node.css_first(".complex-name, .title, .item-title")
                price_node = node.css_first(".price, .price-text, .item-price")
                area_node = node.css_first(".area, .spec-area, .item-area")
                floor_node = node.css_first(".floor, .spec-floor, .item-floor")
                address_node = node.css_first(".address, .item-address")
                desc_node = node.css_first(".description, .item-desc, .summary")

                raw_item = RawListing(
                    source_code=self.SOURCE_CODE,
                    external_listing_id=str(listing_id).strip(),
                    source_url=source_url,
                    complex_name_raw=complex_node.text(strip=True) if complex_node else None,
                    address_raw=address_node.text(strip=True) if address_node else None,
                    price_raw=price_node.text(strip=True) if price_node else None,
                    area_raw=area_node.text(strip=True) if area_node else None,
                    floor_raw=floor_node.text(strip=True) if floor_node else None,
                    description_raw=desc_node.text(strip=True) if desc_node else None,
                    collected_at=datetime.now(),
                    raw_payload={
                        "html_snippet": node.html,
                    },
                )
                raw_listings.append(raw_item)

        except Exception as e:
            raise ParseException(f"Site A 매물 카드 파싱 중 오류가 발생했습니다: {e}") from e

        return raw_listings

    def parse_detail_page(self, html_content: str, raw_listing: RawListing) -> RawListing:
        """매물 상세 페이지 HTML 파싱하여 raw_listing 보완."""
        try:
            tree = HTMLParser(html_content)
            full_desc_node = tree.css_first(".detail-description, .full-desc, #description")
            if full_desc_node:
                raw_listing.description_raw = full_desc_node.text(strip=True)

            mortgage_info_node = tree.css_first(".mortgage-info, .tag-mortgage, .spec-mortgage")
            if mortgage_info_node:
                raw_listing.raw_payload["mortgage_text_raw"] = mortgage_info_node.text(strip=True)

        except Exception as e:
            raise ParseException(f"Site A 상세 페이지 파싱 중 오류 발생: {e}") from e

        return raw_listing
