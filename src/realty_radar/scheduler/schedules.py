from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.constants import CrawlJobType
from realty_radar.infrastructure.database.session import SessionFactory


def schedule_regular_search_job(source_code: str = "SITE_A", region_name: str = "여의도동") -> None:
    """주기적 정기 매물 검색 작업 등록 태스크."""
    print(f"[Scheduler Task] 정기 매물 수집 작업 생성 요청: {source_code} ({region_name})")
    with SessionFactory() as db:
        service = CrawlJobService(db)
        job = service.create_job(
            source_code=source_code,
            job_type=CrawlJobType.SEARCH,
            request_data={
                "source_code": source_code,
                "region_name": region_name,
            },
            priority=100,
        )
        print(f"[Scheduler Task] crawl_job 등록 완료 (Job ID: {job.id})")
