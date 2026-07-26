import pytest

from realty_radar.crawler.adapters.site_a.adapter import SiteAAdapter, SiteAComplex


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _article(article_no: int) -> dict:
    return {
        "articleNo": article_no,
        "tradeTypeCode": "A1",
        "dealOrWarrantPrc": "5억",
        "area1": "110.0",
        "area2": "84.97",
        "floorInfo": "10/20",
        "buildingName": "101",
    }


class FakeApi:
    def __init__(self, pages: dict[int, dict]):
        self.pages = pages
        self.requested_pages: list[int] = []

    async def complexes(self, region_code: int):
        return [
            SiteAComplex(
                complex_id=1001,
                region_code=region_code,
                name="테스트 아파트",
                address="서울특별시 강서구 테스트로 1",
                normalized_name="테스트아파트",
            )
        ]

    async def articles(self, complex_id: int, page: int):
        self.requested_pages.append(page)
        return self.pages[page]


@pytest.mark.anyio
async def test_is_more_data_adds_the_next_page_to_the_shared_queue():
    api = FakeApi(
        {
            1: {"articleList": [_article(2001)], "isMoreData": True},
            2: {"articleList": [_article(2002)], "isMoreData": False},
        }
    )
    adapter = SiteAAdapter(api=api)
    batches = []

    outcome = await adapter.collect_dong(1150010200, lambda rows: batches.append(rows))

    assert outcome.partial is False
    assert api.requested_pages == [1, 2]
    assert [item.article_id for batch in batches for item in batch] == [2001, 2002]


@pytest.mark.anyio
async def test_repeated_page_marks_the_dong_partial_and_does_not_loop():
    api = FakeApi(
        {
            1: {"articleList": [_article(2001)], "isMoreData": True},
            2: {"articleList": [_article(2001)], "isMoreData": True},
        }
    )
    adapter = SiteAAdapter(api=api)

    outcome = await adapter.collect_dong(1150010200, lambda rows: None)

    assert outcome.partial is True
    assert api.requested_pages == [1, 2]
