"""SITE_A crawl job 등록용 CLI helper."""
from datetime import datetime, timezone

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.infrastructure.database.session import SessionFactory


def enqueue_crawl(scope_code: int) -> int:
    with SessionFactory() as db:
        job = CrawlJobService(db).create_job(
            scope_level=3,
            scope_code=scope_code,
            dedupe_key=f"cli:{scope_code}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            priority=50,
        )
        return job.job_id
