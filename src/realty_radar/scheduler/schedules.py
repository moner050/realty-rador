from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.application.listing_batch_writer import utc_now
from realty_radar.infrastructure.database.models import SchedulerLog
from realty_radar.infrastructure.database.session import SessionFactory


def schedule_regular_search_job(scope_code: int | None = None) -> None:
    """매일 06시 정각 수도권 전체 시/군/구 정기 수집 배치를 큐에 등록하고 실행 이력을 DB에 기록합니다."""
    with SessionFactory() as db:
        # 스케줄러 실행 시작 로그 기록
        now = utc_now()
        log = SchedulerLog(
            job_name="네이버부동산 매일 06시 전체 수집",
            trigger_type="cron",
            status=SchedulerLog.STATUS_STARTED,
            started_at=now,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        try:
            service = CrawlJobService(db)
            jobs = service.enqueue_metro_batch()
            jobs_count = len(jobs)

            # 성공 기록
            log.status = SchedulerLog.STATUS_SUCCESS
            log.jobs_created = jobs_count
            log.finished_at = utc_now()
            db.commit()

            print(f"[Scheduler] 수도권 전체 시/군/구 정기 수집 배치 {jobs_count}개 job 등록 완료.")

        except Exception as e:
            # 실패 기록
            try:
                db.rollback()
                log_reload = db.get(SchedulerLog, log.log_id)
                if log_reload:
                    log_reload.status = SchedulerLog.STATUS_FAILED
                    log_reload.error_message = str(e)[:512]
                    log_reload.finished_at = utc_now()
                    db.commit()
            except Exception:
                pass

            print(f"[Scheduler] 정기 수집 배치 등록 실패: {e}")
            raise
