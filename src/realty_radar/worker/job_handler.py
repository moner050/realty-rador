from sqlalchemy.orm import Session

from realty_radar.application.crawl_pipeline_service import CrawlPipelineService
from realty_radar.crawler.adapters.site_a.adapter import SiteAAdapter
from realty_radar.infrastructure.database.models import CrawlJob


class JobHandler:
    """SITE_A crawl job 하나를 v2 pipeline으로 실행한다."""

    def __init__(self, db: Session, adapter: SiteAAdapter):
        self._pipeline = CrawlPipelineService(db, adapter=adapter)

    async def handle_job(self, job: CrawlJob) -> dict[str, object]:
        return await self._pipeline.execute_job(job)
