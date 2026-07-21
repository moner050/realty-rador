from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PriceComparisonResult:
    """실거래가 대비 매물 가격 비교 분석 DTO."""

    listing_price: int
    average_trade_price: int
    price_difference: int  # 차액 (매물가 - 평균실거래가, 음수면 저렴)
    discount_percentage: float  # 할인율 (%, 양수면 저렴, 음수면 고가)
    is_bargain: bool  # 실거래 대비 5% 이상 저렴할 시 급매/저렴 매물 판정


class PriceComparisonEngine:
    """수집 매물가와 실거래 평균가 비교 분석 엔진."""

    @staticmethod
    def compare_price(listing_price: int | None, trade_prices: list[int]) -> PriceComparisonResult | None:
        """매물 가격과 최근 실거래가 목록을 비교분석."""
        if not listing_price or not trade_prices:
            return None

        avg_price = sum(trade_prices) // len(trade_prices)
        diff = listing_price - avg_price
        discount_pct = round(((avg_price - listing_price) / avg_price) * 100.0, 2)

        is_bargain = discount_pct >= 5.0

        return PriceComparisonResult(
            listing_price=listing_price,
            average_trade_price=avg_price,
            price_difference=diff,
            discount_percentage=discount_pct,
            is_bargain=is_bargain,
        )
