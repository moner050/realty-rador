from sqlalchemy.orm import Session

from realty_radar.application.complex_match_service import ComplexMatchService
from realty_radar.application.listing_dedup_service import ListingDedupService
from realty_radar.application.listing_upsert_service import ListingUpsertService
from realty_radar.crawler.adapters.site_a.normalizer import SiteANormalizer
from realty_radar.crawler.adapters.site_b.normalizer import SiteBNormalizer
from realty_radar.crawler.base.models import SourceSearchRequest
from realty_radar.crawler.factory import AdapterFactory


class CrawlPipelineService:
    """크롤링 실행, 정규화, 단지 매칭, DB 저장 및 중복 추정 통합 파이프라인 서비스."""

    def __init__(self, db: Session):
        self.db = db
        self.upsert_service = ListingUpsertService(db)
        self.complex_service = ComplexMatchService(db)
        self.dedup_service = ListingDedupService(db)

    def _get_normalizer(self, source_code: str):
        """소스 코드별 Normalizer 인스턴스 반환."""
        if source_code.upper() == "SITE_B":
            return SiteBNormalizer()
        return SiteANormalizer()

    async def execute_search_pipeline(self, source_code: str, region_name: str) -> dict:
        """검색 파이프라인 실행: 수집 -> 파싱 -> 정규화 -> 단지 매칭 -> DB 저장 -> 동일 매물 추정."""
        adapter = AdapterFactory.get_adapter(source_code)
        normalizer = self._get_normalizer(source_code)

        search_request = SourceSearchRequest(
            source_code=source_code,
            region_name=region_name,
        )

        # 1. Fetch & Parse (RawListings 수집)
        raw_listings = await adapter.search(search_request)

        created_count = 0
        updated_count = 0
        dedup_found_count = 0

        for raw_item in raw_listings:
            # 2. Normalize
            normalized = normalizer.normalize(raw_item)

            # 3. Persist (DB Upsert)
            listing, is_created = self.upsert_service.upsert_listing(normalized)
            if is_created:
                created_count += 1
            else:
                updated_count += 1

            # 4. Complex Match
            self.complex_service.match_listing_complex(listing.id)

            # 5. 동일 매물 추정
            duplicates = self.dedup_service.find_duplicates_for_listing(listing.id)
            if duplicates:
                dedup_found_count += len(duplicates)

        return {
            "source_code": source_code,
            "region_name": region_name,
            "total_fetched": len(raw_listings),
            "created_count": created_count,
            "updated_count": updated_count,
            "dedup_found_count": dedup_found_count,
        }
