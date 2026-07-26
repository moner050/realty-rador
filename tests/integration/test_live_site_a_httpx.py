"""외부 SITE_A 검증: 자격 증명·본문을 절대 출력하거나 저장하지 않는다."""
import os

import httpx
import pytest

from realty_radar.crawler.adapters.site_a.bootstrap import NaverAuthBootstrap
from realty_radar.crawler.adapters.site_a.http_client import NaverHttpClient
from realty_radar.crawler.base.browser import PlaywrightBrowserManager


pytestmark = pytest.mark.live


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_authenticated_httpx_reaches_region_complex_and_article_apis():
    if os.getenv("RUN_LIVE_SITE_A_HTTPX") != "1":
        pytest.skip("set RUN_LIVE_SITE_A_HTTPX=1 to run external verification")

    # Plain httpx is intentionally observed first; its exact block status may change.
    async with httpx.AsyncClient(timeout=10) as plain:
        plain_response = await plain.get("https://new.land.naver.com/api/regions/list?cortarNo=1150000000")
    assert plain_response.status_code in {200, 401, 403, 429}

    browser = PlaywrightBrowserManager(headless=True)
    client = NaverHttpClient(NaverAuthBootstrap(browser))
    try:
        regions = await client.get_json("https://new.land.naver.com/api/regions/list", params={"cortarNo": 1150000000})
        assert isinstance(regions, dict)
        region_list = regions.get("regionList") or []
        assert region_list
        dong_code = int(region_list[0]["cortarNo"])

        complexes = await client.get_json(
            "https://new.land.naver.com/api/regions/complexes",
            params={"cortarNo": dong_code, "realEstateType": "APT", "order": ""},
        )
        assert isinstance(complexes, dict)
        complex_list = complexes.get("complexList") or []
        assert complex_list
        complex_id = int(complex_list[0]["complexNo"])

        articles = await client.get_json(
            f"https://new.land.naver.com/api/articles/complex/{complex_id}",
            params={"realEstateType": "APT", "tradeType": "", "sameAddressGroup": "false", "page": 1},
        )
        assert isinstance(articles, dict)
        assert isinstance(articles.get("articleList"), list)
    finally:
        await client.aclose()
        await browser.close()
