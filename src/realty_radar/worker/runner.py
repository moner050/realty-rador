"""lease heartbeat을 유지하며 SITE_A 잡을 실행하는 worker."""
from __future__ import annotations

import asyncio
import os
import signal
import uuid

from realty_radar.application.crawl_job_service import HEARTBEAT_SECONDS, CrawlJobService
from realty_radar.crawler.adapters.site_a.adapter import SiteAAdapter
from realty_radar.crawler.adapters.site_a.http_client import RetryWaitError
from realty_radar.infrastructure.database.session import SessionFactory
from realty_radar.worker.job_handler import JobHandler


class WorkerRunner:
    def __init__(self, poll_interval_seconds: int = 5):
        self.worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.poll_interval = poll_interval_seconds
        self.is_running = True
        self._adapter = SiteAAdapter()

    def stop(self) -> None:
        self.is_running = False

    async def run(self) -> None:
        try:
            while self.is_running:
                with SessionFactory() as db:
                    service = CrawlJobService(db)
                    job = service.claim_next_job(self.worker_id)
                    if job is None:
                        await asyncio.sleep(self.poll_interval)
                        continue
                    token = job.lease_token
                    assert token is not None
                    heartbeat = asyncio.create_task(self._heartbeat(service, job.job_id, token))
                    try:
                        result = await JobHandler(db, self._adapter).handle_job(job)
                        service.mark_success(job.job_id, token, result)
                    except RetryWaitError as error:
                        service.mark_retry(job.job_id, token, "RETRY_WAIT", str(error))
                    except Exception as error:
                        service.mark_retry(job.job_id, token, type(error).__name__, str(error))
                    finally:
                        heartbeat.cancel()
                        try:
                            await heartbeat
                        except asyncio.CancelledError:
                            pass
        finally:
            await self._adapter.aclose()

    async def _heartbeat(self, service: CrawlJobService, job_id: int, token: str) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            if not service.heartbeat(job_id, token):
                return


def start_worker() -> None:
    runner = WorkerRunner()
    signal.signal(signal.SIGINT, lambda *_: runner.stop())
    signal.signal(signal.SIGTERM, lambda *_: runner.stop())
    asyncio.run(runner.run())
