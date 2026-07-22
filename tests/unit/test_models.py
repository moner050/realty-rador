from datetime import datetime
from realty_radar.infrastructure.database.models import (
    ApartmentComplex,
    CrawlSource,
    Listing,
)


def test_model_instantiation():
    """ORM 모델 객체 인스턴스화 테스트."""
    source = CrawlSource(
        code="SITE_A",
        name="부동산 사이트 A",
        base_url="https://site-a.com",
        adapter_name="site_a_adapter",
    )
    assert source.code == "SITE_A"

    complex_item = ApartmentComplex(
        official_name="여의도 시범아파트",
        normalized_name="여의도시범아파트",
        sido_name="서울특별시",
        sigungu_name="영등포구",
        legal_dong_name="여의도동",
    )
    assert complex_item.official_name == "여의도 시범아파트"

    listing = Listing(
        source_id=1,
        external_listing_id="L12345",
        source_url="https://site-a.com/item/12345",
        transaction_type="SALE",
        sale_price=650000000,
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )
    assert listing.external_listing_id == "L12345"
    assert listing.sale_price == 650000000


def test_search_result_pagination():
    """SearchResult 페이징 프로퍼티(total_pages, has_prev, has_next) 계산 검증."""
    from realty_radar.domain.listing.models import SearchResult

    res = SearchResult(items=["item1", "item2"], total_count=45, page=2, page_size=20)
    assert res.total_pages == 3
    assert res.has_prev is True
    assert res.has_next is True

    res_last = SearchResult(items=["item3"], total_count=45, page=3, page_size=20)
    assert res_last.total_pages == 3
    assert res_last.has_prev is True
    assert res_last.has_next is False
