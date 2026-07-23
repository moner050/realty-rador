from datetime import datetime, timedelta
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.constants import CrawlJobStatus, CrawlJobType
from realty_radar.infrastructure.cache.redis_client import redis_cache
from realty_radar.infrastructure.database.models import CrawlJob, CrawlSource


class CrawlJobService:
    """크롤링 비동기 작업 큐 생성, 선점 및 상태 변경 서비스."""

    def __init__(self, db: Session):
        self.db = db

    def _get_or_create_source(self, source_code: str) -> CrawlSource:
        """출처 사이트 코드로 조회 후 없으면 새로 생성."""
        stmt = select(CrawlSource).where(CrawlSource.source_code == source_code)
        source = self.db.scalar(stmt)
        if not source:
            source = CrawlSource(
                source_code=source_code,
                source_name=f"출처 사이트 ({source_code})",
                base_url=f"https://{source_code.lower()}.com",
            )
            self.db.add(source)
            self.db.flush()
        return source

    def create_job(
        self,
        source_code: str,
        job_type: CrawlJobType,
        target_region: Optional[str] = None,
        target_url: Optional[str] = None,
        priority: int = 10,
        request_data: Optional[dict[str, Any]] = None,
    ) -> CrawlJob:
        """신규 크롤링 작업 큐 생성."""
        source = self._get_or_create_source(source_code)

        region = target_region or (request_data.get("region_name") if request_data else None)

        job = CrawlJob(
            source_id=source.id,
            job_type=job_type.value if hasattr(job_type, "value") else str(job_type),
            target_region=region,
            target_url=target_url,
            status=CrawlJobStatus.PENDING.value,
            priority=priority,
            created_at=datetime.now(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def fetch_next_job(self, worker_id: str = "worker-1") -> CrawlJob | None:
        """대기(PENDING/RETRY_WAIT) 중인 최우선 작업을 선점하여 RUNNING으로 변경."""
        now = datetime.now()

        stmt = (
            select(CrawlJob)
            .where(
                CrawlJob.status.in_([CrawlJobStatus.PENDING.value, CrawlJobStatus.RETRY_WAIT.value]),
                (CrawlJob.next_retry_at.is_(None)) | (CrawlJob.next_retry_at <= now),
            )
            .order_by(CrawlJob.priority.asc(), CrawlJob.created_at.asc())
        )
        job = self.db.scalar(stmt)

        if job:
            job.status = CrawlJobStatus.RUNNING.value
            job.worker_id = worker_id
            job.started_at = now
            job.retry_count += 1
            self.db.commit()
            self.db.refresh(job)
            return job

        return None

    def mark_job_success(self, job_id: int, result_data: Any = None) -> CrawlJob | None:
        """작업 처리 성공 완료 처리."""
        stmt = select(CrawlJob).where(CrawlJob.id == job_id)
        job = self.db.scalar(stmt)

        if job:
            job.status = CrawlJobStatus.SUCCESS.value
            job.finished_at = datetime.now()
            self.db.commit()
            self.db.refresh(job)
            return job
        return None

    def mark_job_failure(self, job_id: int, error_type: str, error_message: str) -> CrawlJob | None:
        """작업 실패 및 재시도 스케줄링 처리."""
        stmt = select(CrawlJob).where(CrawlJob.id == job_id)
        job = self.db.scalar(stmt)

        if job:
            job.error_type = error_type
            job.error_message = error_message

            if job.retry_count < job.max_retries:
                job.status = CrawlJobStatus.RETRY_WAIT.value
                job.next_retry_at = datetime.now() + timedelta(minutes=5 * job.retry_count)
            else:
                job.status = CrawlJobStatus.FAILED.value
                job.finished_at = datetime.now()

            self.db.commit()
            self.db.refresh(job)
            return job
        return None

    def get_progress_summary(self) -> dict[str, Any]:
        """최근 크롤링 진행 현황, 수치 통계 및 백분율(%) 계산 (Redis 5초 인메모리 캐싱 지원)."""
        cache_key = "crawl_job_progress_summary"
        cached_summary = redis_cache.get(cache_key)
        if cached_summary and isinstance(cached_summary, dict):
            return cached_summary

        stmt = select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(100)
        jobs = list(self.db.scalars(stmt).all())

        total_jobs = len(jobs)
        if total_jobs == 0:
            res = {
                "total_jobs": 0,
                "completed_jobs": 0,
                "running_jobs": 0,
                "pending_jobs": 0,
                "failed_jobs": 0,
                "progress_percent": 100,
                "is_active_crawling": False,
                "current_target": "대기 중인 수집 없음",
                "recent_jobs": [],
            }
            redis_cache.set(cache_key, res, ttl=5)
            return res

        pending_jobs = sum(1 for j in jobs if j.status == "PENDING")
        running_jobs = sum(1 for j in jobs if j.status == "RUNNING")
        success_jobs = sum(1 for j in jobs if j.status == "SUCCESS")
        failed_jobs = sum(1 for j in jobs if j.status in ["FAILED", "RETRY_WAIT"])

        completed_jobs = success_jobs + failed_jobs
        progress_percent = int((completed_jobs / total_jobs) * 100) if total_jobs > 0 else 100
        is_active_crawling = (running_jobs + pending_jobs) > 0

        active_job = next((j for j in jobs if j.status == "RUNNING"), None)
        if active_job:
            region = active_job.target_region or "전국"
            current_target = f"{active_job.source.source_name if active_job.source else '네이버부동산'} ({region})"
        elif pending_jobs > 0:
            current_target = f"크롤링 대기 중 ({pending_jobs}건)"
        else:
            current_target = "모든 작업 완료됨"

        res = {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "running_jobs": running_jobs,
            "pending_jobs": pending_jobs,
            "failed_jobs": failed_jobs,
            "progress_percent": progress_percent,
            "is_active_crawling": is_active_crawling,
            "current_target": current_target,
            "recent_jobs": [
                {
                    "id": j.id,
                    "status": j.status,
                    "target_region": j.target_region,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in jobs[:5]
            ],
        }
        redis_cache.set(cache_key, res, ttl=5)
        return res
