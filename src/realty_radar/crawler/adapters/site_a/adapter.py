"""SITE_A API-only collector: Playwright bootstrap, httpx collection, bounded page queue."""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable

from realty_radar.application.listing_batch_writer import IncomingListing
from realty_radar.crawler.adapters.site_a.bootstrap import NaverAuthBootstrap
from realty_radar.crawler.adapters.site_a.http_client import NaverHttpClient, NaverHttpError, RetryWaitError
from realty_radar.crawler.adapters.site_a.parser import SiteAArticleParser, SiteAComplexData, normalize_complex_name, parse_positive_int
from realty_radar.crawler.base.browser import PlaywrightBrowserManager


NEW_LAND_BASE = "https://new.land.naver.com"
MAX_PAGES_PER_COMPLEX = 100


@dataclass(frozen=True, slots=True)
class SiteAComplex(SiteAComplexData):
    """동의 complex API에서 필요한 최소 값만 유지한다."""

    @classmethod
    def from_api(cls, raw: dict, region_code: int) -> "SiteAComplex | None":
        complex_id = parse_positive_int(raw.get("complexNo"))
        if complex_id is None:
            return None
        name = str(raw.get("complexName") or "").strip()
        if not name:
            return None
        base_address = str(raw.get("cortarAddress") or "").strip()
        detail_address = str(raw.get("detailAddress") or "").strip()
        address = " ".join(part for part in (base_address, detail_address) if part) or "미상"
        approve_ymd = str(raw.get("useApproveYmd") or "")
        construction_year = int(approve_ymd[:4]) if approve_ymd[:4].isdigit() else 0
        households = parse_positive_int(raw.get("totalHouseholdCount")) or 0
        return cls(
            complex_id=complex_id,
            region_code=region_code,
            name=name[:120],
            normalized_name=normalize_complex_name(name)[:120] or name[:120],
            address=address[:240],
            construction_year=construction_year,
            household_count=households,
        )


@dataclass(frozen=True, slots=True)
class DongCollectionOutcome:
    region_code: int
    fetched_count: int
    parsed_count: int
    rejected_count: int
    partial: bool


BatchCallback = Callable[[list[IncomingListing]], Awaitable[None] | None]


class NaverLandApi:
    """인증된 httpx JSON endpoint 얇은 래퍼."""

    def __init__(self, client: NaverHttpClient):
        self._client = client

    async def dongs(self, region_code: int) -> list[int]:
        payload = await self._client.get_json(f"{NEW_LAND_BASE}/api/regions/list", params={"cortarNo": region_code})
        if not isinstance(payload, dict):
            raise NaverHttpError("SITE_A region response must be an object")
        return [code for item in payload.get("regionList") or [] if (code := parse_positive_int(item.get("cortarNo"))) is not None]

    async def complexes(self, region_code: int) -> list[SiteAComplex]:
        payload = await self._client.get_json(
            f"{NEW_LAND_BASE}/api/regions/complexes",
            params={"cortarNo": region_code, "realEstateType": "APT", "order": ""},
        )
        if not isinstance(payload, dict):
            raise NaverHttpError("SITE_A complex response must be an object")
        return [
            complex_data
            for item in payload.get("complexList") or []
            if isinstance(item, dict)
            if (complex_data := SiteAComplex.from_api(item, region_code)) is not None
        ]

    async def articles(self, complex_id: int, page: int) -> dict:
        payload = await self._client.get_json(
            f"{NEW_LAND_BASE}/api/articles/complex/{complex_id}",
            params={"realEstateType": "APT", "tradeType": "", "sameAddressGroup": "false", "page": page},
        )
        if not isinstance(payload, dict):
            raise NaverHttpError("SITE_A article response must be an object")
        return payload


class SiteAAdapter:
    """SITE_A 한 곳만 수집하며 브라우저 fetch fallback을 제공하지 않는다."""

    def __init__(self, *, api: NaverLandApi | object | None = None, headless: bool = True):
        self._owns_resources = api is None
        if api is None:
            self._browser_manager = PlaywrightBrowserManager(headless=headless)
            self._http_client = NaverHttpClient(NaverAuthBootstrap(self._browser_manager))
            self._api = NaverLandApi(self._http_client)
        else:
            self._browser_manager = None
            self._http_client = None
            self._api = api
        self._parser = SiteAArticleParser()

    async def list_dongs(self, region_code: int) -> list[int]:
        return await self._api.dongs(region_code)

    async def begin_job(self) -> None:
        """job마다 독립 Playwright context bootstrap, HTTP connection pool은 재사용."""
        if self._http_client is not None:
            await self._http_client.refresh_session()

    async def collect_dong(self, region_code: int, on_batch: BatchCallback) -> DongCollectionOutcome:
        complexes = await self._api.complexes(region_code)
        if not complexes:
            return DongCollectionOutcome(region_code, 0, 0, 0, False)

        page_queue: asyncio.Queue[tuple[SiteAComplex, int] | None] = asyncio.Queue()
        for complex_data in complexes:
            page_queue.put_nowait((complex_data, 1))

        seen_page_signatures: dict[int, set[tuple[int, ...]]] = {}
        seen_articles: set[int] = set()
        state = {"fetched": 0, "parsed": 0, "rejected": 0, "partial": False}
        state_lock = asyncio.Lock()

        async def worker() -> None:
            while True:
                item = await page_queue.get()
                if item is None:
                    page_queue.task_done()
                    return
                complex_data, page = item
                try:
                    payload = await self._api.articles(complex_data.complex_id, page)
                    articles = payload.get("articleList") or []
                    if not isinstance(articles, list):
                        async with state_lock:
                            state["partial"] = True
                        continue
                    article_ids = tuple(
                        article_id
                        for raw in articles
                        if isinstance(raw, dict)
                        if (article_id := parse_positive_int(raw.get("articleNo"))) is not None
                    )
                    signatures = seen_page_signatures.setdefault(complex_data.complex_id, set())
                    if page > 1 and article_ids in signatures:
                        async with state_lock:
                            state["partial"] = True
                        continue
                    signatures.add(article_ids)
                    if payload.get("isMoreData") and (not article_ids or page >= MAX_PAGES_PER_COMPLEX):
                        async with state_lock:
                            state["partial"] = True
                    elif payload.get("isMoreData"):
                        page_queue.put_nowait((complex_data, page + 1))

                    parsed_rows: list[IncomingListing] = []
                    rejected = 0
                    for raw in articles:
                        if not isinstance(raw, dict):
                            rejected += 1
                            continue
                        parsed = self._parser.parse(raw, complex_data)
                        if parsed is None:
                            rejected += 1
                            continue
                        if parsed.article_id in seen_articles:
                            continue
                        seen_articles.add(parsed.article_id)
                        parsed_rows.append(parsed)
                    if parsed_rows:
                        callback_result = on_batch(parsed_rows)
                        if inspect.isawaitable(callback_result):
                            await callback_result
                    async with state_lock:
                        state["fetched"] += len(articles)
                        state["parsed"] += len(parsed_rows)
                        state["rejected"] += rejected
                except RetryWaitError:
                    raise
                except NaverHttpError:
                    async with state_lock:
                        state["partial"] = True
                finally:
                    page_queue.task_done()

        worker_count = min(32, max(1, len(complexes)))
        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
        try:
            await page_queue.join()
        finally:
            for _ in workers:
                page_queue.put_nowait(None)
            await asyncio.gather(*workers)
        return DongCollectionOutcome(
            region_code=region_code,
            fetched_count=state["fetched"],
            parsed_count=state["parsed"],
            rejected_count=state["rejected"],
            partial=state["partial"],
        )

    async def aclose(self) -> None:
        if not self._owns_resources:
            return
        assert self._http_client is not None
        assert self._browser_manager is not None
        await self._http_client.aclose()
        await self._browser_manager.close()
