from datetime import datetime, timezone

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.infrastructure.database.session import SessionFactory


def schedule_regular_search_job(scope_code: int = 1100000000) -> None:
    """SITE_A 수도권 scope를 한 번 큐에 넣는다."""
    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    with SessionFactory() as db:
        CrawlJobService(db).create_job(
            scope_level=1,
            scope_code=scope_code,
            dedupe_key=f"scheduled:{scope_code}:{bucket}",
            priority=100,
        )
