from realty_radar.crawler.adapters.site_b.parser import SiteBParser
from realty_radar.crawler.factory import AdapterFactory

SITE_B_HTML = """
<div class="container">
    <div class="realty-item" data-item-id="SITEB-101">
        <a href="/property/101">여의도 시범아파트 2동</a>
        <div class="name">여의도 시범아파트 2동</div>
        <div class="price-tag">매매 6억 5,000</div>
        <div class="size-info">공급 110㎡ / 전용 84.97㎡</div>
        <div class="floor-info">중/15층</div>
        <div class="loc">서울특별시 영등포구 여의도동</div>
        <div class="memo">융자없음 깨끗한 로얄층</div>
    </div>
</div>
"""


def test_site_b_parser():
    """SiteBParser 매물 카드 추출 테스트."""
    parser = SiteBParser()
    items = parser.parse_listing_cards(SITE_B_HTML)

    assert len(items) == 1
    assert items[0].external_listing_id == "SITEB-101"
    assert items[0].price_raw == "매매 6억 5,000"


def test_adapter_factory():
    """AdapterFactory 어댑터 생성 테스트."""
    adapter_a = AdapterFactory.get_adapter("SITE_A")
    assert adapter_a.source_code == "SITE_A"

    adapter_b = AdapterFactory.get_adapter("SITE_B")
    assert adapter_b.source_code == "SITE_B"
