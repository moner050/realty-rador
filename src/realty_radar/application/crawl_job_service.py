"""SITE_A 전용 lease 기반 crawl job queue와 동 coverage 상태 관리."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from realty_radar.application.listing_batch_writer import (
    CHANGE_LIFECYCLE,
    HISTORY_REMOVED,
    HISTORY_STALE,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_REMOVED,
    LIFECYCLE_STALE,
    utc_now,
)
from realty_radar.crawler.adapters.site_a.region_codes import SIGUNGU_CODES
from realty_radar.infrastructure.database.models import CrawlJob, CrawlScope, ListingCurrent, ListingHistory


JOB_QUEUED = 1
JOB_RUNNING = 2
JOB_SUCCESS = 3
JOB_RETRY_WAIT = 4
JOB_FAILED = 5
JOB_CANCELLED = 6

SCOPE_PENDING = 1
SCOPE_COMPLETE = 2
SCOPE_FAILED = 3

LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 15
METRO_BATCH_PREFIX = "manual-metro:"
METRO_SCOPE_LEVEL = 2

_SIGUNGU_BY_CODE = {
    int(code): (sido_name, sigungu_name)
    for sido_name, sigungu_codes in SIGUNGU_CODES.items()
    for sigungu_name, code in sigungu_codes.items()
}

_JOB_STATUS_LABELS = {
    JOB_QUEUED: "대기",
    JOB_RUNNING: "수집 중",
    JOB_SUCCESS: "완료",
    JOB_RETRY_WAIT: "재시도 대기",
    JOB_FAILED: "실패",
    JOB_CANCELLED: "취소",
}


class CrawlJobService:
    """잡 선점과 동 단위 완결성 판정을 DB 트랜잭션으로 보장한다."""

    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        *,
        scope_level: int,
        scope_code: int,
        dedupe_key: str,
        priority: int = 100,
        max_attempts: int = 3,
    ) -> CrawlJob:
        """중복 키가 살아 있으면 기존 잡을 반환하고, 아니면 새 SITE_A 잡을 만든다."""
        existing = self.db.scalar(select(CrawlJob).where(CrawlJob.dedupe_key == dedupe_key))
        if existing is not None:
            return existing

        now = utc_now()
        job = CrawlJob(
            dedupe_key=dedupe_key[:160],
            status=JOB_QUEUED,
            priority=priority,
            available_at=now,
            attempt=0,
            max_attempts=max_attempts,
            scope_level=scope_level,
            scope_code=scope_code,
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def enqueue_metro_batch(self, scope_codes: list[int] | None = None) -> list[CrawlJob]:
        """Queue a manual batch for all metro sigungu or an explicitly selected subset."""
        if self.get_latest_metro_batch_progress()["is_active"]:
            return []

        codes = list(dict.fromkeys(scope_codes or list(_SIGUNGU_BY_CODE)))
        if not codes or any(code not in _SIGUNGU_BY_CODE for code in codes):
            raise ValueError("scope_codes must be known metro sigungu codes")

        now = utc_now()
        batch_id = uuid4().hex
        jobs = [
            CrawlJob(
                dedupe_key=f"{METRO_BATCH_PREFIX}{batch_id}:{code}",
                status=JOB_QUEUED,
                priority=50,
                available_at=now,
                attempt=0,
                max_attempts=3,
                scope_level=METRO_SCOPE_LEVEL,
                scope_code=int(code),
                created_at=now,
                updated_at=now,
            )
            for code in codes
        ]
        self.db.add_all(jobs)
        self.db.commit()
        return jobs

    def get_latest_metro_batch_progress(self) -> dict[str, object]:
        """Return the latest manual metro batch without adding a tracking table."""
        latest = self.db.scalar(
            select(CrawlJob)
            .where(CrawlJob.dedupe_key.like(f"{METRO_BATCH_PREFIX}%"))
            .order_by(CrawlJob.created_at.desc(), CrawlJob.job_id.desc())
            .limit(1)
        )
        if latest is None:
            return self._empty_metro_batch_progress()

        batch_id = self._metro_batch_id(latest.dedupe_key)
        if batch_id is None:
            return self._empty_metro_batch_progress()
        jobs = list(
            self.db.scalars(
                select(CrawlJob)
                .where(CrawlJob.dedupe_key.like(f"{METRO_BATCH_PREFIX}{batch_id}:%"))
                .order_by(CrawlJob.scope_code)
            ).all()
        )
        status_counts = {
            JOB_QUEUED: 0,
            JOB_RUNNING: 0,
            JOB_SUCCESS: 0,
            JOB_RETRY_WAIT: 0,
            JOB_FAILED: 0,
            JOB_CANCELLED: 0,
        }
        regions: dict[str, list[dict[str, object]]] = {sido_name: [] for sido_name in SIGUNGU_CODES}
        for job in jobs:
            status_counts[job.status] = status_counts.get(job.status, 0) + 1
            sido_name, sigungu_name = _SIGUNGU_BY_CODE.get(job.scope_code, ("기타", str(job.scope_code)))
            regions.setdefault(sido_name, []).append(
                {
                    "job_id": job.job_id,
                    "sigungu_name": sigungu_name,
                    "status": job.status,
                    "status_label": _JOB_STATUS_LABELS.get(job.status, "알 수 없음"),
                    "fetched_count": job.fetched_count,
                    "committed_count": job.committed_count,
                    "error_code": job.error_code,
                    "error_message": job.error_message,
                }
            )

        pending_count = status_counts[JOB_QUEUED] + status_counts[JOB_RETRY_WAIT]
        running_count = status_counts[JOB_RUNNING]
        failed_count = status_counts[JOB_FAILED]
        success_count = status_counts[JOB_SUCCESS]
        return {
            "has_batch": True,
            "batch_id": batch_id,
            "total_sigungu": len(jobs),
            "pending_count": pending_count,
            "running_count": running_count,
            "completed_count": success_count,
            "failed_count": failed_count,
            "retry_count": status_counts[JOB_RETRY_WAIT],
            "is_active": bool(pending_count or running_count),
            "worker_waiting": bool(status_counts[JOB_QUEUED] and not running_count),
            "regions": [
                {"sido_name": sido_name, "items": items}
                for sido_name, items in regions.items()
                if items
            ],
        }

    @staticmethod
    def _metro_batch_id(dedupe_key: str) -> str | None:
        if not dedupe_key.startswith(METRO_BATCH_PREFIX):
            return None
        batch_id, separator, _ = dedupe_key[len(METRO_BATCH_PREFIX):].partition(":")
        return batch_id if separator and batch_id else None

    @staticmethod
    def _empty_metro_batch_progress() -> dict[str, object]:
        return {
            "has_batch": False,
            "batch_id": None,
            "total_sigungu": 0,
            "pending_count": 0,
            "running_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "is_active": False,
            "worker_waiting": False,
            "regions": [],
        }

    def claim_next_job(self, worker_id: str) -> CrawlJob | None:
        """``FOR UPDATE SKIP LOCKED``로 하나를 선점하고 60초 lease를 부여한다."""
        now = utc_now()
        self._reap_expired_leases(now)
        statement = (
            select(CrawlJob)
            .where(
                CrawlJob.status.in_((JOB_QUEUED, JOB_RETRY_WAIT)),
                CrawlJob.available_at <= now,
                CrawlJob.attempt < CrawlJob.max_attempts,
            )
            .order_by(CrawlJob.available_at, CrawlJob.priority, CrawlJob.job_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = self.db.scalar(statement)
        if job is None:
            return None

        job.status = JOB_RUNNING
        job.attempt += 1
        job.lease_token = uuid4().hex
        job.lease_owner = worker_id[:120]
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.started_at = job.started_at or now
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def heartbeat(self, job_id: int, lease_token: str) -> bool:
        now = utc_now()
        result = self.db.execute(
            update(CrawlJob)
            .where(
                CrawlJob.job_id == job_id,
                CrawlJob.status == JOB_RUNNING,
                CrawlJob.lease_token == lease_token,
                CrawlJob.lease_expires_at > now,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                updated_at=now,
            )
        )
        self.db.commit()
        return result.rowcount == 1

    def mark_success(self, job_id: int, lease_token: str, result_json: dict | None = None) -> CrawlJob | None:
        return self._finish(job_id, lease_token, JOB_SUCCESS, result_json=result_json)

    def mark_retry(self, job_id: int, lease_token: str, error_code: str, error_message: str) -> CrawlJob | None:
        job = self._leased_job(job_id, lease_token)
        if job is None:
            return None

        now = utc_now()
        job.error_code = error_code[:64]
        job.error_message = error_message[:512]
        job.lease_token = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.updated_at = now
        if job.attempt >= job.max_attempts:
            job.status = JOB_FAILED
            job.finished_at = now
        else:
            job.status = JOB_RETRY_WAIT
            job.available_at = now + timedelta(seconds=min(300, 5 * (2 ** max(0, job.attempt - 1))))
        self.db.commit()
        self.db.refresh(job)
        return job

    def open_scope(self, job_id: int, region_code: int, total_pages: int = 0) -> CrawlScope:
        scope = self.db.get(CrawlScope, (job_id, region_code))
        if scope is not None:
            return scope
        scope = CrawlScope(
            job_id=job_id,
            region_code=region_code,
            status=SCOPE_PENDING,
            total_pages=total_pages,
            started_at=utc_now(),
        )
        self.db.add(scope)
        self.db.commit()
        self.db.refresh(scope)
        return scope

    def record_page(self, job_id: int, region_code: int, *, fetched: int, committed: int, rejected: int) -> None:
        now = utc_now()
        self.db.execute(
            update(CrawlScope)
            .where(CrawlScope.job_id == job_id, CrawlScope.region_code == region_code)
            .values(
                done_pages=CrawlScope.done_pages + 1,
                fetched_count=CrawlScope.fetched_count + fetched,
                committed_count=CrawlScope.committed_count + committed,
                rejected_count=CrawlScope.rejected_count + rejected,
                finished_at=now,
            )
        )
        self.db.commit()

    def fail_scope(self, job_id: int, region_code: int, error_code: str, error_message: str, truncated: bool = False) -> None:
        self.db.execute(
            update(CrawlScope)
            .where(CrawlScope.job_id == job_id, CrawlScope.region_code == region_code)
            .values(
                status=SCOPE_FAILED,
                failed_pages=CrawlScope.failed_pages + 1,
                is_truncated=truncated,
                error_code=error_code[:64],
                error_message=error_message[:512],
                finished_at=utc_now(),
            )
        )
        self.db.commit()

    def complete_scope(self, job_id: int, region_code: int) -> tuple[int, int]:
        """완전한 동 수집일 때만 그 동의 미관측 매물을 stale/remove 처리한다."""
        scope = self.db.get(CrawlScope, (job_id, region_code))
        if scope is None:
            raise ValueError("scope must be opened before completion")
        if scope.status == SCOPE_COMPLETE:
            return (0, 0)
        if scope.status == SCOPE_FAILED or scope.failed_pages > 0 or scope.is_truncated:
            return (0, 0)

        scope.status = SCOPE_COMPLETE
        scope.finished_at = utc_now()
        self.db.flush()
        if self.db.bind is not None and self.db.bind.dialect.name == "mysql":
            stale, removed = self._advance_lifecycle_mysql(job_id, region_code)
        else:
            stale, removed = self._advance_lifecycle_sqlite(job_id, region_code)
        self.db.commit()
        return stale, removed

    def get_progress_summary(self) -> dict[str, int | bool | str | list[dict[str, object]]]:
        jobs = list(self.db.scalars(select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(100)).all())
        status_counts = {status: 0 for status in (JOB_QUEUED, JOB_RUNNING, JOB_SUCCESS, JOB_RETRY_WAIT, JOB_FAILED)}
        for job in jobs:
            status_counts[job.status] = status_counts.get(job.status, 0) + 1
        return {
            "total_jobs": len(jobs),
            "completed_jobs": status_counts[JOB_SUCCESS] + status_counts[JOB_FAILED],
            "running_jobs": status_counts[JOB_RUNNING],
            "pending_jobs": status_counts[JOB_QUEUED] + status_counts[JOB_RETRY_WAIT],
            "failed_jobs": status_counts[JOB_FAILED],
            "progress_percent": 100 if not jobs else int(
                100 * (status_counts[JOB_SUCCESS] + status_counts[JOB_FAILED]) / len(jobs)
            ),
            "is_active_crawling": bool(status_counts[JOB_RUNNING] or status_counts[JOB_QUEUED] or status_counts[JOB_RETRY_WAIT]),
            "current_target": "SITE_A",
            "recent_jobs": [
                {
                    "id": job.job_id,
                    "status": job.status,
                    "target_region": str(job.scope_code),
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                }
                for job in jobs[:5]
            ],
        }

    def _leased_job(self, job_id: int, lease_token: str) -> CrawlJob | None:
        now = utc_now()
        return self.db.scalar(
            select(CrawlJob).where(
                CrawlJob.job_id == job_id,
                CrawlJob.status == JOB_RUNNING,
                CrawlJob.lease_token == lease_token,
                CrawlJob.lease_expires_at > now,
            )
        )

    def _finish(self, job_id: int, lease_token: str, status: int, result_json: dict | None = None) -> CrawlJob | None:
        job = self._leased_job(job_id, lease_token)
        if job is None:
            return None
        now = utc_now()
        job.status = status
        job.result_json = result_json
        job.finished_at = now
        job.lease_token = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def _reap_expired_leases(self, now) -> None:
        expired = list(
            self.db.scalars(
                select(CrawlJob)
                .where(CrawlJob.status == JOB_RUNNING, CrawlJob.lease_expires_at <= now)
                .with_for_update(skip_locked=True)
            ).all()
        )
        for job in expired:
            job.lease_token = None
            job.lease_owner = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.updated_at = now
            if job.attempt >= job.max_attempts:
                job.status = JOB_FAILED
                job.finished_at = now
            else:
                job.status = JOB_RETRY_WAIT
                job.available_at = now
        if expired:
            self.db.flush()

    def _advance_lifecycle_sqlite(self, job_id: int, region_code: int) -> tuple[int, int]:
        candidates = list(
            self.db.scalars(
                select(ListingCurrent).where(
                    ListingCurrent.region_code == region_code,
                    ListingCurrent.last_seen_job_id != job_id,
                    ListingCurrent.lifecycle.in_((LIFECYCLE_ACTIVE, LIFECYCLE_STALE)),
                )
            ).all()
        )
        stale = 0
        removed = 0
        now = utc_now()
        for listing in candidates:
            if listing.lifecycle == LIFECYCLE_ACTIVE:
                listing.lifecycle = LIFECYCLE_STALE
                listing.miss_count = min(255, listing.miss_count + 1)
                event_type = HISTORY_STALE
                stale += 1
            else:
                listing.lifecycle = LIFECYCLE_REMOVED
                listing.miss_count = min(255, listing.miss_count + 1)
                listing.removed_at = now
                event_type = HISTORY_REMOVED
                removed += 1
            listing.last_changed_at = now
            self.db.add(
                ListingHistory(
                    article_id=listing.article_id,
                    complex_id=listing.complex_id,
                    job_id=job_id,
                    event_type=event_type,
                    change_mask=CHANGE_LIFECYCLE,
                    primary_price=listing.primary_price,
                    monthly_rent=listing.monthly_rent,
                    lifecycle=listing.lifecycle,
                    mortgage_code=listing.mortgage_code,
                    floor_no=listing.floor_no,
                    total_floor=listing.total_floor,
                    direction_code=listing.direction_code,
                    state_hash=listing.state_hash,
                    occurred_at=now,
                )
            )
        if candidates:
            self.db.execute(
                update(CrawlJob)
                .where(CrawlJob.job_id == job_id)
                .values(removed_count=CrawlJob.removed_count + removed, updated_at=now)
            )
        return stale, removed

    def _advance_lifecycle_mysql(self, job_id: int, region_code: int) -> tuple[int, int]:
        connection = self.db.connection()
        parameters = {
            "job_id": job_id,
            "region_code": region_code,
            "active": LIFECYCLE_ACTIVE,
            "stale": LIFECYCLE_STALE,
            "removed": LIFECYCLE_REMOVED,
            "stale_event": HISTORY_STALE,
            "removed_event": HISTORY_REMOVED,
            "mask": CHANGE_LIFECYCLE,
            "now": utc_now(),
        }
        stale = int(
            connection.scalar(
                text(
                    """
                    SELECT COUNT(*) FROM listing_current
                    WHERE region_code = :region_code AND last_seen_job_id <> :job_id
                      AND lifecycle = :active
                    """
                ),
                parameters,
            )
            or 0
        )
        removed = int(
            connection.scalar(
                text(
                    """
                    SELECT COUNT(*) FROM listing_current
                    WHERE region_code = :region_code AND last_seen_job_id <> :job_id
                      AND lifecycle = :stale
                    """
                ),
                parameters,
            )
            or 0
        )
        connection.execute(
            text(
                """
                INSERT IGNORE INTO listing_history (
                    article_id, complex_id, job_id, event_type, change_mask, primary_price,
                    monthly_rent, lifecycle, mortgage_code, floor_no, total_floor,
                    direction_code, state_hash, occurred_at
                )
                SELECT article_id, complex_id, :job_id,
                       CASE WHEN lifecycle = :active THEN :stale_event ELSE :removed_event END,
                       :mask, primary_price, monthly_rent,
                       CASE WHEN lifecycle = :active THEN :stale ELSE :removed END,
                       mortgage_code, floor_no, total_floor, direction_code, state_hash, :now
                FROM listing_current
                WHERE region_code = :region_code AND last_seen_job_id <> :job_id
                  AND lifecycle IN (:active, :stale)
                """
            ),
            parameters,
        )
        connection.execute(
            text(
                """
                UPDATE listing_current
                SET lifecycle = CASE WHEN lifecycle = :active THEN :stale ELSE :removed END,
                    miss_count = LEAST(255, miss_count + 1),
                    last_changed_at = :now,
                    removed_at = CASE WHEN lifecycle = :stale THEN :now ELSE removed_at END
                WHERE region_code = :region_code AND last_seen_job_id <> :job_id
                  AND lifecycle IN (:active, :stale)
                """
            ),
            parameters,
        )
        if removed:
            connection.execute(
                update(CrawlJob)
                .where(CrawlJob.job_id == job_id)
                .values(removed_count=CrawlJob.removed_count + removed, updated_at=parameters["now"])
            )
        return stale, removed
