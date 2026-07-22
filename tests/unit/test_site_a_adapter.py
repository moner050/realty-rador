from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from realty_radar.crawler.adapters.site_a.adapter import SiteAAdapter
from realty_radar.crawler.base.models import RawListing, SourceSearchRequest


@pytest.mark.anyio
async def test_site_a_adapter_with_mock():
    adapter = SiteAAdapter()
    req = SourceSearchRequest(source_code="SITE_A", region_name="강서구")

    mock_raw_item = RawListing(
        source_code="SITE_A",
        external_listing_id="SITE_A-1001-0001",
        source_url="https://new.land.naver.com/complexes/1001",
        complex_name_raw="등촌동 아이파크 111동",
        address_raw="서울특별시 강서구 등촌동",
        price_raw="매매 15억 5,000",
        area_raw="전용 134.98㎡ / 공급 171㎡",
        floor_raw="고/20층",
        description_raw="초품아 역세권 디딤돌 가능",
    )

    mock_ctx = AsyncMock()

    with patch.object(adapter.client, "create_context", new_callable=AsyncMock) as mock_create_ctx, \
         patch.object(adapter.client, "get_dong_list", new_callable=AsyncMock) as mock_dong, \
         patch.object(adapter.client, "get_complexes_in_dong", new_callable=AsyncMock) as mock_cpx, \
         patch.object(adapter.client, "fetch_complex_articles", new_callable=AsyncMock) as mock_scrape:

        mock_create_ctx.return_value = mock_ctx
        mock_dong.return_value = [{"cortarNo": "1150010200", "cortarName": "등촌동"}]
        mock_cpx.return_value = [{
            "complexNo": "1001",
            "complexName": "등촌동 아이파크",
            "cortarAddress": "서울특별시 강서구 등촌동",
            "detailAddress": "138",
            "dealCount": 1,
            "leaseCount": 0,
            "rentCount": 0,
        }]
        mock_scrape.return_value = [mock_raw_item]

        listings = await adapter.search(req, limit=5)
        assert len(listings) == 1
        assert listings[0].source_code == "SITE_A"
        assert listings[0].external_listing_id == "SITE_A-1001-0001"
        assert "등촌동 아이파크" in listings[0].complex_name_raw
        assert "15억 5,000" in listings[0].price_raw
