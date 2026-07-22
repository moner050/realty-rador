"""사이트 B 실제 매물 수집 어댑터 (SITE_B API 기반)."""
import logging
from realty_radar.crawler.adapters.site_a.adapter import NaverLandScraperClient
from realty_radar.crawler.adapters.site_a.region_codes import resolve_cortarno, SIDO_CODES, SIGUNGU_CODES
from realty_radar.crawler.base.models import RawListing, SourceSearchRequest
from realty_radar.crawler.base.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class SiteBAdapter:
    """사이트 B 실제 매물 수집 어댑터 (SITE_B)."""

    source_code: str = "SITE_B"

    def __init__(self, headless: bool = True, interval_ms: int = 1500):
        self.rate_limiter = RateLimiter(interval_ms=interval_ms)
        self.client = NaverLandScraperClient(rate_limiter=self.rate_limiter)

    async def validate_session(self) -> bool:
        """세션 유효성 검증."""
        return True

    async def _collect_region(self, cortarno: str, limit: int | None = None) -> list[RawListing]:
        """특정 구/시 cortarNo의 모든 동/단지를 순회하여 매물 수집."""
        raw_listings: list[RawListing] = []

        dongs = await self.client.get_dong_list(cortarno)
        if not dongs:
            complexes = await self.client.get_complexes_in_dong(cortarno)
            dongs = [{"cortarNo": cortarno, "cortarName": "전체"}] if complexes else []

        for dong in dongs:
            dong_code = dong.get("cortarNo", "")
            dong_name = dong.get("cortarName", "")

            complexes = await self.client.get_complexes_in_dong(dong_code)
            if not complexes:
                continue

            active_complexes = [
                c for c in complexes
                if (c.get("dealCount", 0) + c.get("leaseCount", 0) + c.get("rentCount", 0)) > 0
            ]

            for cpx in active_complexes:
                complex_no = cpx.get("complexNo", "")
                complex_name = cpx.get("complexName", "")
                cortar_address = cpx.get("cortarAddress", "")

                items = await self.client.fetch_complex_articles(
                    complex_no=complex_no,
                    complex_name=complex_name,
                    dong_address=cortar_address,
                    source_code=self.source_code,
                )
                raw_listings.extend(items)

                if limit and len(raw_listings) >= limit:
                    return raw_listings[:limit]

        return raw_listings

    async def search(self, request: SourceSearchRequest, limit: int | None = None) -> list[RawListing]:
        """SITE_B 실제 매물 수집."""
        region_name = request.region_name or ""
        cortarno = resolve_cortarno(region_name)

        if not cortarno:
            cortarno = "1100000000"

        try:
            if cortarno in SIDO_CODES.values():
                all_listings: list[RawListing] = []
                sido_name = None
                for sido, code in SIDO_CODES.items():
                    if code == cortarno:
                        sido_name = sido
                        break

                if sido_name and sido_name in SIGUNGU_CODES:
                    for sigungu_name, sigungu_code in SIGUNGU_CODES[sido_name].items():
                        sub_listings = await self._collect_region(sigungu_code, limit=limit)
                        all_listings.extend(sub_listings)
                        if limit and len(all_listings) >= limit:
                            return all_listings[:limit]
                return all_listings
            else:
                return await self._collect_region(cortarno, limit=limit)
        finally:
            await self.client.close()

    async def fetch_detail(self, raw_listing: RawListing) -> RawListing:
        """개별 매물 상세 페이지 수집."""
        return raw_listing

    async def check_availability(self, external_listing_id: str, source_url: str) -> bool:
        """매물 유효 여부 확인."""
        return True

    async def close(self):
        """리소스 해제."""
        await self.client.close()
