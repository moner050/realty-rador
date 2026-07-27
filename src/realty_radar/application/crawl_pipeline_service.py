"""SITE_A producer → bounded DB writer → scope completeness pipeline."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from realty_radar.application.async_batch_writer import BoundedBatchWriter
from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.application.mortgage_enrichment_service import MortgageEnrichmentRunner
from realty_radar.crawler.adapters.site_a.adapter import DongCollectionOutcome, SiteAAdapter
from realty_radar.crawler.adapters.site_a.http_client import RetryWaitError
from realty_radar.infrastructure.database.models import CrawlJob


class CrawlPipelineService:
    """SITE_A만 수집하며 raw payload·fuzzy match·cross-source dedup을 수행하지 않는다."""

    def __init__(
        self,
        db: Session,
        *,
        session_factory: sessionmaker | None = None,
        adapter_factory: Callable[[], SiteAAdapter] | None = None,
        adapter: SiteAAdapter | None = None,
    ):
        self.db = db
        self.job_service = CrawlJobService(db)
        self._session_factory = session_factory or sessionmaker(
            bind=db.get_bind(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        self._adapter_factory = adapter_factory or SiteAAdapter
        self._adapter = adapter

    async def execute_job(self, job: CrawlJob) -> dict[str, object]:
        """한 job의 대상 동을 수집한다. 실패한 동은 stale 판단에서 제외된다."""
        adapter = self._adapter or self._adapter_factory()
        close_adapter = self._adapter is None
        writer = BoundedBatchWriter(self._session_factory, job.job_id)
        writer.start()
        outcomes: list[DongCollectionOutcome] = []
        stale_count = 0
        removed_count = 0
        partial_count = 0
        semaphore = asyncio.Semaphore(4)

        async def collect_one_dong(region_code: int) -> None:
            nonlocal stale_count, removed_count, partial_count
            async with semaphore:
                self.job_service.open_scope(job.job_id, region_code)
                try:
                    outcome = await adapter.collect_dong(region_code, writer.submit)
                except RetryWaitError:
                    self.job_service.fail_scope(job.job_id, region_code, "RETRY_WAIT", "SITE_A HTTP circuit is open")
                    raise
                except Exception as error:
                    self.job_service.fail_scope(job.job_id, region_code, type(error).__name__, str(error))
                    partial_count += 1
                    return

                await writer.flush()
                self.job_service.record_page(
                    job.job_id,
                    region_code,
                    fetched=outcome.fetched_count,
                    committed=outcome.parsed_count,
                    rejected=outcome.rejected_count,
                )
                if outcome.partial:
                    self.job_service.fail_scope(job.job_id, region_code, "PARTIAL", "pagination was incomplete", truncated=True)
                    partial_count += 1
                else:
                    stale, removed = self.job_service.complete_scope(job.job_id, region_code)
                    stale_count += stale
                    removed_count += removed
                outcomes.append(outcome)

        try:
            begin_job = getattr(adapter, "begin_job", None)
            if begin_job is not None:
                await begin_job()
            dongs = await adapter.list_dongs(job.scope_code)
            target_dongs = dongs or [job.scope_code]
            tasks = [asyncio.create_task(collect_one_dong(region_code)) for region_code in target_dongs]
            try:
                await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            batch_result = await writer.aclose()
            detail_checked_count = await MortgageEnrichmentRunner(
                self._session_factory,
                detail_fetcher=adapter.article_detail,
                job_id=job.job_id,
            ).run_once(batch_size=100, priority_job_id=job.job_id)
            return {
                "job_id": job.job_id,
                "scope_code": job.scope_code,
                "dong_count": len(target_dongs),
                "partial_scope_count": partial_count,
                "stale_count": stale_count,
                "removed_count": removed_count,
                "fetched_count": batch_result.fetched_count,
                "committed_count": batch_result.committed_count,
                "created_count": batch_result.created_count,
                "updated_count": batch_result.updated_count,
                "rejected_count": batch_result.rejected_count,
                "detail_checked_count": detail_checked_count,
                "outcomes": [asdict(outcome) for outcome in outcomes],
            }
        finally:
            try:
                await writer.aclose()
            finally:
                closer = getattr(adapter, "aclose", None)
                if close_adapter and closer is not None:
                    await closer()
