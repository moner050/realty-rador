from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.infrastructure.database.session import SessionFactory


def schedule_regular_search_job(scope_code: int | None = None) -> None:
    """매일 06시 정각 수도권 전체 시/군/구 정기 수집 배치를 큐에 등록합니다."""
    with SessionFactory() as db:
        service = CrawlJobService(db)
        jobs = service.enqueue_metro_batch()
        print(f"[Scheduler] 수도권 전체 시/군/구 정기 수집 배치 {len(jobs)}개 job 등록 완료.")
