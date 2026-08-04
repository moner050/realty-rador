from decimal import Decimal

import httpx

from realty_radar.enrichment.naver_maps.geocoder import GeocodeStatus, NaverGeocoder


def test_geocode_returns_verified_coordinates_from_naver_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/map-geocode/v2/geocode"
        assert request.url.params["query"] == "서울특별시 강서구 테스트로 1"
        assert request.headers["x-ncp-apigw-api-key-id"] == "public-key"
        assert request.headers["x-ncp-apigw-api-key"] == "server-secret"
        return httpx.Response(
            200,
            json={"status": "OK", "addresses": [{"x": "126.8500000", "y": "37.5500000"}]},
        )

    geocoder = NaverGeocoder(
        client_id="public-key",
        client_secret="server-secret",
        transport=httpx.MockTransport(handler),
    )

    result = geocoder.geocode("서울특별시 강서구 테스트로 1")

    assert result.status is GeocodeStatus.OK
    assert result.latitude == Decimal("37.5500000")
    assert result.longitude == Decimal("126.8500000")


def test_geocode_returns_not_found_without_coordinates_for_empty_address_list():
    geocoder = NaverGeocoder(
        client_id="public-key",
        client_secret="server-secret",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "OK", "addresses": []})),
    )

    result = geocoder.geocode("존재하지 않는 주소")

    assert result.status is GeocodeStatus.NOT_FOUND
    assert result.latitude is None
    assert result.longitude is None


def test_geocode_without_credentials_returns_not_configured_without_http_call():
    def no_request(_: httpx.Request) -> httpx.Response:
        raise AssertionError("키가 없으면 지오코딩 요청을 보내면 안 됩니다.")

    geocoder = NaverGeocoder(
        client_id="",
        client_secret="",
        transport=httpx.MockTransport(no_request),
    )

    result = geocoder.geocode("서울특별시 강서구 테스트로 1")

    assert result.status is GeocodeStatus.NOT_CONFIGURED
