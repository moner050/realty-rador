from datetime import datetime
from selectolax.parser import HTMLParser

from realty_radar.crawler.base.exceptions import ParseException
from realty_radar.crawler.base.models import RawListing


class SiteAParser:
    """사이트 A HTML 파싱 전문 클래스."""

    SOURCE_CODE = "SITE_A"

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
