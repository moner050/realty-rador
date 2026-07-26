"""SITE_A crawl job 등록용 CLI helper."""
import asyncio
from datetime import datetime, timezone

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.application.mortgage_enrichment_service import run_site_a_mortgage_enrichment
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


def enrich_mortgages(*, job_id: int, batch_size: int = 100, max_batches: int = 100, concurrency: int = 2) -> int:
    """CLI/scheduler entrypoint for a bounded, resumable SITE_A mortgage sweep."""
    return asyncio.run(
        run_site_a_mortgage_enrichment(
            SessionFactory,
            job_id=job_id,
            batch_size=batch_size,
            max_batches=max_batches,
            concurrency=concurrency,
        )
    )
