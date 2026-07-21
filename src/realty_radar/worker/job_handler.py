from sqlalchemy.orm import Session

from realty_radar.application.crawl_pipeline_service import CrawlPipelineService
from realty_radar.constants import CrawlJobType
from realty_radar.infrastructure.database.models import CrawlJob


class JobHandler:
    """CrawlJob 작업 처리 핸들러."""

    def __init__(self, db: Session):
        self.db = db
        self.pipeline_service = CrawlPipelineService(db)

    async def handle_job(self, job: CrawlJob) -> dict:
        """CrawlJob 유형별 비동기 수행 함수."""
        req_data = getattr(job, "request_json", None) or {}
        source_code = job.source.source_code if (job.source and hasattr(job.source, "source_code")) else req_data.get("source_code", "SITE_A")
        region_name = job.target_region or req_data.get("region_name") or "여의도동"

        if job.job_type == CrawlJobType.SEARCH.value or job.job_type == "SEARCH":
            # 검색 수집 파이프라인 구동
            result = await self.pipeline_service.execute_search_pipeline(
                source_code=source_code,
                region_name=region_name,
            )
            return result
        else:
            return {"status": "skipped", "message": f"미지원 작업 유형: {job.job_type}"}
