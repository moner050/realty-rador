import asyncio
from realty_radar.enrichment.public_data.client import PublicDataApiClient


def test_public_data_client_mock_fetch():
    """공공데이터 API MOCK 수집기 단위 테스트."""
    client = PublicDataApiClient()
    trades = asyncio.run(client.fetch_apartment_trades("11560", "202607"))

    assert len(trades) >= 1
    assert trades[0]["apartment_name"] == "여의도 시범아파트"
    assert trades[0]["deal_amount"] > 0
