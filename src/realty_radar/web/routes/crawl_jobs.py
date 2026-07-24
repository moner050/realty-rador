import asyncio
import logging
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.application.crawl_pipeline_service import CrawlPipelineService
from realty_radar.constants import CrawlJobStatus, CrawlJobType
from realty_radar.infrastructure.database.models import CrawlJob
from realty_radar.infrastructure.database.session import get_db, SessionFactory
from realty_radar.web.auth import is_authenticated, require_authentication
from realty_radar.web.jinja_filters import register_jinja_filters

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"], dependencies=[Depends(require_authentication)])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)


def _run_async_crawl_job(job_id: int, source_code: str, region_name: str):
    """백그라운드에서 실행되는 실제 크롤링 수집 비동기 태스크."""
    with SessionFactory() as db:
        job = db.get(CrawlJob, job_id)
        if not job:
            logger.error("CrawlJob id=%d를 찾을 수 없습니다.", job_id)
            return

        job.status = CrawlJobStatus.RUNNING.value
        job.started_at = datetime.now()
        db.commit()

        try:
            pipeline = CrawlPipelineService(db)
            result = asyncio.run(pipeline.execute_search_pipeline(source_code=source_code, region_name=region_name))

            job.status = CrawlJobStatus.SUCCESS.value
            job.completed_at = datetime.now()
            job.total_items_fetched = result.get("total_fetched", 0)
            job.total_items_upserted = result.get("created_count", 0) + result.get("updated_count", 0)
            job.result_summary = (
                f"수집 {result.get('total_fetched', 0)}건 완료 "
                f"(신규 {result.get('created_count', 0)}건, 수정 {result.get('updated_count', 0)}건)"
            )
            db.commit()
            logger.info("수동 크롤링 작업 job_id=%d 완료: %s", job_id, job.result_summary)
        except Exception as e:
            db.rollback()
            logger.exception("수동 크롤링 작업 job_id=%d 실행 중 오류 발생: %s", job_id, e)
            job.status = CrawlJobStatus.FAILED.value
            job.completed_at = datetime.now()
            job.error_log = str(e)
            db.commit()


@router.get("/jobs", response_class=HTMLResponse, name="jobs_dashboard")
def get_jobs_dashboard(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """크롤링 작업 수집 현황 모니터링 화면."""
    stmt = select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(50)
    jobs = list(db.scalars(stmt).all())

    job_service = CrawlJobService(db)
    summary = job_service.get_progress_summary()

    return templates.TemplateResponse(
        request=request,
        name="jobs/index.html",
        context={
            "jobs": jobs,
            "summary": summary,
            "pending_count": summary["pending_jobs"],
            "running_count": summary["running_jobs"],
            "success_count": summary["completed_jobs"],
            "failed_count": summary["failed_jobs"],
            "is_authenticated": True,
        },
    )


@router.get("/api/crawl-jobs/progress", response_class=HTMLResponse, name="get_crawl_progress")
def get_crawl_progress(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """실시간 크롤링 진행도 위젯 HTMX partial 렌더링 API."""
    job_service = CrawlJobService(db)
    summary = job_service.get_progress_summary()

    return templates.TemplateResponse(
        request=request,
        name="jobs/progress_partial.html",
        context={
            "summary": summary,
        },
    )


@router.post("/api/crawl-jobs", name="create_crawl_job")
def create_crawl_job(
    request: Request,
    source_code: Annotated[str, Form(...)],
    region_name: Annotated[str, Form(...)],
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
):
    """웹 폼 수동 수집 작업 등록 및 즉시 백그라운드 수집 가동 API."""
    job_service = CrawlJobService(db)
    job = job_service.create_job(
        source_code=source_code,
        job_type=CrawlJobType.SEARCH,
        target_region=region_name,
        request_data={
            "source_code": source_code,
            "region_name": region_name,
        },
        priority=50,
    )

    # 백그라운드 태스크 등록으로 즉시 수집 가동
    background_tasks.add_task(_run_async_crawl_job, job.id, source_code, region_name)

    # HTMX 요청일 경우 진행도 위젯 HTML 반환
    if request.headers.get("HX-Request"):
        summary = job_service.get_progress_summary()
        return templates.TemplateResponse(
            request=request,
            name="jobs/progress_partial.html",
            context={
                "summary": summary,
            },
        )

    return RedirectResponse(url="/jobs", status_code=303)


@router.post("/api/backfill-households", response_class=HTMLResponse, name="backfill_households")
def backfill_households(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """세대수/준공년도가 비어있는 단지에 대해 공공데이터 일괄 백필 수행."""
    import asyncio
    from realty_radar.enrichment.public_data.sync_service import PublicDataSyncService
    from realty_radar.infrastructure.database.models import ApartmentComplex

    stmt = (
        select(ApartmentComplex)
        .where(
            (ApartmentComplex.total_households.is_(None)) |
            (ApartmentComplex.construction_year.is_(None))
        )
        .limit(100)
    )
    missing_complexes = list(db.scalars(stmt).all())

    sync_svc = PublicDataSyncService(db)
    success_count = 0
    fail_count = 0

    for cpx in missing_complexes:
        try:
            try:
                loop = asyncio.get_running_loop()
                loop.run_until_complete(sync_svc.sync_complex_public_data(cpx.id))
            except RuntimeError:
                asyncio.run(sync_svc.sync_complex_public_data(cpx.id))
            success_count += 1
        except Exception:
            fail_count += 1

    result_html = f"""
    <div class="p-4 rounded-lg bg-emerald-950/40 border border-emerald-500/30 text-sm text-emerald-300 space-y-1">
        <div class="flex items-center space-x-2">
            <svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            <strong>세대수 백필 완료</strong>
        </div>
        <p class="text-xs text-slate-400">
            대상 단지: <strong class="text-white">{len(missing_complexes)}</strong>건 |
            성공: <strong class="text-emerald-400">{success_count}</strong>건 |
            실패: <strong class="text-rose-400">{fail_count}</strong>건
        </p>
    </div>
    """
    return HTMLResponse(content=result_html)
