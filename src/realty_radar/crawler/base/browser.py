from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from realty_radar.config import settings


class PlaywrightBrowserManager:
    """Playwright 싱글톤 브라우저 인스턴스 및 세션/페이지 리소스 관리자."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None

    async def initialize(self) -> None:
        """브라우저 서브시스템 초기화."""
        if not self._playwright:
            self._playwright = await async_playwright().start()

        if not self._browser:
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--ignore-certificate-errors"],
            )

    async def close(self) -> None:
        """리소스 정리."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def get_auth_path(self, source_code: str) -> Path:
        """사이트별 세션 스토리지 파일 경로 반환."""
        settings.auth_directory.mkdir(parents=True, exist_ok=True)
        return settings.auth_directory / f"{source_code.lower()}_state.json"

    @asynccontextmanager
    async def get_page(self, source_code: str | None = None) -> AsyncGenerator[Page, None]:
        """자동으로 리소스를 회수하는 브라우저 페이지 컨텍스트 매니저 (SSL 오류 무시 처리)."""
        await self.initialize()
        assert self._browser is not None

        context_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "ignore_https_errors": True,  # SSL 인증서 오류 방지 무시
        }

        if source_code:
            auth_path = self.get_auth_path(source_code)
            if auth_path.exists():
                context_kwargs["storage_state"] = str(auth_path)

        context: BrowserContext = await self._browser.new_context(**context_kwargs)
        page: Page = await context.new_page()

        try:
            yield page
        finally:
            await page.close()
            await context.close()
