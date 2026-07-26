"""Playwright로 SITE_A HTTP session을 bootstrap한다."""
from __future__ import annotations

import asyncio

from playwright.async_api import Request, Route

from realty_radar.crawler.adapters.site_a.http_client import (
    BROWSER_HEADER_NAMES,
    AuthenticationError,
    NaverCookie,
    NaverCredentials,
)
from realty_radar.crawler.base.browser import PlaywrightBrowserManager


BOOTSTRAP_URL = "https://new.land.naver.com/complexes/1001"
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


class NaverAuthBootstrap:
    """자격 증명만 메모리로 전달하고 page/context를 즉시 해제한다."""

    def __init__(self, browser_manager: PlaywrightBrowserManager, timeout_seconds: float = 20.0):
        self._browser_manager = browser_manager
        self._timeout_seconds = timeout_seconds

    async def __call__(self) -> NaverCredentials:
        context = await self._browser_manager.new_context()
        page = await context.new_page()
        authorization: str | None = None
        request_headers: dict[str, str] = {}
        authorization_ready = asyncio.Event()

        async def route_resource(route: Route) -> None:
            if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                await route.abort()
                return
            await route.continue_()

        def capture_request(request: Request) -> None:
            nonlocal authorization, request_headers
            token = request.headers.get("authorization")
            if token and authorization is None:
                authorization = token
                request_headers = {
                    name: value
                    for name, value in request.headers.items()
                    if name.lower() in BROWSER_HEADER_NAMES
                }
                authorization_ready.set()

        try:
            await context.route("**/*", route_resource)
            page.on("request", capture_request)
            await page.goto(BOOTSTRAP_URL, wait_until="domcontentloaded", timeout=int(self._timeout_seconds * 1000))
            await asyncio.wait_for(authorization_ready.wait(), timeout=self._timeout_seconds)
            playwright_cookies = await context.cookies()
            cookies = tuple(
                NaverCookie(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie["domain"],
                    path=cookie.get("path") or "/",
                )
                for cookie in playwright_cookies
            )
            if not authorization or not cookies:
                raise AuthenticationError("SITE_A bootstrap did not capture both authorization and cookies")
            return NaverCredentials(
                authorization=authorization,
                cookies=cookies,
                request_headers=request_headers,
            )
        except asyncio.TimeoutError as error:
            raise AuthenticationError("SITE_A bootstrap timed out before Authorization was observed") from error
        finally:
            await page.close()
            await context.close()
