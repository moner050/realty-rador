"""SITE_A job queue dashboard. 웹 요청은 job만 등록하고 worker가 실행한다."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.infrastructure.database.models import CrawlJob
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import require_admin
from realty_radar.web.jinja_filters import register_jinja_filters
from realty_radar.web.routes.home import _municipality_codes, _region_options


router = APIRouter(tags=["jobs"], dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)


def _progress_context(db: Session) -> dict[str, object]:
    service = CrawlJobService(db)
    return {
        "summary": service.get_progress_summary(),
        "metro_progress": service.get_latest_metro_batch_progress(),
        "region_options": _region_options(),
    }


def _selected_metro_scope_codes(
    *,
    sido_code: str | None,
    municipality: str | None,
    sigungu_code: str | None,
) -> list[int] | None:
    try:
        selected_sido = int(sido_code) if sido_code else None
        selected_sigungu = int(sigungu_code) if sigungu_code else None
    except ValueError as error:
        raise HTTPException(status_code=422, detail="지역 선택값이 올바르지 않습니다.") from error

    if selected_sido is None:
        if municipality or selected_sigungu is not None:
            raise HTTPException(status_code=422, detail="시도를 먼저 선택하세요.")
        return None

    region = next((item for item in _region_options() if item["code"] == selected_sido), None)
    if region is None:
        raise HTTPException(status_code=422, detail="수집 가능한 시도가 아닙니다.")

    all_codes = [
        district["code"]
        for city in region["municipalities"]
        for district in city["districts"] or [{"code": code} for code in city["codes"]]
    ] + [district["code"] for district in region["districts"]]
    municipality_scope = _municipality_codes(selected_sido, municipality)
    if municipality and municipality_scope == []:
        raise HTTPException(status_code=422, detail="선택한 시/군이 해당 시도에 없습니다.")
    allowed_codes = municipality_scope or all_codes
    if selected_sigungu is not None:
        if selected_sigungu not in allowed_codes:
            raise HTTPException(status_code=422, detail="선택한 구가 해당 지역에 없습니다.")
        return [selected_sigungu * 100_000]
    return [code * 100_000 for code in allowed_codes]


def _render_progress(request: Request, db: Session):
    return templates.TemplateResponse(
        request,
        "jobs/progress_partial.html",
        {"is_admin": True, **_progress_context(db)},
    )


@router.get("/jobs", response_class=HTMLResponse, name="jobs_dashboard")
def get_jobs_dashboard(request: Request, db: Annotated[Session, Depends(get_db)]):
    jobs = list(db.scalars(select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(50)).all())
    return templates.TemplateResponse(
        request,
        "jobs/index.html",
        {"jobs": jobs, "is_authenticated": True, "is_admin": True, **_progress_context(db)},
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
    sido_code: Annotated[str | None, Form()] = None,
    municipality: Annotated[str | None, Form()] = None,
    sigungu_code: Annotated[str | None, Form()] = None,
):
    scope_codes = _selected_metro_scope_codes(
        sido_code=sido_code,
        municipality=municipality,
        sigungu_code=sigungu_code,
    )
    CrawlJobService(db).enqueue_metro_batch(scope_codes)
    if request.headers.get("HX-Request") == "true":
        return _render_progress(request, db)
    return RedirectResponse(url="/jobs", status_code=303)
