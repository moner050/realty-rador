import asyncio
import os
import signal
import sys
import uuid

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.infrastructure.database.session import SessionFactory
from realty_radar.worker.job_handler import JobHandler


class WorkerRunner:
    """무한 루프 기반 Worker 작업 Polling 및 안전 종료 실행기."""

    def __init__(self, poll_interval_seconds: int = 5):
        self.worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.poll_interval = poll_interval_seconds
        self.is_running = True

    def stop(self) -> None:
        """Worker 프로세스 안전 종료 플래그 설정."""
        print(f"[{self.worker_id}] Worker 프로세스 종료 요청 수신...")
        self.is_running = False

    async def run(self) -> None:
        """Worker 루프 실행: PENDING/RETRY_WAIT 작업 선점 및 파이프라인 처리."""
        print(f"[{self.worker_id}] Realty Radar Worker 프로세스가 시작되었습니다.")

        while self.is_running:
            with SessionFactory() as db:
                job_service = CrawlJobService(db)
                job = job_service.fetch_next_job(worker_id=self.worker_id)

                if not job:
                    # 대기 작업이 없으면 딜레이 후 폴링
                    await asyncio.sleep(self.poll_interval)
                    continue

                print(f"[{self.worker_id}] 작업 선점 (Job ID: {job.id}, Type: {job.job_type})")

                try:
                    handler = JobHandler(db)
                    result = await handler.handle_job(job)

                    job_service.mark_job_success(job.id, result_data=result)
                    print(f"[{self.worker_id}] 작업 완료 성공 (Job ID: {job.id})")

                except Exception as e:
                    print(f"[{self.worker_id}] 작업 실행 중 오류 발생 (Job ID: {job.id}): {e}")
                    db.rollback()  # 롤백 처리로 세션 복구
                    job_service.mark_job_failure(
                        job_id=job.id,
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )

        print(f"[{self.worker_id}] Worker 프로세스가 종료되었습니다.")


def start_worker():
    """Worker 모듈 단독 실행 엔트리포인트."""
    runner = WorkerRunner()

    def _signal_handler(sig, frame):
        runner.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    asyncio.run(runner.run())
