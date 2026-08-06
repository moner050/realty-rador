"""Redis 캐시 모듈 단위 테스트."""
from realty_radar.infrastructure.cache.map_cache import MapViewportCache, get_redis_client


def test_get_redis_client_handles_missing_redis_gracefully():
    """Redis 서버 미연동 환경에서 None을 반환하며 예외가 발생하지 않음."""
    client = get_redis_client()
    # redis 서버 미구동 상태여도 예외 없이 안전하게 처리
    assert client is None or hasattr(client, "get")


def test_map_viewport_cache_methods_run_without_exceptions():
    """Redis 미구동 상태에서 get/set 호출 시 예외 없이 처리됨."""
    result = MapViewportCache.get_viewport_cache("test_key")
    assert result is None

    MapViewportCache.set_viewport_cache("test_key", {"mode": "markers", "markers": []})
