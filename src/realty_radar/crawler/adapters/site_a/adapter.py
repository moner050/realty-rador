"""네이버 부동산 실제 매물 수집 어댑터 (Playwright 세션 + fin.land.naver.com API 기반)."""
import asyncio
import logging
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Error as PlaywrightError

from realty_radar.crawler.adapters.site_a.parser import SiteAParser
from realty_radar.crawler.adapters.site_a.region_codes import resolve_cortarno, SIDO_CODES, SIGUNGU_CODES
from realty_radar.crawler.base.models import RawListing, SourceSearchRequest
from realty_radar.crawler.base.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

FIN_LAND_BASE = "https://fin.land.naver.com"
NEW_LAND_BASE = "https://new.land.naver.com"


class NaverLandScraperClient:
    """Playwright 단일 세션 기반 네이버 부동산 수집 클라이언트 (fin.land.naver.com API 전용)."""

    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._session_page: Page | None = None
        self._initialized = False
        self._closed = False

    async def _ensure_browser(self) -> BrowserContext:
        """Playwright 브라우저 컨텍스트 생성 및 세션 초기화."""
        if self._closed:
            raise RuntimeError("BROWSER_CLOSED")

        if self._context and self._initialized:
            return self._context

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
        )
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = { runtime: {} };
        """)

        self._session_page = await self._context.new_page()
        await self._session_page.goto(
            f"{NEW_LAND_BASE}/complexes?cortarNo=1100000000",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(1)
        self._initialized = True
        logger.info("Playwright 브라우저 세션 초기화 완료")
        return self._context

    async def _fetch_json(self, api_url: str) -> dict | list | None:
        """세션 페이지에서 fetch() GET 호출."""
        if self._closed:
            return None
        await self._ensure_browser()
        try:
            result = await self._session_page.evaluate(f"""
                async () => {{
                    try {{
                        const r = await fetch("{api_url}");
                        if (!r.ok) return null;
                        return await r.json();
                    }} catch(e) {{
                        return null;
                    }}
                }}
            """)
            return result
        except Exception as e:
            err_msg = str(e)
            if "Connection closed" in err_msg or "Target closed" in err_msg or "destroyed" in err_msg:
                self._closed = True
                raise RuntimeError("BROWSER_CLOSED") from e
            logger.warning("API GET fetch 실패 (%s): %s", api_url[:80], e)
            return None

    async def get_dong_list(self, sigungu_cortarno: str) -> list[dict]:
        """구/시 cortarNo에 해당하는 하위 동 목록 조회."""
        await self.rate_limiter.acquire()
        api_url = f"{NEW_LAND_BASE}/api/regions/list?cortarNo={sigungu_cortarno}"
        data = await self._fetch_json(api_url)
        if data and isinstance(data, dict):
            return data.get("regionList") or []
        return []

    async def get_complexes_in_dong(self, dong_cortarno: str) -> list[dict]:
        """동 cortarNo에 해당하는 아파트 단지 목록 조회."""
        await self.rate_limiter.acquire()
        api_url = f"{NEW_LAND_BASE}/api/regions/complexes?cortarNo={dong_cortarno}&realEstateType=APT&order="
        data = await self._fetch_json(api_url)
        if data and isinstance(data, dict):
            return data.get("complexList") or []
        return []

    async def fetch_complex_articles(
        self, complex_no: str, complex_name: str = "", dong_address: str = "",
        source_code: str = "SITE_A", max_pages: int = 5, total_households: int | None = None,
    ) -> list[RawListing]:
        """fin.land.naver.com front-api POST 요청으로 단지 매물 목록 JSON 수집."""
        if self._closed:
            return []

        ctx = await self._ensure_browser()
        parser = SiteAParser()
        raw_listings: list[RawListing] = []
        seen_article_nos: set[str] = set()

        try:
            await self.rate_limiter.acquire()
            page = await ctx.new_page()
            await page.goto(f"{FIN_LAND_BASE}/complexes/{complex_no}?tab=article", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)

            post_url = f"{FIN_LAND_BASE}/front-api/v1/complex/article/list"

            for page_no in range(1, max_pages + 1):
                await self.rate_limiter.acquire()
                payload = {
                    "size": 30,
                    "complexNumber": str(complex_no),
                    "tradeTypes": [],
                    "pyeongTypes": [],
                    "dongNumbers": [],
                    "userChannelType": "PC",
                    "articleSortType": "RANKING_DESC",
                    "lastInfo": []
                }

                res_json = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const r = await fetch("{post_url}", {{
                                method: "POST",
                                headers: {{ "Content-Type": "application/json" }},
                                body: JSON.stringify({payload})
                            }});
                            if (!r.ok) return null;
                            return await r.json();
                        }} catch(e) {{
                            return null;
                        }}
                    }}
                """)

                if not res_json or not isinstance(res_json, dict):
                    break

                result = res_json.get("result") or {}
                articles = result.get("list") or []
                if not articles:
                    break

                for item in articles:
                    info = item.get("representativeArticleInfo") or item
                    article_no = str(info.get("articleNumber") or info.get("articleNo") or "")

                    if not article_no or article_no in seen_article_nos:
                        continue
                    seen_article_nos.add(article_no)

                    raw_item = parser.parse_fin_article_json(
                        item=item,
                        source_code=source_code,
                        default_complex_name=complex_name,
                        default_address=dong_address,
                        total_households=total_households,
                    )
                    if raw_item:
                        raw_listings.append(raw_item)

                if not result.get("hasNextPage"):
                    break

            await page.close()
        except Exception as e:
            err_msg = str(e)
            if "Connection closed" in err_msg or "Target closed" in err_msg or "destroyed" in err_msg:
                self._closed = True
                logger.info("서버 재시작으로 인한 브라우저 연결 종료 감지 (단지: %s)", complex_name)
                raise RuntimeError("BROWSER_CLOSED") from e
            logger.warning("단지 [%s](%s) fin API 수집 중 오류: %s", complex_name, complex_no, e)

        logger.info(
            "단지 [%s](%s) fin API 매물 %d건 수집 완료 (세대수: %s)",
            complex_name, complex_no, len(raw_listings), total_households
        )
        return raw_listings

    async def scrape_complex_listings(
        self, complex_no: str, complex_name: str = "", dong_address: str = "", source_code: str = "SITE_A"
    ) -> list[RawListing]:
        """하위 호환용 별칭 메서드."""
        return await self.fetch_complex_articles(
            complex_no=complex_no,
            complex_name=complex_name,
            dong_address=dong_address,
            source_code=source_code,
        )

    async def close(self):
        """브라우저 리소스 해제."""
        self._closed = True
        if self._session_page:
            try:
                await self._session_page.close()
            except Exception:
                pass
            self._session_page = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._context = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        self._initialized = False


class SiteAAdapter:
    """네이버 부동산 실제 매물 수집 어댑터 (SITE_A)."""

    source_code: str = "SITE_A"

    def __init__(self, headless: bool = True, interval_ms: int = 1500):
        self.rate_limiter = RateLimiter(interval_ms=interval_ms)
        self.client = NaverLandScraperClient(rate_limiter=self.rate_limiter)

    async def _collect_region(self, cortarno: str, limit: int | None = None) -> list[RawListing]:
        """특정 구/시 cortarNo의 모든 동/단지를 순회하여 매물 수집."""
        raw_listings: list[RawListing] = []

        try:
            dongs = await self.client.get_dong_list(cortarno)
            if not dongs:
                logger.warning("동 목록 조회 실패 (cortarNo: %s), 직접 단지 조회 시도", cortarno)
                complexes = await self.client.get_complexes_in_dong(cortarno)
                dongs = [{"cortarNo": cortarno, "cortarName": "전체"}] if complexes else []

            logger.info("지역 %s: %d개 동 발견", cortarno, len(dongs))

            for dong in dongs:
                dong_code = dong.get("cortarNo", "")
                dong_name = dong.get("cortarName", "")

                complexes = await self.client.get_complexes_in_dong(dong_code)
                if not complexes:
                    continue

                active_complexes = [
                    c for c in complexes
                    if (c.get("dealCount", 0) + c.get("leaseCount", 0) + c.get("rentCount", 0)) > 0
                ]
                logger.info("  동 [%s]: 전체 %d개 단지, 매물 있는 %d개 단지", dong_name, len(complexes), len(active_complexes))

                for cpx in active_complexes:
                    complex_no = cpx.get("complexNo", "")
                    complex_name = cpx.get("complexName", "")
                    cortar_address = cpx.get("cortarAddress", "")
                    total_households = cpx.get("totalHouseholdCount")

                    items = await self.client.fetch_complex_articles(
                        complex_no=complex_no,
                        complex_name=complex_name,
                        dong_address=cortar_address,
                        source_code=self.source_code,
                        total_households=total_households,
                    )
                    raw_listings.extend(items)
                    logger.info("    단지 [%s] → %d건 수집 (누적 %d건)", complex_name, len(items), len(raw_listings))

                    if limit and len(raw_listings) >= limit:
                        return raw_listings[:limit]

        except RuntimeError as r_err:
            if str(r_err) == "BROWSER_CLOSED":
                logger.info("브라우저 연결 중단으로 수집 루프를 안전하게 멈춥니다.")
                return raw_listings
            raise

        return raw_listings

    async def search(self, request: SourceSearchRequest, limit: int | None = None) -> list[RawListing]:
        """지역 기반 실제 매물 수집."""
        region_name = request.region_name or ""
        cortarno = resolve_cortarno(region_name)

        if not cortarno:
            logger.warning("지역 '%s'의 cortarNo를 찾을 수 없어 서울 전체를 수집합니다.", region_name)
            cortarno = "1100000000"

        try:
            if cortarno in SIDO_CODES.values():
                all_listings: list[RawListing] = []
                sido_name = None
                for sido, code in SIDO_CODES.items():
                    if code == cortarno:
                        sido_name = sido
                        break

                if sido_name and sido_name in SIGUNGU_CODES:
                    for sigungu_name, sigungu_code in SIGUNGU_CODES[sido_name].items():
                        logger.info("시/도 [%s] → 구/시 [%s] 수집 시작", sido_name, sigungu_name)
                        sub_listings = await self._collect_region(sigungu_code, limit=limit)
                        all_listings.extend(sub_listings)
                        if limit and len(all_listings) >= limit:
                            return all_listings[:limit]
                        if getattr(self.client, "_closed", False):
                            break
                return all_listings
            else:
                return await self._collect_region(cortarno, limit=limit)
        finally:
            await self.client.close()

    async def fetch_detail(self, raw_listing: RawListing) -> RawListing:
        """매물 상세 정보 보강."""
        return raw_listing

    async def check_availability(self, external_listing_id: str, source_url: str) -> bool:
        """매물 유효 여부 확인."""
        return True

    async def close(self):
        """리소스 해제."""
        await self.client.close()
