import asyncio

from sqlalchemy import select

from realty_radar.application.crawl_job_service import JOB_SUCCESS, CrawlJobService
from realty_radar.application.listing_batch_writer import utc_now
from realty_radar.application.mortgage_enrichment_service import run_site_a_mortgage_enrichment
from realty_radar.enrichment.naver_maps.backfill import run_geocode_sweep
from realty_radar.enrichment.naver_maps.geocoder import NaverGeocoder
from realty_radar.infrastructure.database.models import CrawlJob, SchedulerLog
from realty_radar.infrastructure.database.session import SessionFactory


def _latest_successful_crawl_job_id(db) -> int | None:
    return db.scalar(
        select(CrawlJob.job_id)
        .where(CrawlJob.status == JOB_SUCCESS)
        .order_by(CrawlJob.job_id.desc())
        .limit(1)
    )


def schedule_listing_detail_backfill() -> None:
    with SessionFactory() as db:
        job_id = _latest_successful_crawl_job_id(db)

    if job_id is None:
        return

    checked = asyncio.run(
        run_site_a_mortgage_enrichment(
            SessionFactory,
            job_id=job_id,
            batch_size=100,
            concurrency=2,
            max_batches=50,
        )
    )
    print(f"[Scheduler] listing detail checked={checked}")


def schedule_geocode_backfill() -> None:
    with SessionFactory() as db:
        log = SchedulerLog(
            job_name="네이버 지도 단지 좌표 사전 적재",
            trigger_type="cron",
            status=SchedulerLog.STATUS_STARTED,
            started_at=utc_now(),
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        try:
            stats = run_geocode_sweep(
                SessionFactory,
                NaverGeocoder(),
                now=utc_now(),
                batch_size=100,
                max_batches=5,
                max_requests=500,
            )
            log.status = SchedulerLog.STATUS_SUCCESS
            log.finished_at = utc_now()
            db.commit()

            print(
                "[Scheduler] geocode "
                f"selected={stats.selected_count} "
                f"requests={stats.external_request_count} "
                f"ok={stats.ok_count} "
                f"not_found={stats.not_found_count} "
                f"failed={stats.failed_count}"
            )
        except Exception as exc:
            try:
                db.rollback()
                log_reload = db.get(SchedulerLog, log.log_id)
                if log_reload:
                    log_reload.status = SchedulerLog.STATUS_FAILED
                    log_reload.error_message = str(exc)[:512]
                    log_reload.finished_at = utc_now()
                    db.commit()
            except Exception:
                pass

            print(f"[Scheduler] geocode preload failed: {exc}")
            raise


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
