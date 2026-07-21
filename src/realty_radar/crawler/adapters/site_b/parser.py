from datetime import datetime
from selectolax.parser import HTMLParser

from realty_radar.crawler.base.exceptions import ParseException
from realty_radar.crawler.base.models import RawListing


class SiteBParser:
    """사이트 B HTML 파싱 전문 클래스."""

    SOURCE_CODE = "SITE_B"

    def parse_listing_cards(self, html_content: str, base_url: str = "https://site-b.com") -> list[RawListing]:
        """SITE_B 검색 결과 HTML 페이지에서 매물 카드 목록 추출."""
        raw_listings: list[RawListing] = []

        try:
            tree = HTMLParser(html_content)
            card_nodes = tree.css(".realty-item, .property-card, div.item")

            for node in card_nodes:
                listing_id = node.attributes.get("data-item-id") or node.attributes.get("id")
                if not listing_id:
                    continue

                link_node = node.css_first("a")
                source_url = base_url
                if link_node and link_node.attributes.get("href"):
                    href = link_node.attributes["href"]
                    source_url = href if href.startswith("http") else f"{base_url}{href}"

                complex_node = node.css_first(".name, .apt-name")
                price_node = node.css_first(".price-tag, .money")
                area_node = node.css_first(".size-info, .area-spec")
                floor_node = node.css_first(".floor-info, .floor-spec")
                address_node = node.css_first(".loc, .address-text")
                desc_node = node.css_first(".memo, .desc")

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
            raise ParseException(f"Site B 매물 카드 파싱 중 오류가 발생했습니다: {e}") from e

        return raw_listings
