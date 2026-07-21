from typing import Annotated
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.constants import CrawlJobType
from realty_radar.infrastructure.database.models import CrawlJob
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.jinja_filters import register_jinja_filters

router = APIRouter(tags=["jobs"])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)


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
    db: Annotated[Session, Depends(get_db)],
):
    """웹 폼 수동 수집 작업 등록 API (HTMX 비동기 응답 지원)."""
    job_service = CrawlJobService(db)
    job_service.create_job(
        source_code=source_code,
        job_type=CrawlJobType.SEARCH,
        target_region=region_name,
        request_data={
            "source_code": source_code,
            "region_name": region_name,
        },
        priority=50,
    )

    # HTMX 요청일 경우 진행도 위젯 HTML 바로 반환
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
