"""SITE_A job queue dashboard. 웹 요청은 job만 등록하고 worker가 실행한다."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.infrastructure.database.models import CrawlJob
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import require_authentication
from realty_radar.web.jinja_filters import register_jinja_filters


router = APIRouter(tags=["jobs"], dependencies=[Depends(require_authentication)])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)


def _progress_context(db: Session) -> dict[str, object]:
    service = CrawlJobService(db)
    return {
        "summary": service.get_progress_summary(),
        "metro_progress": service.get_latest_metro_batch_progress(),
    }


def _render_progress(request: Request, db: Session):
    return templates.TemplateResponse(
        request,
        "jobs/progress_partial.html",
        _progress_context(db),
    )


@router.get("/jobs", response_class=HTMLResponse, name="jobs_dashboard")
def get_jobs_dashboard(request: Request, db: Annotated[Session, Depends(get_db)]):
    jobs = list(db.scalars(select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(50)).all())
    return templates.TemplateResponse(
        request,
        "jobs/index.html",
        {"jobs": jobs, "is_authenticated": True, **_progress_context(db)},
    )


@router.get("/api/crawl-jobs/progress", response_class=HTMLResponse, name="get_crawl_progress")
def get_crawl_progress(request: Request, db: Annotated[Session, Depends(get_db)]):
    return _render_progress(request, db)


@router.post("/api/crawl-jobs", name="create_crawl_job")
def create_crawl_job(
    request: Request,
    region_code: Annotated[int, Form(...)],
    db: Annotated[Session, Depends(get_db)],
):
    now = datetime.now(timezone.utc)
    job = CrawlJobService(db).create_job(
        scope_level=3,
        scope_code=region_code,
        dedupe_key=f"manual:{region_code}:{now.strftime('%Y%m%d%H%M%S%f')}",
        priority=50,
    )
    if request.headers.get("HX-Request") == "true":
        return _render_progress(request, db)
    return RedirectResponse(url="/jobs", status_code=303)


@router.post("/api/crawl-jobs/metro", name="create_metro_crawl_batch")
def create_metro_crawl_batch(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    CrawlJobService(db).enqueue_metro_batch()
    if request.headers.get("HX-Request") == "true":
        return _render_progress(request, db)
    return RedirectResponse(url="/jobs", status_code=303)
