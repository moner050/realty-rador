from typing import Protocol

from realty_radar.crawler.base.models import RawListing, SourceSearchRequest


class ListingSourceAdapter(Protocol):
    """크롤링 사이트 어댑터 표준 프로토콜 인터페이스."""

    source_code: str

    async def validate_session(self) -> bool:
        """현재 세션 쿠키 유효성 검증."""
        ...

    async def search(self, request: SourceSearchRequest) -> list[RawListing]:
        """검색 결과 목록 수집."""
        ...

    async def fetch_detail(self, raw_listing: RawListing) -> RawListing:
        """매물 상세 정보 수집."""
        ...

    async def check_availability(self, external_listing_id: str, source_url: str) -> bool:
        """매물 존재 여부 확인."""
        ...
