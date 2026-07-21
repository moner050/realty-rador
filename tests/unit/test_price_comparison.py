from realty_radar.domain.analytics.price_comparison import PriceComparisonEngine


def test_price_comparison_bargain_detection():
    """실거래 대비 5% 이상 저렴한 매물 급매(is_bargain) 판정 단위 테스트."""
    engine = PriceComparisonEngine()
    trade_prices = [1_000_000_000, 1_000_000_000]  # 평균 10억

    # 매물가 9.3억 (7% 저렴) -> is_bargain True
    res_bargain = engine.compare_price(930_000_000, trade_prices)
    assert res_bargain is not None
    assert res_bargain.discount_percentage == 7.0
    assert res_bargain.is_bargain is True

    # 매물가 9.8억 (2% 저렴) -> is_bargain False
    res_normal = engine.compare_price(980_000_000, trade_prices)
    assert res_normal is not None
    assert res_normal.discount_percentage == 2.0
    assert res_normal.is_bargain is False
