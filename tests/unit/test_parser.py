from realty_radar.crawler.adapters.site_a.parser import SiteAParser

HTML_FIXTURE = """
<div class="container">
    <div class="listing-card" data-id="ITEM-101">
        <a class="card-link" href="/item/101">여의도 시범아파트</a>
        <div class="title">여의도 시범아파트 1동</div>
        <div class="price">매매 6억 5,000</div>
        <div class="area">공급 110㎡ / 전용 84.97㎡</div>
        <div class="floor">중/15층</div>
        <div class="address">서울특별시 영등포구 여의도동</div>
        <div class="description">융자없음, 로얄층 올수리 남향 매물</div>
    </div>
    <div class="listing-card" data-id="ITEM-102">
        <a class="card-link" href="/item/102">여의도 광장아파트</a>
        <div class="title">여의도 광장아파트 3동</div>
        <div class="price">전세 4억 2,000</div>
        <div class="area">전용 59.9㎡</div>
        <div class="floor">7/12층</div>
        <div class="address">서울특별시 영등포구 여의도동</div>
        <div class="description">근저당 2억 설정, 채권최고액 있음</div>
    </div>
</div>
"""


def test_site_a_parser_listing_cards():
    """SiteAParser HTML 매물 카드 추출 단위 테스트."""
    parser = SiteAParser()
    items = parser.parse_listing_cards(HTML_FIXTURE)

    assert len(items) == 2

    first = items[0]
    assert first.external_listing_id == "ITEM-101"
    assert first.complex_name_raw == "여의도 시범아파트 1동"
    assert first.price_raw == "매매 6억 5,000"
    assert first.description_raw == "융자없음, 로얄층 올수리 남향 매물"

    second = items[1]
    assert second.external_listing_id == "ITEM-102"
    assert second.price_raw == "전세 4억 2,000"
