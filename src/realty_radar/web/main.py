import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.config import settings
from realty_radar.constants import TransactionType
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.infrastructure.cache.redis_client import redis_cache
from realty_radar.infrastructure.database.session import SessionFactory
from realty_radar.web.routes.auth import router as auth_router
from realty_radar.web.routes.crawl_jobs import router as crawl_jobs_router
from realty_radar.web.routes.home import _enrich_listings_with_loans, router as home_router
from realty_radar.web.routes.settings import router as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 라이프사이클 이벤트 (0.01초 초고속 부팅)."""
    settings.data_directory.mkdir(parents=True, exist_ok=True)
    settings.auth_directory.mkdir(parents=True, exist_ok=True)
    settings.snapshot_directory.mkdir(parents=True, exist_ok=True)
    settings.screenshot_directory.mkdir(parents=True, exist_ok=True)

    yield


app = FastAPI(
    title="Realty Radar",
    description="개인용 부동산 매물 크롤링·필터링 시스템",
    version="0.1.0",
    lifespan=lifespan,
)

# Static directory 마운트
static_dir = Path("src/realty_radar/web/static")
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 라우터 등록
app.include_router(home_router)
app.include_router(auth_router)
app.include_router(crawl_jobs_router)
app.include_router(settings_router)


@app.get("/healthz", name="healthcheck")
def healthcheck():
    """시스템 헬스체크 API."""
    return {"status": "ok", "app_env": settings.app_env}
