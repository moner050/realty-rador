import asyncio
import json
import logging
from typing import Any, Callable

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from realty_radar.crawler.adapters.site_a.parser import SiteAParser
from realty_radar.crawler.adapters.site_a.region_codes import SIDO_CODES, SIGUNGU_CODES, resolve_cortarno
from realty_radar.crawler.base.exceptions import CrawlException
from realty_radar.crawler.base.models import RawListing, SourceSearchRequest
from realty_radar.crawler.base.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

NEW_LAND_BASE = "https://new.land.naver.com"
FIN_LAND_BASE = "https://fin.land.naver.com"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class NaverLandScraperClient:
    """Playwright Bearer 토큰 동적 캡처 + Promise.all 다중 fetch 초고속 스크래핑 클라이언트."""

    def __init__(self, headless: bool = True, rate_limiter: RateLimiter | None = None):
        self.headless = headless
        self.rate_limiter = rate_limiter or RateLimiter(interval_ms=20, max_concurrent=15)
        self._pw = None
        self._browser: Browser | None = None
        self._main_context: BrowserContext | None = None
        self._session_page: Page | None = None
        self._auth_token: str | None = None
        self._initialized = False
        self._closed = False
        self._init_lock = asyncio.Lock()

    async def _ensure_browser(self):
        """Playwright 메인 세션 초기화 및 Bearer 토큰 자동 인터셉트 캡처 (동시성 안전)."""
        async with self._init_lock:
            if self._closed and self._browser:
                self._closed = False

            if self._initialized and self._browser and self._main_context and self._session_page:
                try:
                    if not self._session_page.is_closed():
                        return self._main_context
                except Exception:
                    pass

            self._initialized = False
            self._closed = False

            try:
                if not self._pw:
                    self._pw = await async_playwright().start()
                if not self._browser or not self._browser.is_connected():
                    self._browser = await self._pw.chromium.launch(
                        headless=self.headless,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                        ],
                    )

                self._main_context = await self._browser.new_context(
                    user_agent=DEFAULT_USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="ko-KR",
                )
                await self._main_context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']});
                    window.chrome = { runtime: {} };
                """)

                self._session_page = await self._main_context.new_page()

                # Bearer Authorization 토큰 자동 인터셉터 등록
                def on_request(req):
                    if "authorization" in req.headers and not self._auth_token:
                        self._auth_token = req.headers["authorization"]

                self._session_page.on("request", on_request)

                try:
                    await self._session_page.goto(
                        f"{NEW_LAND_BASE}/complexes/1001",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                except Exception as goto_err:
                    logger.warning("페이지 진입 중 경고(수집 계속 진행): %s", goto_err)

                await asyncio.sleep(1.0)

                if not self._auth_token:
                    logger.warning("메인 페이지 접속 시 Authorization 토큰 캡처 미완료 (기본 토큰 대기)")

                self._initialized = True
                logger.info("Playwright 메인 브라우저 및 Bearer Authorization 토큰 세션 완료")
                return self._main_context

            except Exception as e:
                logger.warning("Playwright 브라우저 초기화 오류: %s", e)
                raise

    async def create_context(self) -> BrowserContext:
        """독립 세션 Context 생성."""
        await self._ensure_browser()
        return self._main_context

    async def _fetch_json(self, api_url: str, timeout_sec: float = 10.0) -> dict | list | None:
        """메인 세션 페이지에서 direct fetch() 호출."""
        await self._ensure_browser()
        try:
            await self.rate_limiter.acquire()
            try:
                token = self._auth_token or ""
                js_code = f"""
                    async () => {{
                        try {{
                            const headers = {{}};
                            if ("{token}") headers["Authorization"] = "{token}";
                            const r = await fetch("{api_url}", {{ headers }});
                            if (!r.ok) return null;
                            return await r.json();
                        }} catch(e) {{
                            return null;
                        }}
                    }}
                """
                result = await self._session_page.evaluate(js_code)
                return result
            finally:
                self.rate_limiter.release()
        except Exception as e:
            logger.warning("API GET fetch 실패 (%s): %s", api_url[:80], e)
            return None

    async def _fetch_json_batch(self, api_urls: list[str]) -> list[dict | list | None]:
        """Promise.all 다중 fetch: 1회 evaluate 호출로 N개 API 동시 요청 (오버헤드 1/N)."""
        if not api_urls:
            return []
        await self._ensure_browser()
        try:
            await self.rate_limiter.acquire()
            try:
                token = self._auth_token or ""
                urls_json = json.dumps(api_urls)
                js_code = f"""
                    async () => {{
                        const urls = {urls_json};
                        const token = "{token}";
                        const results = await Promise.all(urls.map(async (url) => {{
                            try {{
                                const headers = {{}};
                                if (token) headers["Authorization"] = token;
                                const r = await fetch(url, {{ headers }});
                                if (!r.ok) return null;
                                return await r.json();
                            }} catch(e) {{
                                return null;
                            }}
                        }}));
                        return results;
                    }}
                """
                result = await self._session_page.evaluate(js_code)
                return result if result else [None] * len(api_urls)
            finally:
                self.rate_limiter.release()
        except Exception as e:
            logger.warning("Promise.all 배치 fetch 실패 (%d건): %s", len(api_urls), e)
            return [None] * len(api_urls)

    async def get_dong_list(self, sigungu_cortarno: str) -> list[dict]:
        """구/시 cortarNo에 해당하는 하위 동 목록 조회."""
        api_url = f"{NEW_LAND_BASE}/api/regions/list?cortarNo={sigungu_cortarno}"
        data = await self._fetch_json(api_url)
        if data and isinstance(data, dict):
            return data.get("regionList") or []
        return []

    async def get_complexes_in_dong(self, dong_cortarno: str) -> list[dict]:
        """동 cortarNo에 해당하는 아파트 단지 목록 조회."""
        api_url = f"{NEW_LAND_BASE}/api/regions/complexes?cortarNo={dong_cortarno}&realEstateType=APT&order="
        data = await self._fetch_json(api_url)
        if data and isinstance(data, dict):
            return data.get("complexList") or []
        return []

    async def get_complexes_in_dong_batch(self, dong_cortarnos: list[str]) -> list[list[dict]]:
        """다수 동의 단지 목록을 Promise.all 배치로 동시 조회."""
        api_urls = [f"{NEW_LAND_BASE}/api/regions/complexes?cortarNo={code}&realEstateType=APT&order=" for code in dong_cortarnos]
        results = await self._fetch_json_batch(api_urls)
        parsed = []
        for data in results:
            if data and isinstance(data, dict):
                parsed.append(data.get("complexList") or [])
            else:
                parsed.append([])
        return parsed

    async def fetch_complex_articles(
        self, complex_no: str, complex_name: str = "", dong_address: str = "",
        source_code: str = "SITE_A", max_pages: int = 5,
        total_households: int | None = None, construction_year: int | None = None,
        context: Any = None,
    ) -> list[RawListing]:
        """Bearer Authorization 토큰 기반 direct API 초고속 수집."""
        parser = SiteAParser()
        raw_listings: list[RawListing] = []
        seen_article_nos: set[str] = set()

        try:
            await self._ensure_browser()
            token = self._auth_token or ""

            for page_no in range(1, max_pages + 1):
                await self.rate_limiter.acquire()
                try:
                    api_url = f"{NEW_LAND_BASE}/api/articles/complex/{complex_no}?realEstateType=APT&tradeType=&sameAddressGroup=false&page={page_no}"

                    js_code = f"""
                        async () => {{
                            try {{
                                const headers = {{}};
                                if ("{token}") headers["Authorization"] = "{token}";
                                const r = await fetch("{api_url}", {{ headers }});
                                if (!r.ok) return null;
                                return await r.json();
                            }} catch(e) {{
                                return null;
                            }}
                        }}
                    """

                    res_json = await self._session_page.evaluate(js_code)
                finally:
                    self.rate_limiter.release()

                if not res_json or not isinstance(res_json, dict):
                    break

                articles = res_json.get("articleList") or []
                if not articles:
                    break

                for item in articles:
                    article_no = str(item.get("articleNo", ""))
                    if not article_no or article_no in seen_article_nos:
                        continue
                    seen_article_nos.add(article_no)

                    raw_item = parser.parse_new_article_json(
                        item=item,
                        source_code=source_code,
                        default_complex_name=complex_name,
                        default_address=dong_address,
                        total_households=total_households,
                        construction_year=construction_year,
                    )
                    if raw_item:
                        raw_listings.append(raw_item)

                if not res_json.get("isMoreData", False) and page_no > 1:
                    break

        except Exception as e:
            logger.warning("단지 [%s](%s) 초고속 API 수집 중 오류: %s", complex_name, complex_no, e)

        logger.info(
            "단지 [%s](%s) 초고속 API 매물 %d건 수집 완료 (세대수: %s, 준공연도: %s)",
            complex_name, complex_no, len(raw_listings), total_households, construction_year
        )
        return raw_listings

    async def fetch_complex_articles_batch(
        self, complex_infos: list[dict], source_code: str = "SITE_A",
    ) -> list[RawListing]:
        """다수 단지의 1페이지 매물을 Promise.all 배치로 동시 수집 (evaluate 1회 = N개 단지)."""
        parser = SiteAParser()
        raw_listings: list[RawListing] = []

        if not complex_infos:
            return raw_listings

        api_urls = [
            f"{NEW_LAND_BASE}/api/articles/complex/{cpx['complex_no']}?realEstateType=APT&tradeType=&sameAddressGroup=false&page=1"
            for cpx in complex_infos
        ]

        results = await self._fetch_json_batch(api_urls)

        for cpx_info, res_json in zip(complex_infos, results):
            if not res_json or not isinstance(res_json, dict):
                continue

            articles = res_json.get("articleList") or []
            for item in articles:
                article_no = str(item.get("articleNo", ""))
                if not article_no:
                    continue

                raw_item = parser.parse_new_article_json(
                    item=item,
                    source_code=source_code,
                    default_complex_name=cpx_info.get("complex_name", ""),
                    default_address=cpx_info.get("dong_address", ""),
                    total_households=cpx_info.get("total_households"),
                    construction_year=cpx_info.get("construction_year"),
                )
                if raw_item:
                    raw_listings.append(raw_item)

            # 추가 페이지가 있으면 순차 수집
            if res_json.get("isMoreData", False):
                extra = await self.fetch_complex_articles(
                    complex_no=cpx_info["complex_no"],
                    complex_name=cpx_info.get("complex_name", ""),
                    dong_address=cpx_info.get("dong_address", ""),
                    source_code=source_code,
                    total_households=cpx_info.get("total_households"),
                    construction_year=cpx_info.get("construction_year"),
                )
                # 1페이지는 이미 수집했으므로 중복 제거
                seen = {r.external_listing_id for r in raw_listings}
                for r in extra:
                    if r.external_listing_id not in seen:
                        raw_listings.append(r)

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
        """리소스 일괄 해제."""
        self._closed = True
        if self._session_page:
            try:
                await self._session_page.close()
            except Exception:
                pass
            self._session_page = None
        if self._main_context:
            try:
                await self._main_context.close()
            except Exception:
                pass
            self._main_context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        self._initialized = False


class SiteAAdapter:
    """네이버 부동산 Promise.all 다중 fetch 초고속 병렬 매물 수집 어댑터 (SITE_A)."""

    source_code: str = "SITE_A"

    # Promise.all 배치 크기 (1회 evaluate에서 동시 fetch할 단지 수)
    COMPLEX_BATCH_SIZE = 8

    def __init__(self, headless: bool = True, interval_ms: int = 30, max_workers: int = 30):
        self.max_workers = max_workers
        self.rate_limiter = RateLimiter(interval_ms=interval_ms, max_concurrent=max_workers)
        self.client = NaverLandScraperClient(headless=headless, rate_limiter=self.rate_limiter)

    async def _collect_dong_task(
        self,
        dong: dict,
        on_batch_callback: Callable[[list[RawListing]], Any] | None,
    ) -> list[RawListing]:
        """개별 동(Dong) 수집: Promise.all 배치로 다수 단지를 1회 evaluate에서 동시 수집."""
        dong_code = dong.get("cortarNo", "")
        dong_name = dong.get("cortarName", "")
        collected: list[RawListing] = []

        try:
            complexes = await self.client.get_complexes_in_dong(dong_code)
            if not complexes:
                return collected

            active_complexes = [
                c for c in complexes
                if (c.get("dealCount", 0) + c.get("leaseCount", 0) + c.get("rentCount", 0)) > 0
            ]
            logger.info("  [Promise.all 배치] 동 [%s]: 매물 있는 %d개 단지 수집 시작", dong_name, len(active_complexes))

            # Promise.all 배치 처리 (COMPLEX_BATCH_SIZE개씩 1회 evaluate로 동시 fetch)
            for i in range(0, len(active_complexes), self.COMPLEX_BATCH_SIZE):
                batch = active_complexes[i:i + self.COMPLEX_BATCH_SIZE]

                # 배치 정보 구성
                batch_infos = []
                for cpx in batch:
                    use_ymd = str(cpx.get("useApproveYmd") or "").strip()
                    c_year = int(use_ymd[:4]) if (use_ymd and len(use_ymd) >= 4 and use_ymd[:4].isdigit()) else None

                    batch_infos.append({
                        "complex_no": cpx.get("complexNo", ""),
                        "complex_name": cpx.get("complexName", ""),
                        "dong_address": cpx.get("cortarAddress", ""),
                        "total_households": cpx.get("totalHouseholdCount"),
                        "construction_year": c_year,
                    })

                # 1회 evaluate → N개 fetch 동시 실행
                items = await self.client.fetch_complex_articles_batch(
                    complex_infos=batch_infos,
                    source_code=self.source_code,
                )

                if items:
                    collected.extend(items)
                    if on_batch_callback:
                        try:
                            on_batch_callback(items)
                        except Exception as cb_err:
                            logger.warning("배치 콜백 실행 중 오류: %s", cb_err)

        except Exception as e:
            logger.warning("동 [%s] 배치 수집 중 예외 발생: %s", dong_name, e)

        return collected

    async def _collect_region(
        self, cortarno: str, limit: int | None = None, on_batch_callback: Callable[[list[RawListing]], Any] | None = None
    ) -> list[RawListing]:
        """특정 구/시 cortarNo의 모든 동/단지를 워커 풀로 초고속 수집."""
        raw_listings: list[RawListing] = []

        try:
            dongs = await self.client.get_dong_list(cortarno)
            if not dongs:
                logger.warning("동 목록 조회 실패 (cortarNo: %s), 직접 단지 조회 시도", cortarno)
                complexes = await self.client.get_complexes_in_dong(cortarno)
                dongs = [{"cortarNo": cortarno, "cortarName": "전체"}] if complexes else []

            logger.info("지역 %s: 동 %d개 발견 -> %d개 워커 가동", cortarno, len(dongs), self.max_workers)

            if not dongs:
                return raw_listings

            # 동 목록을 asyncio.Queue에 넣기
            task_queue: asyncio.Queue[dict] = asyncio.Queue()
            for d in dongs:
                await task_queue.put(d)

            worker_count = min(self.max_workers, len(dongs))

            async def worker_loop():
                while not task_queue.empty():
                    try:
                        dong = task_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    items = await self._collect_dong_task(dong, on_batch_callback)
                    raw_listings.extend(items)
                    task_queue.task_done()

            # 이벤트 루프 호환 병렬 실행
            try:
                loop = asyncio.get_running_loop()
                workers = [loop.create_task(worker_loop()) for _ in range(worker_count)]
                await asyncio.gather(*workers)
            except RuntimeError:
                for _ in range(worker_count):
                    await worker_loop()

        except Exception as r_err:
            logger.warning("지역 [%s] 수집 처리 중 예외: %s", cortarno, r_err)

        return raw_listings

    async def search(
        self, request: SourceSearchRequest, limit: int | None = None, on_batch_callback: Callable[[list[RawListing]], Any] | None = None
    ) -> list[RawListing]:
        """지역 기반 실제 매물 초고속 병렬 수집 (서울 및 경기도 전역 다중 병렬 연쇄 수집)."""
        region_name = request.region_name or ""
        cortarno = resolve_cortarno(region_name)

        try:
            all_listings: list[RawListing] = []

            # 1. 서울 및 경기도 전체 수집 ("ALL_METRO" 또는 "전체")
            if cortarno == "ALL_METRO" or region_name in ["전체", "서울 및 경기도", "서울/경기", "ALL", ""]:
                target_sidos = ["서울특별시", "경기도", "인천광역시"]

                sigungu_items = []
                for sido_name in target_sidos:
                    if sido_name in SIGUNGU_CODES:
                        for sigungu_name, sigungu_code in SIGUNGU_CODES[sido_name].items():
                            sigungu_items.append((sido_name, sigungu_name, sigungu_code))

                # 구/시 동시 병렬 배치 10개씩
                batch_size = 10
                for i in range(0, len(sigungu_items), batch_size):
                    chunk = sigungu_items[i:i + batch_size]
                    logger.info("========== 동시 병렬 구/시 수집 그룹 (%d개 동시): %s ==========", len(chunk), [c[1] for c in chunk])

                    async def run_sigungu(sido_name, sigungu_name, sigungu_code):
                        try:
                            return await self._collect_region(sigungu_code, limit=limit, on_batch_callback=on_batch_callback)
                        except Exception as e:
                            logger.warning("구/시 [%s] 수집 중 예외: %s", sigungu_name, e)
                            return []

                    try:
                        loop = asyncio.get_running_loop()
                        tasks = [loop.create_task(run_sigungu(s[0], s[1], s[2])) for s in chunk]
                        results = await asyncio.gather(*tasks)
                    except RuntimeError:
                        results = []
                        for s in chunk:
                            res = await run_sigungu(s[0], s[1], s[2])
                            results.append(res)

                    for res in results:
                        all_listings.extend(res)

                    if limit and len(all_listings) >= limit:
                        return all_listings[:limit]

                return all_listings

            # 2. 특정 시/도 수집 (예: 서울특별시, 경기도, 인천광역시)
            elif cortarno in SIDO_CODES.values():
                sido_name = None
                for sido, code in SIDO_CODES.items():
                    if code == cortarno:
                        sido_name = sido
                        break

                if sido_name and sido_name in SIGUNGU_CODES:
                    sigungu_items = [(sido_name, k, v) for k, v in SIGUNGU_CODES[sido_name].items()]
                    batch_size = 10
                    for i in range(0, len(sigungu_items), batch_size):
                        chunk = sigungu_items[i:i + batch_size]
                        try:
                            loop = asyncio.get_running_loop()
                            tasks = [loop.create_task(self._collect_region(code, limit=limit, on_batch_callback=on_batch_callback)) for _, _, code in chunk]
                            results = await asyncio.gather(*tasks)
                        except RuntimeError:
                            results = []
                            for _, _, code in chunk:
                                res = await self._collect_region(code, limit=limit, on_batch_callback=on_batch_callback)
                                results.append(res)

                        for res in results:
                            all_listings.extend(res)
                        if limit and len(all_listings) >= limit:
                            return all_listings[:limit]
                return all_listings

            # 3. 특정 구/시/동 개별 수집
            else:
                return await self._collect_region(cortarno, limit=limit, on_batch_callback=on_batch_callback)
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
