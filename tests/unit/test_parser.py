from realty_radar.crawler.adapters.site_a.parser import SiteAArticleParser, SiteAComplexData


def test_site_a_parser_uses_numeric_authoritative_ids_and_normalizes_fields():
    parser = SiteAArticleParser()
    listing = parser.parse(
        {
            "articleNo": "2001",
            "complexNo": "1001",
            "cortarNo": "1150010200",
            "tradeTypeCode": "A1",
            "dealOrWarrantPrc": "6억 5,000",
            "area1": "110",
            "area2": "84.97",
            "floorInfo": "10/20",
            "direction": "남동향",
        },
        SiteAComplexData(
            complex_id=1001,
            region_code=1150010200,
            name="테스트 아파트",
            normalized_name="테스트아파트",
            address="서울특별시 강서구 테스트로 1",
        ),
    )

    assert listing is not None
    assert listing.article_id == 2001
    assert listing.primary_price == 650_000_000
    assert listing.exclusive_area_x100 == 8497
    assert listing.direction_code == 2


def test_site_a_parser_rejects_missing_or_mismatched_authoritative_ids():
    parser = SiteAArticleParser()
    complex_data = SiteAComplexData(1001, 1150010200, "테스트", "테스트", "서울")
    assert parser.parse({"articleNo": None}, complex_data) is None
    assert parser.parse({"articleNo": 1, "complexNo": 9999}, complex_data) is None
