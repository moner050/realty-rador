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


@router.get("/jobs", response_class=HTMLResponse, name="jobs_dashboard")
def get_jobs_dashboard(request: Request, db: Annotated[Session, Depends(get_db)]):
    jobs = list(db.scalars(select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(50)).all())
    summary = CrawlJobService(db).get_progress_summary()
    return templates.TemplateResponse(request, "jobs/index.html", {"jobs": jobs, "summary": summary, "is_authenticated": True})


@router.get("/api/crawl-jobs/progress", response_class=HTMLResponse, name="get_crawl_progress")
def get_crawl_progress(request: Request, db: Annotated[Session, Depends(get_db)]):
    return templates.TemplateResponse(request, "jobs/progress_partial.html", {"summary": CrawlJobService(db).get_progress_summary()})


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
        return templates.TemplateResponse(request, "jobs/progress_partial.html", {"summary": CrawlJobService(db).get_progress_summary()})
    return RedirectResponse(url="/jobs", status_code=303)
